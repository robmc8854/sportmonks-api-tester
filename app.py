# app.py — API-FOOTBALL (API-SPORTS) version with bookmaker filters, extra markets, CSV export, in-play scan
import os, sys, time, threading, logging, csv, io
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request, Response
from dateutil import tz

# =========================
# Config
# =========================
APP_TZ = os.getenv("APP_TIMEZONE", "Europe/London")

APIS_BASE = "https://v3.football.api-sports.io"
APIS_KEY = (os.getenv("APISPORTS_KEY") or os.getenv("API_SPORTS_KEY") or "").strip()
HEADERS = {"x-apisports-key": APIS_KEY}

EVERY_MINUTES = int(os.getenv("EVERY_MINUTES", "60"))            # daily cycle
INPLAY_MINUTES = int(os.getenv("INPLAY_MINUTES", "0"))            # 0 disables in-play scan; e.g., 5 to enable
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "5"))          # % edge
LEAGUE_WHITELIST = {x.strip() for x in os.getenv("LEAGUE_WHITELIST", "").split(",") if x.strip()}

# Bookmaker controls
# Priority list: we pick the first bookmaker found in this order; if not present we fall back to "best price".
BOOKMAKER_PRIORITY = [x.strip() for x in os.getenv(
    "APIS_BOOKMAKERS", "Pinnacle, bet365, Betfair, 1xBet, William Hill, Marathonbet"
).split(",") if x.strip()]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_TOKEN and CHAT_ID)

STATE: Dict[str, Any] = {
    "last_run": None,
    "predictions": {},  # date -> fixtures w/ prediction
    "value_bets": {},   # date -> value bets (vb + fixture)
    "errors": []
}

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
log = logging.getLogger("bet-bot")
log.info("Booting API-FOOTBALL… tz=%s edge_threshold=%s every_minutes=%s key=%s",
         APP_TZ, EDGE_THRESHOLD, EVERY_MINUTES, "SET" if APIS_KEY else "MISSING")

def utc_now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=tz.UTC).isoformat()

def record_error(msg: str):
    STATE["errors"].append({"t": utc_now_iso(), "msg": msg})

# =========================
# HTTP helper with simple retry (429/5xx)
# =========================
def apis_get(path: str, params: Optional[Dict[str, Any]] = None, expect_list=True, retries: int = 2) -> Dict[str, Any]:
    if not APIS_KEY:
        msg = "API-FOOTBALL key missing — returning empty"
        log.warning(msg); record_error(msg)
        return {"response": [], "results": 0, "paging": {"current": 1, "total": 1}}

    url = f"{APIS_BASE}/{path.lstrip('/')}"
    q = dict(params or {})
    attempt = 0
    while True:
        attempt += 1
        try:
            log.info("GET %s params=%s attempt=%s", url, q, attempt)
            r = requests.get(url, headers=HEADERS, params=q, timeout=45)
            log.info("↳ status=%s, remaining=%s", r.status_code, r.headers.get("x-ratelimit-remaining", "?"))
            if r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt <= retries:
                    backoff = 2 ** attempt
                    log.warning("Rate/Server issue (%s). Backing off %ss…", r.status_code, backoff)
                    time.sleep(backoff); continue
            if r.status_code != 200:
                log.error("Body: %s", r.text[:800])
            r.raise_for_status()
            data = r.json()
            if expect_list:
                log.info("↳ results=%s paging=%s", data.get("results"), data.get("paging"))
            return data
        except Exception as e:
            if attempt <= retries:
                backoff = 2 ** attempt
                log.warning("HTTP error %s. Retry in %ss", e, backoff)
                time.sleep(backoff); continue
            msg = f"HTTP error GET {path}: {e}"
            log.exception(msg); record_error(msg)
            return {"response": [], "results": 0, "paging": {"current": 1, "total": 1}}

def apis_paginated(path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = apis_get(path, {**params, "page": page})
        chunk = data.get("response", []) or []
        items.extend(chunk)
        paging = data.get("paging") or {}
        log.info("Pagination page=%s got=%s total_pages=%s", page, len(chunk), paging.get("total"))
        if not chunk or page >= int(paging.get("total", 1)):
            break
        page += 1
    return items

# =========================
# Fetchers (API-FOOTBALL)
# =========================
def get_fixtures_by_date(d: str) -> List[Dict[str, Any]]:
    fixtures = apis_paginated("fixtures", {"date": d})
    log.info("Fixtures on %s: %d", d, len(fixtures))
    if LEAGUE_WHITELIST:
        before = len(fixtures)
        fixtures = [fx for fx in fixtures if str((fx.get("league") or {}).get("id", "")) in LEAGUE_WHITELIST]
        log.info("Whitelist filtered: %d -> %d", before, len(fixtures))
    return fixtures

def get_standings(league_id: int, season: int) -> List[Dict[str, Any]]:
    data = apis_get("standings", {"league": league_id, "season": season})
    resp = data.get("response", [])
    if not resp:
        return []
    tables = (((resp[0] or {}).get("league") or {}).get("standings") or [])
    rows = tables[0] if tables else []
    out = []
    for r in rows:
        out.append({
            "team_id": ((r.get("team") or {}).get("id")),
            "position": r.get("rank"),
            "points": (r.get("points")),
        })
    log.info("Standings %s/%s rows=%d", league_id, season, len(out))
    return out

def get_head_to_head(home_id: int, away_id: int, last: int = 5) -> List[Dict[str, Any]]:
    data = apis_get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last})
    return data.get("response", [])

def get_team_form(team_id: int, start: str, end: str, season_hint: Optional[int]) -> Dict[str, Any]:
    params = {"team": team_id, "from": start, "to": end}
    if season_hint:
        params["season"] = season_hint
    data = apis_get("fixtures", params)
    fixtures = data.get("response", [])[:5]
    wins = draws = losses = 0
    for fx in fixtures:
        gh = ((fx.get("goals") or {}).get("home") or 0)
        ga = ((fx.get("goals") or {}).get("away") or 0)
        th = ((fx.get("teams") or {}).get("home") or {})
        ta = ((fx.get("teams") or {}).get("away") or {})
        is_home = th.get("id") == team_id
        team_goals = gh if is_home else ga
        opp_goals = ga if is_home else gh
        if team_goals > opp_goals: wins += 1
        elif team_goals == opp_goals: draws += 1
        else: losses += 1
    total = wins + draws + losses
    form_score = (wins*3 + draws)/(total*3) if total>0 else 0.5
    out = {"wins": wins, "draws": draws, "losses": losses, "formScore": form_score, "form": f"{wins}W-{draws}D-{losses}L"}
    log.info("Form team=%s -> %s", team_id, out)
    return out

# =========================
# Odds parsing (bookmaker priority + multiple markets)
# =========================
def _bookmaker_rank(name: str) -> int:
    """Lower rank = higher priority. Unknown bookmakers get large rank."""
    name_l = (name or "").strip().lower()
    for idx, ref in enumerate(BOOKMAKER_PRIORITY):
        if name_l == ref.strip().lower():
            return idx
    return 999  # unknowns last

def _pick_best(values: List[Tuple[str, float, str]], prefer_label_set: set) -> Optional[Tuple[str, float, str]]:
    """
    values: list of (bookmakerName, oddFloat, label/selection)
    prefer_label_set: e.g., {"home","draw","away"} or {"over 2.5","under 2.5"} or {"yes","no"}
    Strategy: sort by bookmaker priority, then by highest odds within same bookmaker.
    If none match prefer_label_set, return the max odd overall.
    """
    if not values:
        return None
    # filter to desired labels if present
    filtered = [v for v in values if v[2].lower() in prefer_label_set]
    pool = filtered if filtered else values
    # group by bookmaker priority
    pool.sort(key=lambda x: (_bookmaker_rank(x[0]), -x[1]))
    return pool[0]  # best bookmaker by priority, highest price within

def get_odds_for_fixture(fixture_id: int) -> Dict[str, Any]:
    """
    /odds?fixture=ID — extract:
      - match_winner: {home, draw, away}
      - over_under_25: {over, under}
      - both_teams_score: {yes, no}
    We prefer bookmakers in BOOKMAKER_PRIORITY, otherwise best available.
    """
    data = apis_get("odds", {"fixture": fixture_id})
    resp = data.get("response", [])
    if not resp:
        return {}

    # Collect all candidates
    oneX2_vals: List[Tuple[str, float, str]] = []     # (book, odd, "home"/"draw"/"away")
    ou25_vals: List[Tuple[str, float, str]] = []      # (book, odd, "over 2.5"/"under 2.5")
    btts_vals: List[Tuple[str, float, str]] = []      # (book, odd, "yes"/"no")

    for book in resp:
        bname = (book.get("bookmaker") or {}).get("name") or book.get("name") or ""
        for bet in (book.get("bets") or []):
            bet_name = (bet.get("name") or "").lower().strip()
            values = bet.get("values") or []

            # 1X2 aliases
            if bet_name in ("match winner", "1x2", "winner"):
                for sel in values:
                    try:
                        odd = float(sel.get("odd"))
                    except Exception:
                        continue
                    label = (sel.get("value") or "").lower().strip()
                    if label in ("home", "1", "home team"):
                        oneX2_vals.append((bname, odd, "home"))
                    elif label in ("draw", "x"):
                        oneX2_vals.append((bname, odd, "draw"))
                    elif label in ("away", "2", "away team"):
                        oneX2_vals.append((bname, odd, "away"))

            # Over/Under aliases (we target 2.5 total goals)
            if "over" in bet_name and "under" in bet_name:
                for sel in values:
                    try:
                        odd = float(sel.get("odd"))
                    except Exception:
                        continue
                    label = (sel.get("value") or "").lower().strip()  # e.g., "Over 2.5"
                    if label in ("over 2.5", "o 2.5", "over2.5"):
                        ou25_vals.append((bname, odd, "over 2.5"))
                    elif label in ("under 2.5", "u 2.5", "under2.5"):
                        ou25_vals.append((bname, odd, "under 2.5"))

            # BTTS aliases
            if "both teams to score" in bet_name or "btts" in bet_name:
                for sel in values:
                    try:
                        odd = float(sel.get("odd"))
                    except Exception:
                        continue
                    label = (sel.get("value") or "").lower().strip()
                    if label in ("yes", "y"):
                        btts_vals.append((bname, odd, "yes"))
                    elif label in ("no", "n"):
                        btts_vals.append((bname, odd, "no"))

    result = {}

    # choose best by bookmaker priority then price
    best_home = _pick_best([v for v in oneX2_vals if v[2] == "home"], {"home"})
    best_draw = _pick_best([v for v in oneX2_vals if v[2] == "draw"], {"draw"})
    best_away = _pick_best([v for v in oneX2_vals if v[2] == "away"], {"away"})
    if best_home or best_draw or best_away:
        result["match_winner"] = {
            "home": best_home[1] if best_home else None,
            "draw": best_draw[1] if best_draw else None,
            "away": best_away[1] if best_away else None,
        }

    best_over = _pick_best(ou25_vals, {"over 2.5"})
    best_under = _pick_best(ou25_vals, {"under 2.5"})
    if best_over or best_under:
        result["over_under_25"] = {
            "over": best_over[1] if best_over else None,
            "under": best_under[1] if best_under else None,
        }

    best_yes = _pick_best(btts_vals, {"yes"})
    best_no  = _pick_best(btts_vals, {"no"})
    if best_yes or best_no:
        result["both_teams_score"] = {
            "yes": best_yes[1] if best_yes else None,
            "no": best_no[1] if best_no else None,
        }

    return result

# =========================
# Prediction math (unchanged core)
# =========================
def calculate_h2h_factor(h2h_fixtures: List[Dict[str, Any]], home_team_id: int) -> float:
    if not h2h_fixtures: return 0.0
    recent = h2h_fixtures[-5:]
    home_wins = 0
    for fx in recent:
        th = ((fx.get("teams") or {}).get("home") or {}).get("id")
        ta = ((fx.get("teams") or {}).get("away") or {}).get("id")
        gh = ((fx.get("goals") or {}).get("home") or 0)
        ga = ((fx.get("goals") or {}).get("away") or 0)
        if th == home_team_id and gh > ga: home_wins += 1
        elif ta == home_team_id and ga > gh: home_wins += 1
    return (home_wins/len(recent)) - 0.5 if recent else 0.0

def calculate_confidence(home_p: float, away_p: float, draw_p: float, standings_rel: float, form_rel: float, h2h_rel: float) -> float:
    max_p = max(home_p, away_p, draw_p)
    decisiveness = (max_p - (1/3)) / (2/3)
    data_rel = (standings_rel + form_rel + h2h_rel)/3.0
    return max(0.1, min(0.95, decisiveness*0.7 + data_rel*0.3))

def advanced_prediction(fx_norm: Dict[str, Any], standings_rows: List[Dict[str, Any]], h2h: List[Dict[str, Any]], team_form: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    home = fx_norm["participants"][0]; away = fx_norm["participants"][1]
    home_id, away_id = home["id"], away["id"]

    def standing_for(team_id: int) -> Dict[str, Any]:
        for s in standings_rows:
            if int(s.get("team_id") or 0) == team_id:
                return s
        return {}

    hs, as_ = standing_for(home_id), standing_for(away_id)
    home_pos, away_pos = hs.get("position") or 10, as_.get("position") or 10
    home_pts, away_pts = hs.get("points") or 20, as_.get("points") or 20
    home_form = (team_form.get(home_id) or {}).get("formScore", 0.5)
    away_form = (team_form.get(away_id) or {}).get("formScore", 0.5)

    h2h_factor = calculate_h2h_factor(h2h, home_id)
    home_adv = 0.1

    home_p, away_p, draw_p = 0.4 + home_adv, 0.3, 0.3
    pos_diff = (int(away_pos) - int(home_pos)) / 20.0
    home_p += pos_diff * 0.2; away_p -= pos_diff * 0.2

    pts_diff = (float(home_pts) - float(away_pts)) / 50.0
    home_p += pts_diff * 0.15; away_p -= pts_diff * 0.15

    home_p += (home_form - 0.5) * 0.2
    away_p += (away_form - 0.5) * 0.2

    home_p += h2h_factor * 0.1
    away_p -= h2h_factor * 0.1

    total = home_p + away_p + draw_p
    if total <= 0: home_p = away_p = draw_p = 1/3
    else: home_p, away_p, draw_p = home_p/total, away_p/total, draw_p/total

    home_xg = max(0.5, 1.5 + (home_form - away_form) * 2)
    away_xg = max(0.5, 1.2 + (away_form - home_form) * 2)
    total_xg = home_xg + away_xg
    over25 = 0.6 + (total_xg - 2.5) * 0.15 if total_xg > 2.5 else 0.4 - (2.5 - total_xg) * 0.15
    over25 = max(0.0, min(1.0, over25))
    btts = max(0.1, min(0.9, (home_xg * away_xg) / 4.0))

    conf = calculate_confidence(home_p, away_p, draw_p, 0.8 if standings_rows else 0.3, 0.7 if team_form else 0.2, 0.6 if h2h else 0.1)

    return {
        "match_winner": {"home": round(home_p*100), "draw": round(draw_p*100), "away": round(away_p*100)},
        "over_under_25": {"over": round(over25*100), "under": round((1-over25)*100)},
        "both_teams_score": {"yes": round(btts*100), "no": round((1-btts)*100)},
        "expected_goals": {"home": f"{home_xg:.1f}", "away": f"{away_xg:.1f}", "total": f"{(home_xg+away_xg):.1f}"},
        "confidence": round(conf*100),
    }

def calculate_value_bets(fixtures_with_preds: List[Dict[str, Any]], edge_min: float = EDGE_THRESHOLD) -> List[Dict[str, Any]]:
    out = []
    for match in fixtures_with_preds:
        odds = match.get("odds") or {}
        pred = match.get("prediction") or {}
        if not pred:
            match["valueBets"] = []; continue

        value_bets = []

        # 1) Match winner 1X2
        mw = odds.get("match_winner") or {}
        if all(mw.get(k) for k in ("home", "draw", "away")):
            home_imp, draw_imp, away_imp = 1/float(mw["home"]), 1/float(mw["draw"]), 1/float(mw["away"])
            home_pred = pred["match_winner"]["home"]/100.0
            draw_pred = pred["match_winner"]["draw"]/100.0
            away_pred = pred["match_winner"]["away"]/100.0
            em = 1.0 + (edge_min/100.0)
            if home_pred > home_imp*em:
                value_bets.append({"market":"Match Winner","selection":"Home Win","odds":mw["home"],
                                   "predictedProb":f"{home_pred*100:.1f}","impliedProb":f"{home_imp*100:.1f}",
                                   "edge":f"{(home_pred-home_imp)*100:.1f}"})
            if draw_pred > draw_imp*em:
                value_bets.append({"market":"Match Winner","selection":"Draw","odds":mw["draw"],
                                   "predictedProb":f"{draw_pred*100:.1f}","impliedProb":f"{draw_imp*100:.1f}",
                                   "edge":f"{(draw_pred-draw_imp)*100:.1f}"})
            if away_pred > away_imp*em:
                value_bets.append({"market":"Match Winner","selection":"Away Win","odds":mw["away"],
                                   "predictedProb":f"{away_pred*100:.1f}","impliedProb":f"{away_imp*100:.1f}",
                                   "edge":f"{(away_pred-away_imp)*100:.1f}"})

        # 2) Over/Under 2.5
        ou = odds.get("over_under_25") or {}
        if ou.get("over") and ou.get("under"):
            over_imp, under_imp = 1/float(ou["over"]), 1/float(ou["under"])
            over_pred = (pred["over_under_25"]["over"])/100.0
            under_pred = 1 - over_pred
            em = 1.0 + (edge_min/100.0)
            if over_pred > over_imp*em:
                value_bets.append({"market":"Over/Under 2.5","selection":"Over 2.5","odds":ou["over"],
                                   "predictedProb":f"{over_pred*100:.1f}","impliedProb":f"{over_imp*100:.1f}",
                                   "edge":f"{(over_pred-over_imp)*100:.1f}"})
            if under_pred > under_imp*em:
                value_bets.append({"market":"Over/Under 2.5","selection":"Under 2.5","odds":ou["under"],
                                   "predictedProb":f"{under_pred*100:.1f}","impliedProb":f"{under_imp*100:.1f}",
                                   "edge":f"{(under_pred-under_imp)*100:.1f}"})

        # 3) BTTS
        btts = odds.get("both_teams_score") or {}
        if btts.get("yes") and btts.get("no"):
            yes_imp, no_imp = 1/float(btts["yes"]), 1/float(btts["no"])
            yes_pred = (pred["both_teams_score"]["yes"])/100.0
            no_pred = 1 - yes_pred
            em = 1.0 + (edge_min/100.0)
            if yes_pred > yes_imp*em:
                value_bets.append({"market":"BTTS","selection":"Yes","odds":btts["yes"],
                                   "predictedProb":f"{yes_pred*100:.1f}","impliedProb":f"{yes_imp*100:.1f}",
                                   "edge":f"{(yes_pred-yes_imp)*100:.1f}"})
            if no_pred > no_imp*em:
                value_bets.append({"market":"BTTS","selection":"No","odds":btts["no"],
                                   "predictedProb":f"{no_pred*100:.1f}","impliedProb":f"{no_imp*100:.1f}",
                                   "edge":f"{(no_pred-no_imp)*100:.1f}"})

        match["valueBets"] = value_bets
        out.extend([dict(vb, fixture=match) for vb in value_bets])

    log.info("Value bets found: %d (threshold=%s%%)", len(out), edge_min)
    return out

# =========================
# Normalization
# =========================
def normalize_fixture(fx: Dict[str, Any]) -> Dict[str, Any]:
    fid = (fx.get("fixture") or {}).get("id")
    when = (fx.get("fixture") or {}).get("date")
    venue = ((fx.get("fixture") or {}).get("venue") or {}).get("name")
    league = fx.get("league") or {}
    teams = fx.get("teams") or {}
    th, ta = (teams.get("home") or {}), (teams.get("away") or {})
    league_obj = {"id": league.get("id"), "name": league.get("name"), "season": league.get("season")}
    participants = [{"id": th.get("id"), "name": th.get("name")}, {"id": ta.get("id"), "name": ta.get("name")}]
    return {"id": fid, "starting_at": when, "venue": {"name": venue}, "league": league_obj, "participants": participants}

# =========================
# Pipeline
# =========================
def run_pipeline_for_date(d: str) -> Dict[str, Any]:
    log.info("=== Pipeline start for %s ===", d)
    fixtures_raw = get_fixtures_by_date(d)
    if not fixtures_raw:
        STATE["predictions"][d] = []; STATE["value_bets"][d] = []; STATE["last_run"] = utc_now_iso()
        log.warning("No fixtures for %s", d)
        return {"count": 0, "value_bets": 0}

    standings_cache: Dict[str, List[Dict[str, Any]]] = {}
    def standings_for(league_id: int, season: int) -> List[Dict[str, Any]]:
        key = f"{league_id}:{season}"
        if key not in standings_cache:
            standings_cache[key] = get_standings(league_id, season)
        return standings_cache[key]

    # Team form window (past 180 days)
    start = (date.fromisoformat(d) - timedelta(days=180)).isoformat()
    end = d

    # Collect unique team IDs + season hint
    team_ids: List[int] = []
    team_season_hint: Dict[int, int] = {}
    for fx in fixtures_raw:
        league = fx.get("league") or {}
        season_hint = league.get("season")
        teams = fx.get("teams") or {}
        for t in [teams.get("home") or {}, teams.get("away") or {}]:
            tid = t.get("id")
            if tid:
                team_ids.append(tid)
                if season_hint and tid not in team_season_hint:
                    team_season_hint[tid] = season_hint
    team_ids = sorted(list(set(team_ids)))
    log.info("Unique team IDs: %d", len(team_ids))

    # Compute team form
    team_form: Dict[int, Dict[str, Any]] = {}
    for tid in team_ids:
        team_form[tid] = get_team_form(tid, start, end, season_hint=team_season_hint.get(tid))

    # For each fixture: normalize, fetch H2H, standings, odds, predict
    results: List[Dict[str, Any]] = []
    for fx in fixtures_raw:
        fxn = normalize_fixture(fx)
        parts = fxn.get("participants") or []
        if len(parts) < 2 or not parts[0]["id"] or not parts[1]["id"]:
            log.info("Skipping fixture (bad participants): %s", fxn.get("id")); continue
        league = fxn.get("league") or {}
        league_id, season = league.get("id"), league.get("season")
        standings_rows = standings_for(league_id, season) if (league_id and season) else []

        # H2H
        try:
            h2h = get_head_to_head(parts[0]["id"], parts[1]["id"], last=5)
        except Exception as e:
            log.warning("H2H error %s vs %s: %s", parts[0]["id"], parts[1]["id"], e)
            h2h = []

        # Prediction
        pred = advanced_prediction(fxn, standings_rows, h2h, team_form)
        fxn["prediction"] = pred

        # Odds for multiple markets
        try:
            fxn["odds"] = get_odds_for_fixture(fxn["id"])
        except Exception as e:
            log.warning("Odds error for fixture %s: %s", fxn["id"], e)
            fxn["odds"] = {}

        results.append(fxn)

    # Value bets across markets
    value_bets = calculate_value_bets(results, EDGE_THRESHOLD)

    # Sort & persist
    results.sort(key=lambda r: r["prediction"]["confidence"], reverse=True)
    value_bets.sort(key=lambda v: float(v["edge"]), reverse=True)

    STATE["predictions"][d] = results
    STATE["value_bets"][d] = value_bets
    STATE["last_run"] = utc_now_iso()

    log.info("=== Pipeline done %s: fixtures=%d predictions=%d value_bets=%d ===",
             d, len(fixtures_raw), len(results), len(value_bets))
    return {"count": len(results), "value_bets": len(value_bets)}

# =========================
# Telegram
# =========================
def send_telegram(text: str):
    if not SEND_TELEGRAM:
        log.info("Telegram disabled; skipping"); return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": text}, timeout=15)
        log.info("Telegram sent")
    except Exception as e:
        log.error("Telegram send error: %s", e)

def notify_top_value_bets(d: str, top_n: int = 3):
    vbs = STATE["value_bets"].get(d, [])[:top_n]
    if not vbs:
        send_telegram(f"[{d}] No value bets found (edge ≥ {EDGE_THRESHOLD}%)."); return
    lines = [f"[{d}] Top Value Bets (edge ≥ {EDGE_THRESHOLD}%):"]
    for vb in vbs:
        fx = vb["fixture"]
        home = fx["participants"][0]["name"]; away = fx["participants"][1]["name"]
        when = fx.get("starting_at"); edge = vb["edge"]
        lines.append(f"• {home} vs {away} @ {when} — {vb['market']} / {vb['selection']} — odds {vb['odds']} (edge +{edge}%)")
    send_telegram("\n".join(lines))

# =========================
# Schedulers (daily + optional in-play)
# =========================
def scheduler_loop_daily():
    while True:
        try:
            d = date.today().isoformat()
            stats = run_pipeline_for_date(d)
            notify_top_value_bets(d, top_n=3)
            log.info("Daily run complete: %s", stats)
        except Exception as e:
            msg = f"scheduler error (daily): {e}"
            log.exception(msg); record_error(msg)
        time.sleep(EVERY_MINUTES * 60)

def scheduler_loop_inplay():
    if INPLAY_MINUTES <= 0:
        log.info("In-play scanner disabled"); return
    while True:
        try:
            # Simple presence check: /fixtures?live=all (we only use it for logging)
            data = apis_get("fixtures", {"live": "all"})
            cnt = len(data.get("response", []) or [])
            log.info("In-play scan: live fixtures=%s", cnt)
            # You could extend to pull odds for live fixtures and push alerts if edge>threshold
        except Exception as e:
            msg = f"scheduler error (in-play): {e}"
            log.exception(msg); record_error(msg)
        time.sleep(INPLAY_MINUTES * 60)

# =========================
# Flask app & routes
# =========================
app = Flask(__name__)

@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "last_run": STATE["last_run"], "errors": STATE["errors"][-5:]})

@app.route("/refresh", methods=["POST", "GET"])
def refresh():
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

# NEW: CSV export of value bets
@app.route("/export/value-bets.csv")
def export_value_bets_csv():
    d = request.args.get("date") or date.today().isoformat()
    rows = STATE["value_bets"].get(d, [])
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["date","league","home","away","start","market","selection","odds","edge","model_prob","implied_prob"])
    for vb in rows:
        fx = vb.get("fixture", {})
        home = (fx.get("participants") or [{}])[0].get("name", "")
        away = (fx.get("participants") or [{}, {}])[1].get("name", "")
        league = (fx.get("league") or {}).get("name", "")
        w.writerow([
            d, league, home, away, fx.get("starting_at",""),
            vb.get("market",""), vb.get("selection",""), vb.get("odds",""),
            vb.get("edge",""), vb.get("predictedProb",""), vb.get("impliedProb","")
        ])
    output.seek(0)
    return Response(output.read(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="value-bets-{d}.csv"'})

# --- Minimal HTML dashboard (unchanged) ---
INDEX_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>API-FOOTBALL Betting Bot</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0}
 header{padding:24px;text-align:center;background:linear-gradient(90deg,#2563eb,#7c3aed)} h1{margin:0;font-size:28px}
 .wrap{max-width:1100px;margin:20px auto;padding:0 16px} .card{background:#111827;border:1px solid #374151;border-radius:12px;padding:16px;margin-bottom:16px}
 .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
 input,button,select{background:#1f2937;color:#e5e7eb;border:1px solid #374151;border-radius:8px;padding:10px} button{cursor:pointer}
 table{width:100%;border-collapse:collapse} th,td{border-bottom:1px solid #374151;padding:8px;text-align:left;font-size:14px}
 .pill{padding:2px 8px;border-radius:999px;font-size:12px} .pill.green{background:#065f46;color:#a7f3d0} .pill.yellow{background:#78350f;color:#fde68a} .pill.red{background:#7f1d1d;color:#fecaca}
 .muted{color:#9ca3af} .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px} @media (max-width:900px){.grid{grid-template-columns:1fr}}
</style></head>
<body>
<header><h1>API-FOOTBALL Betting Bot</h1><div class="muted">Predictions • Value Bets • Health</div></header>
<div class="wrap">
 <div class="card">
  <div class="row">
   <div><label class="muted">Date</label><br/><input type="date" id="dateInput"/></div>
   <div><label class="muted">Auto-refresh (mins)</label><br/>
     <select id="autoSel"><option value="0">Off</option><option value="2">2</option><option value="5">5</option><option value="10">10</option></select>
   </div>
   <div style="margin-top:22px"><button id="runBtn">Run now</button> <button id="reloadBtn">Reload Tables</button> <a href="#" id="csvBtn">Download CSV</a></div>
   <div class="muted" id="status" style="margin-left:auto"></div>
  </div>
 </div>

 <div class="grid">
  <div class="card"><h3>Predictions</h3><div class="muted" id="predMeta"></div>
   <div style="overflow:auto;max-height:60vh">
    <table id="predTable">
     <thead><tr><th>Match</th><th>League</th><th>Start</th><th>Home%</th><th>Draw%</th><th>Away%</th><th>O/U 2.5</th><th>BTTS</th><th>Conf</th></tr></thead>
     <tbody></tbody>
    </table>
   </div>
  </div>

  <div class="card"><h3>Value Bets</h3><div class="muted" id="vbMeta"></div>
   <div style="overflow:auto;max-height:60vh">
    <table id="vbTable">
     <thead><tr><th>Match</th><th>Market</th><th>Pick</th><th>Odds</th><th>Model%</th><th>Implied%</th><th>Edge</th></tr></thead>
     <tbody></tbody>
    </table>
   </div>
  </div>
 </div>

 <div class="card"><h3>Health</h3><pre id="health" class="muted" style="white-space:pre-wrap"></pre></div>
</div>

<script>
const $ = (s)=>document.querySelector(s); const today = new Date().toISOString().split('T')[0]; $("#dateInput").value = today;
let timer=null; $("#autoSel").addEventListener("change",()=>{ if(timer) clearInterval(timer); const m=parseInt($("#autoSel").value||"0",10); if(m>0) timer=setInterval(loadAll,m*60*1000); });
$("#runBtn").addEventListener("click",async()=>{ const d=$("#dateInput").value||today; $("#status").textContent="Running…"; await fetch(`/refresh?date=${d}`); $("#status").textContent="Done"; loadAll(); });
$("#reloadBtn").addEventListener("click", loadAll);
$("#csvBtn").addEventListener("click", ()=>{ const d=$("#dateInput").value||today; window.location = `/export/value-bets.csv?date=${d}`; });

function fmt(n){ return n==null?'':(typeof n==='number'?n.toFixed(0):n); }
async function loadPredictions(){
  const d=$("#dateInput").value||today; const r=await fetch(`/predictions?date=${d}`); const j=await r.json();
  $("#predMeta").textContent = `${j.count} matches | last run ${j.last_run||'-'}`;
  const tb=$("#predTable tbody"); tb.innerHTML="";
  (j.items||[]).forEach(fx=>{
    const p=fx.prediction||{};
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${fx.participants?.[0]?.name||'?'} vs ${fx.participants?.[1]?.name||'?'}</td>
      <td>${fx.league?.name||''}</td>
      <td><span class="muted">${(fx.starting_at||'').replace('T',' ').replace('Z','')}</span></td>
      <td>${fmt(p.match_winner?.home)}</td>
      <td>${fmt(p.match_winner?.draw)}</td>
      <td>${fmt(p.match_winner?.away)}</td>
      <td>${fmt(p.over_under_25?.over)}/${fmt(p.over_under_25?.under)}</td>
      <td>${fmt(p.both_teams_score?.yes)}/${fmt(p.both_teams_score?.no)}</td>
      <td><span class="pill ${(p.confidence||0)>=70?'green':(p.confidence||0)>=50?'yellow':'red'}">${fmt(p.confidence)}%</span></td>`;
    tb.appendChild(tr);
  });
}
async function loadValueBets(){
  const d=$("#dateInput").value||today; const r=await fetch(`/value-bets?date=${d}`); const j=await r.json();
  $("#vbMeta").textContent = `${j.count} opportunities | threshold ${j.edge_threshold}% | last run ${j.last_run||'-'}`;
  const tb=$("#vbTable tbody"); tb.innerHTML="";
  (j.items||[]).forEach(vb=>{
    const fx=vb.fixture||{};
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td>${fx.participants?.[0]?.name||'?'} vs ${fx.participants?.[1]?.name||'?'}</td>
      <td>${vb.market}</td>
      <td>${vb.selection}</td>
      <td>${vb.odds}</td>
      <td>${vb.predictedProb}%</td>
      <td>${vb.impliedProb}%</td>
      <td><b>${vb.edge}%</b></td>`;
    tb.appendChild(tr);
  });
}
async function loadHealth(){ const r=await fetch('/healthz'); const j=await r.json(); $("#health").textContent=JSON.stringify(j,null,2); }
async function loadAll(){ await Promise.all([loadPredictions(), loadValueBets(), loadHealth()]); }
loadAll();
</script>
</body></html>
"""

@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

# =========================
# Main
# =========================
if __name__ == "__main__":
    threading.Thread(target=scheduler_loop_daily, daemon=True).start()
    threading.Thread(target=scheduler_loop_inplay, daemon=True).start()
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)