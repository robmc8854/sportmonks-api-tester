import os
import time
import threading
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, jsonify, request
from dateutil import tz

# -----------------------------
# Config & Globals
# -----------------------------
APP_TZ = os.getenv("APP_TIMEZONE", "Europe/London")
BASE_URL = "https://api.sportmonks.com/v3"
RAW_TOKEN = os.getenv("SPORTMONKS_API_TOKEN", "")
# token sanitization (helpful for copy/paste issues)
SPORTMONKS_TOKEN = RAW_TOKEN.strip().replace("\n", "").replace("\r", "").replace("=", "")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_TOKEN and CHAT_ID)

# How often to auto-run (minutes)
EVERY_MINUTES = int(os.getenv("EVERY_MINUTES", "60"))

# League whitelist (optional). Comma-separated IDs or empty for all.
LEAGUE_WHITELIST = {
    x.strip() for x in os.getenv("LEAGUE_WHITELIST", "").split(",") if x.strip()
}

# Value bet threshold (% edge)
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "5"))  # 5% default

# includes (verified)
INCLUDES_FIXTURE = "participants,scores,state,league,venue,weatherreport,events,statistics.type,lineups.player,odds"
INCLUDES_LIVE = "participants,scores,state,league,events,statistics.type,odds"

# in-memory state
STATE: Dict[str, Any] = {
    "last_run": None,
    "predictions": {},   # key: date -> list of fixtures with prediction + odds + valueBets
    "value_bets": {},    # key: date -> list of value bets
    "errors": []
}

# logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bet-bot")


# -----------------------------
# HTTP helpers
# -----------------------------
def sportmonks_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not SPORTMONKS_TOKEN:
        return {"data": []}

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    q = dict(params or {})
    q["api_token"] = SPORTMONKS_TOKEN

    try:
        r = requests.get(url, params=q, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        msg = f"HTTP error GET {endpoint}: {e}"
        log.error(msg)
        STATE["errors"].append({"t": utc_now_iso(), "msg": msg})
        return {"data": []}


def utc_now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=tz.UTC).isoformat()


# -----------------------------
# Data fetchers
# -----------------------------
def get_fixtures_by_date(d: str, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    params = {
        "include": INCLUDES_FIXTURE,
        "per_page": 100
    }
    if league_id:
        params["filter[league_id]"] = league_id
    data = sportmonks_get(f"football/fixtures/date/{d}", params)
    return data.get("data", [])


def get_season_for_league(league_id: str) -> Optional[str]:
    data = sportmonks_get("football/seasons", {
        "filter[league_id]": league_id,
        "include": "league",
        "per_page": 1
    })
    seasons = data.get("data", [])
    return str(seasons[0]["id"]) if seasons else None


def get_standings_for_season(season_id: str) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/standings/seasons/{season_id}", {"include": "participant"})
    blocks = data.get("data", [])
    if not blocks:
        return []
    return blocks[0].get("standings", [])


def get_team_recent_form(team_id: int, start: str, end: str, limit: int = 5) -> Dict[str, Any]:
    data = sportmonks_get(f"football/fixtures/between/{start}/{end}/{team_id}", {
        "include": "participants,scores",
        "per_page": limit
    })
    fixtures = data.get("data", [])
    wins = draws = losses = 0
    for fx in fixtures:
        team_score = 0
        opp_score = 0
        for s in fx.get("scores", []):
            total = (s.get("score") or {}).get("total", 0)
            if s.get("participant_id") == team_id:
                team_score = total
            else:
                opp_score = total
        if team_score > opp_score:
            wins += 1
        elif team_score == opp_score:
            draws += 1
        else:
            losses += 1
    total_games = wins + draws + losses
    form_score = (wins * 3 + draws) / (total_games * 3) if total_games > 0 else 0.5
    return {
        "wins": wins, "draws": draws, "losses": losses,
        "formScore": form_score, "form": f"{wins}W-{draws}D-{losses}L"
    }


def get_head_to_head(team_a: int, team_b: int) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/fixtures/head-to-head/{team_a}/{team_b}", {
        "include": "participants,scores"
    })
    return data.get("data", [])


# -----------------------------
# Prediction math (from your React logic)
# -----------------------------
def calculate_h2h_factor(h2h_fixtures: List[Dict[str, Any]], home_team_id: int) -> float:
    if not h2h_fixtures:
        return 0.0
    recent = h2h_fixtures[-5:]
    home_wins = 0
    for fx in recent:
        home_score = 0
        away_score = 0
        for s in fx.get("scores", []):
            total = (s.get("score") or {}).get("total", 0)
            if s.get("participant_id") == home_team_id:
                home_score = total
            else:
                away_score = total
        if home_score > away_score:
            home_wins += 1
    return (home_wins / len(recent)) - 0.5 if recent else 0.0


def calculate_weather_impact(weather: Optional[Dict[str, Any]]) -> float:
    if not weather:
        return 1.0
    factor = 1.0
    t = weather.get("temperature_celsius")
    if t is not None and (t < 5 or t > 35):
        factor *= 0.95
    w = weather.get("wind_speed")
    if w is not None and w > 20:
        factor *= 0.9
    desc = (weather.get("weather_report") or {}).get("description", "")
    if isinstance(desc, str) and "rain" in desc.lower():
        factor *= 0.85
    return factor


def calculate_confidence(home_p: float, away_p: float, draw_p: float,
                         standings_rel: float, form_rel: float, h2h_rel: float) -> float:
    max_p = max(home_p, away_p, draw_p)
    decisiveness = (max_p - (1/3)) / (2/3)  # 0..1
    data_rel = (standings_rel + form_rel + h2h_rel) / 3.0
    return max(0.1, min(0.95, decisiveness * 0.7 + data_rel * 0.3))


def advanced_prediction(fixture: Dict[str, Any],
                        standings: List[Dict[str, Any]],
                        head_to_head: List[Dict[str, Any]],
                        team_form: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    participants = fixture.get("participants") or []
    if len(participants) < 2:
        return {}

    home = participants[0]
    away = participants[1]
    home_id = int(home.get("id"))
    away_id = int(away.get("id"))

    def standing_for(team_id: int) -> Dict[str, Any]:
        for s in standings:
            if int(s.get("participant_id")) == team_id:
                return s
        return {}

    hs = standing_for(home_id)
    as_ = standing_for(away_id)

    home_position = hs.get("position") or 10
    away_position = as_.get("position") or 10
    home_points = hs.get("points") or 20
    away_points = as_.get("points") or 20

    home_form_score = (team_form.get(home_id) or {}).get("formScore", 0.5)
    away_form_score = (team_form.get(away_id) or {}).get("formScore", 0.5)

    h2h_factor = calculate_h2h_factor(head_to_head, home_id)
    weather_factor = calculate_weather_impact(fixture.get("weatherreport"))

    home_adv = 0.1

    home_p = 0.4 + home_adv
    away_p = 0.3
    draw_p = 0.3

    position_diff = (int(away_position) - int(home_position)) / 20.0
    home_p += position_diff * 0.2
    away_p -= position_diff * 0.2

    points_diff = (float(home_points) - float(away_points)) / 50.0
    home_p += points_diff * 0.15
    away_p -= points_diff * 0.15

    home_p += (home_form_score - 0.5) * 0.2
    away_p += (away_form_score - 0.5) * 0.2

    home_p += h2h_factor * 0.1
    away_p -= h2h_factor * 0.1

    home_p *= weather_factor

    total = home_p + away_p + draw_p
    if total <= 0:
        home_p = away_p = draw_p = 1/3
    else:
        home_p /= total
        away_p /= total
        draw_p /= total

    home_xg = max(0.5, 1.5 + (home_form_score - away_form_score) * 2)
    away_xg = max(0.5, 1.2 + (away_form_score - home_form_score) * 2)
    total_xg = home_xg + away_xg
    over25 = 0.6 + (total_xg - 2.5) * 0.15 if total_xg > 2.5 else 0.4 - (2.5 - total_xg) * 0.15
    over25 = max(0.0, min(1.0, over25))
    btts = max(0.1, min(0.9, (home_xg * away_xg) / 4.0))

    confidence = calculate_confidence(
        home_p, away_p, draw_p,
        0.8 if standings else 0.3,
        0.7 if team_form else 0.2,
        0.6 if head_to_head else 0.1
    )

    return {
        "match_winner": {
            "home": round(home_p * 100),
            "draw": round(draw_p * 100),
            "away": round(away_p * 100),
        },
        "over_under_25": {
            "over": round(over25 * 100),
            "under": round((1 - over25) * 100),
        },
        "both_teams_score": {
            "yes": round(btts * 100),
            "no": round((1 - btts) * 100),
        },
        "expected_goals": {
            "home": f"{home_xg:.1f}",
            "away": f"{away_xg:.1f}",
            "total": f"{(home_xg + away_xg):.1f}",
        },
        "confidence": round(confidence * 100),
        "factors": {
            "form": {"home": home_form_score, "away": away_form_score},
            "standings": {"home": home_position, "away": away_position},
            "headToHead": h2h_factor,
            "weather": weather_factor,
            "homeAdvantage": home_adv,
        },
    }


def calculate_value_bets(fixtures_with_preds: List[Dict[str, Any]], edge_min: float = EDGE_THRESHOLD) -> List[Dict[str, Any]]:
    out = []
    for match in fixtures_with_preds:
        odds = match.get("odds") or {}
        pred = match.get("prediction") or {}
        if not odds or not pred:
            match["valueBets"] = []
            continue

        value_bets = []
        mw = odds.get("match_winner")
        if mw:
            home_odds = mw.get("home")
            draw_odds = mw.get("draw")
            away_odds = mw.get("away")
            if all([home_odds, draw_odds, away_odds]):
                home_implied = 1.0 / float(home_odds)
                draw_implied = 1.0 / float(draw_odds)
                away_implied = 1.0 / float(away_odds)

                home_pred = (pred["match_winner"]["home"]) / 100.0
                draw_pred = (pred["match_winner"]["draw"]) / 100.0
                away_pred = (pred["match_winner"]["away"]) / 100.0

                # value if predicted > implied * 1.05 (or EDGE_MIN)
                em = 1.0 + (edge_min / 100.0)

                if home_pred > home_implied * em:
                    value_bets.append({
                        "market": "Match Winner",
                        "selection": "Home Win",
                        "odds": home_odds,
                        "predictedProb": f"{home_pred*100:.1f}",
                        "impliedProb": f"{home_implied*100:.1f}",
                        "edge": f"{(home_pred - home_implied)*100:.1f}"
                    })
                if draw_pred > draw_implied * em:
                    value_bets.append({
                        "market": "Match Winner",
                        "selection": "Draw",
                        "odds": draw_odds,
                        "predictedProb": f"{draw_pred*100:.1f}",
                        "impliedProb": f"{draw_implied*100:.1f}",
                        "edge": f"{(draw_pred - draw_implied)*100:.1f}"
                    })
                if away_pred > away_implied * em:
                    value_bets.append({
                        "market": "Match Winner",
                        "selection": "Away Win",
                        "odds": away_odds,
                        "predictedProb": f"{away_pred*100:.1f}",
                        "impliedProb": f"{away_implied*100:.1f}",
                        "edge": f"{(away_pred - away_implied)*100:.1f}"
                    })
        match["valueBets"] = value_bets
        out.extend([dict(vb, fixture=match) for vb in value_bets])
    return out


# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline_for_date(d: str) -> Dict[str, Any]:
    log.info(f"Running predictions for {d}")
    fixtures = get_fixtures_by_date(d)

    if LEAGUE_WHITELIST:
        fixtures = [f for f in fixtures if str((f.get("league") or {}).get("id", "")) in LEAGUE_WHITELIST]

    # collect team ids
    team_ids: List[int] = []
    for fx in fixtures:
        for p in fx.get("participants") or []:
            if "id" in p:
                team_ids.append(int(p["id"]))
    team_ids = sorted(list(set(team_ids)))

    # standings (if one league chosen, pick that season. Otherwise skip to keep it simple)
    # You can expand to per-league standings cache if needed.
    standings_all: List[Dict[str, Any]] = []
    if fixtures:
        # opportunistic: use league of first fixture
        first_league_id = str((fixtures[0].get("league") or {}).get("id", ""))
        if first_league_id:
            season_id = get_season_for_league(first_league_id)
            if season_id:
                standings_all = get_standings_for_season(season_id)

    # team form over YTD
    today = date.fromisoformat(d)
    start = (today - timedelta(days=180)).isoformat()
    end = d
    team_form: Dict[int, Dict[str, Any]] = {}
    for tid in team_ids:
        team_form[tid] = get_team_recent_form(tid, start, end, limit=5)

    # predictions per fixture
    results: List[Dict[str, Any]] = []
    for fx in fixtures:
        parts = fx.get("participants") or []
        if len(parts) < 2:
            continue
        teamA = int(parts[0]["id"])
        teamB = int(parts[1]["id"])
        try:
            h2h = get_head_to_head(teamA, teamB)
        except Exception:
            h2h = []

        pred = advanced_prediction(fx, standings_all, h2h, team_form)
        if not pred:
            continue
        out_fx = dict(fx)
        out_fx["prediction"] = pred
        results.append(out_fx)

    value_bets = calculate_value_bets(results, EDGE_THRESHOLD)
    results_sorted = sorted(results, key=lambda r: r["prediction"]["confidence"], reverse=True)
    value_bets_sorted = sorted(value_bets, key=lambda v: float(v["edge"]), reverse=True)

    STATE["predictions"][d] = results_sorted
    STATE["value_bets"][d] = value_bets_sorted
    STATE["last_run"] = utc_now_iso()
    return {"count": len(results_sorted), "value_bets": len(value_bets_sorted)}


# -----------------------------
# Telegram
# -----------------------------
def send_telegram(text: str):
    if not SEND_TELEGRAM:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        log.error(f"Telegram send error: {e}")


def notify_top_value_bets(d: str, top_n: int = 3):
    if not SEND_TELEGRAM:
        return
    vbs = STATE["value_bets"].get(d, [])[:top_n]
    if not vbs:
        send_telegram(f"[{d}] No value bets found (edge >= {EDGE_THRESHOLD}%).")
        return
    lines = [f"[{d}] Top Value Bets (edge ≥ {EDGE_THRESHOLD}%):"]
    for vb in vbs:
        fx = vb["fixture"]
        home = fx["participants"][0]["name"]
        away = fx["participants"][1]["name"]
        when = fx.get("starting_at")
        edge = vb["edge"]
        lines.append(f"• {home} vs {away} @ {when} — {vb['market']} / {vb['selection']} — odds {vb['odds']} (edge +{edge}%)")
    send_telegram("\n".join(lines))


# -----------------------------
# Scheduler
# -----------------------------
def scheduler_loop():
    while True:
        try:
            d = date.today().isoformat()
            stats = run_pipeline_for_date(d)
            notify_top_value_bets(d, top_n=3)
            log.info(f"Run complete for {d}: {stats}")
        except Exception as e:
            msg = f"scheduler error: {e}"
            log.error(msg)
            STATE["errors"].append({"t": utc_now_iso(), "msg": msg})
        time.sleep(EVERY_MINUTES * 60)


# -----------------------------
# Flask app & routes
# -----------------------------
app = Flask(__name__)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "last_run": STATE["last_run"], "errors": STATE["errors"][-5:]})


@app.route("/refresh", methods=["POST", "GET"])
def refresh():
    # allow ?date=YYYY-MM-DD or default today
    d = request.args.get("date") or date.today().isoformat()
    stats = run_pipeline_for_date(d)
    notify_top_value_bets(d, top_n=3)
    return jsonify({"ok": True, "date": d, "stats": stats})


@app.route("/predictions")
def predictions():
    d = request.args.get("date") or date.today().isoformat()
    return jsonify({
        "date": d,
        "count": len(STATE["predictions"].get(d, [])),
        "items": STATE["predictions"].get(d, []),
        "last_run": STATE["last_run"]
    })


@app.route("/value-bets")
def value_bets():
    d = request.args.get("date") or date.today().isoformat()
    return jsonify({
        "date": d,
        "count": len(STATE["value_bets"].get(d, [])),
        "items": STATE["value_bets"].get(d, []),
        "edge_threshold": EDGE_THRESHOLD,
        "last_run": STATE["last_run"]
    })


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "SportMonks betting bot running",
        "endpoints": ["/refresh?date=YYYY-MM-DD", "/predictions?date=YYYY-MM-DD", "/value-bets?date=YYYY-MM-DD", "/healthz"],
        "tz": APP_TZ,
        "every_minutes": EVERY_MINUTES,
        "edge_threshold": EDGE_THRESHOLD
    })


if __name__ == "__main__":
    # start background scheduler
    threading.Thread(target=scheduler_loop, daemon=True).start()
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)