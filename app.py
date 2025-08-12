# app.py
import os
import sys
import time
import threading
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, jsonify, request, Response
from dateutil import tz

# =========================
# Config (env overrides supported)
# =========================
APP_TZ = os.getenv("APP_TIMEZONE", "Europe/London")
BASE_URL = "https://api.sportmonks.com/v3"
SPORTMONKS_TOKEN = (os.getenv("SPORTMONKS_API_TOKEN") or "").strip()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_TOKEN and CHAT_ID)

EVERY_MINUTES = int(os.getenv("EVERY_MINUTES", "60"))  # scheduler frequency
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "5"))  # % edge for value bet

# Optional league whitelist: comma-separated IDs, or blank for all
LEAGUE_WHITELIST = {
    x.strip() for x in os.getenv("LEAGUE_WHITELIST", "").split(",") if x.strip()
}

# Include sets (override with env if needed)
INCLUDES_FIXTURE = os.getenv(
    "SM_INCLUDES_FIXTURE",
    "participants,scores,state,league,venue,weatherreport,events,statistics.type,lineups.player,odds",
)
INCLUDES_LIVE = os.getenv(
    "SM_INCLUDES_LIVE",
    "participants,scores,state,league,events,statistics.type,odds",
)

# In-memory state
STATE: Dict[str, Any] = {
    "last_run": None,
    "predictions": {},   # date -> list of fixture+prediction
    "value_bets": {},    # date -> list of value bets (with fixture attached)
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
log.info(
    "Booting… tz=%s edge_threshold=%s every_minutes=%s token=%s",
    APP_TZ, EDGE_THRESHOLD, EVERY_MINUTES, "SET" if SPORTMONKS_TOKEN else "MISSING"
)

def utc_now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=tz.UTC).isoformat()

def record_error(msg: str):
    STATE["errors"].append({"t": utc_now_iso(), "msg": msg})

# =========================
# HTTP helper
# =========================
def sportmonks_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET wrapper with token injection + logging."""
    if not SPORTMONKS_TOKEN:
        msg = "SportMonks token missing — returning empty data"
        log.warning(msg)
        record_error(msg)
        return {"data": []}

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    q = dict(params or {})
    q["api_token"] = SPORTMONKS_TOKEN

    try:
        # hide token in logs
        log.info("GET %s params=%s", url, {k: v for k, v in q.items() if k != "api_token"})
        r = requests.get(url, params=q, timeout=45)
        log.info("↳ status=%s", r.status_code)
        if r.status_code != 200:
            log.error("Body: %s", r.text[:600])
        r.raise_for_status()
        data = r.json()
        size = len(data.get("data", [])) if isinstance(data, dict) else 0
        log.info("↳ items=%s", size)
        return data
    except Exception as e:
        msg = f"HTTP error GET {endpoint}: {e}"
        log.exception(msg)
        record_error(msg)
        return {"data": []}

# =========================
# Fetchers (with pagination + enrichment)
# =========================
def get_fixtures_by_date(d: str, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    params = {"include": INCLUDES_FIXTURE, "per_page": 100, "page": 1}
    if league_id:
        params["filter[league_id]"] = league_id

    fixtures: List[Dict[str, Any]] = []
    while True:
        data = sportmonks_get(f"football/fixtures/date/{d}", params)
        chunk = data.get("data", []) or []
        meta = data.get("meta", {}) or {}
        fixtures.extend(chunk)

        # Log what keys actually appeared (helps verify includes/plan)
        keyset = set()
        for fx in chunk:
            keyset.update(fx.keys())
        interesting = {"participants","scores","state","league","venue","weatherreport","events","statistics","lineups","odds"}
        present = ", ".join(sorted(keyset & interesting)) if chunk else "-"
        log.info(
            "Pagination page=%s got=%s keys_present=[%s] total=%s",
            params["page"], len(chunk), present, meta.get("total", "?")
        )

        # stop?
        if not chunk or (meta.get("current_page") == meta.get("last_page")):
            break
        params["page"] = params.get("page", 1) + 1

    log.info("Fixtures on %s (all pages): %d", d, len(fixtures))
    return fixtures

def get_season_for_league(league_id: str) -> Optional[str]:
    data = sportmonks_get("football/seasons", {"filter[league_id]": league_id, "per_page": 1})
    seasons = data.get("data", [])
    sid = str(seasons[0]["id"]) if seasons else None
    log.info("League %s -> season %s", league_id, sid)
    return sid

def get_standings_for_season(season_id: str) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/standings/seasons/{season_id}", {"include": "participant"})
    blocks = data.get("data", [])
    standings = blocks[0].get("standings", []) if blocks else []
    log.info("Standings rows for season %s: %d", season_id, len(standings))
    return standings

def get_standings_map(fixtures: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Cache standings per league for the date (multi-league days)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    league_ids = sorted({str((fx.get("league") or {}).get("id", "")) for fx in fixtures if fx.get("league")})
    for lid in league_ids:
        if not lid:
            continue
        sid = get_season_for_league(lid)
        if not sid:
            out[lid] = []
            continue
        out[lid] = get_standings_for_season(sid)
    return out

def get_team_recent_form(team_id: int, start: str, end: str, limit: int = 5) -> Dict[str, Any]:
    data = sportmonks_get(
        f"football/fixtures/between/{start}/{end}/{team_id}",
        {"include": "participants,scores", "per_page": limit}
    )
    fixtures = data.get("data", [])
    wins = draws = losses = 0
    for fx in fixtures:
        team_score = opp_score = 0
        for s in fx.get("scores", []):
            total = (s.get("score") or {}).get("total", 0)
            if s.get("participant_id") == team_id:
                team_score = total
            else:
                opp_score = total
        if team_score > opp_score: wins += 1
        elif team_score == opp_score: draws += 1
        else: losses += 1
    total_games = wins + draws + losses
    form_score = (wins*3 + draws)/(total_games*3) if total_games > 0 else 0.5
    out = {
        "wins": wins, "draws": draws, "losses": losses,
        "formScore": form_score, "form": f"{wins}W-{draws}D-{losses}L"
    }
    log.info("Form team=%s -> %s", team_id, out)
    return out

def get_head_to_head(team_a: int, team_b: int) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/fixtures/head-to-head/{team_a}/{team_b}", {"include": "participants,scores"})
    return data.get("data", [])

def enrich_fixture_if_needed(fx: Dict[str, Any]) -> Dict[str, Any]:
    """Try to fetch missing pieces (e.g., odds/events/statistics)."""
    need_odds = not fx.get("odds")
    need_events = not fx.get("events")
    need_stats = not fx.get("statistics")
    if not (need_odds or need_events or need_stats):
        return fx

    inc = []
    if need_odds: inc.append("odds")
    if need_events: inc.append("events")
    if need_stats: inc.append("statistics.type")
    include_str = ",".join(inc)
    fid = fx.get("id")
    if not fid:
        return fx

    log.info("Enriching fixture %s include=%s", fid, include_str)
    data = sportmonks_get(f"football/fixtures/{fid}", {"include": include_str})
    enriched = (data.get("data") or {}) if isinstance(data, dict) else {}
    for k in ["odds", "events", "statistics"]:
        if not fx.get(k) and enriched.get(k) is not None:
            fx[k] = enriched[k]
    return fx

# =========================
# Prediction math
# =========================
def calculate_h2h_factor(h2h_fixtures: List[Dict[str, Any]], home_team_id: int) -> float:
    if not h2h_fixtures: return 0.0
    recent = h2h_fixtures[-5:]
    home_wins = 0
    for fx in recent:
        home_score = away_score = 0
        for s in fx.get("scores", []):
            total = (s.get("score") or {}).get("total", 0)
            if s.get("participant_id") == home_team_id: home_score = total
            else: away_score = total
        if home_score > away_score: home_wins += 1
    return (home_wins/len(recent)) - 0.5 if recent else 0.0

def calculate_weather_impact(weather: Optional[Dict[str, Any]]) -> float:
    if not weather: return 1.0
    factor = 1.0
    t = weather.get("temperature_celsius")
    if t is not None and (t < 5 or t > 35): factor *= 0.95
    w = weather.get("wind_speed")
    if w is not None and w > 20: factor *= 0.9
    desc = (weather.get("weather_report") or {}).get("description", "")
    if isinstance(desc, str) and "rain" in desc.lower(): factor *= 0.85
    return factor

def calculate_confidence(home_p: float, away_p: float, draw_p: float,
                         standings_rel: float, form_rel: float, h2h_rel: float) -> float:
    max_p = max(home_p, away_p, draw_p)
    decisiveness = (max_p - (1/3)) / (2/3)
    data_rel = (standings_rel + form_rel + h2h_rel)/3.0
    return max(0.1, min(0.95, decisiveness*0.7 + data_rel*0.3))

def advanced_prediction(fixture: Dict[str, Any],
                        standings: List[Dict[str, Any]],
                        head_to_head: List[Dict[str, Any]],
                        team_form: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    parts = fixture.get("participants") or []
    if len(parts) < 2: return {}
    home, away = parts[0], parts[1]
    home_id, away_id = int(home.get("id")), int(away.get("id"))

    def standing_for(team_id: int) -> Dict[str, Any]:
        for s in standings:
            if int(s.get("participant_id")) == team_id: return s
        return {}

    hs, as_ = standing_for(home_id), standing_for(away_id)
    home_pos, away_pos = hs.get("position") or 10, as_.get("position") or 10
    home_pts, away_pts = hs.get("points") or 20, as_.get("points") or 20
    home_form = (team_form.get(home_id) or {}).get("formScore", 0.5)
    away_form = (team_form.get(away_id) or {}).get("formScore", 0.5)

    h2h = calculate_h2h_factor(head_to_head, home_id)
    weather = calculate_weather_impact(fixture.get("weatherreport"))
    home_adv = 0.1

    home_p, away_p, draw_p = 0.4 + home_adv, 0.3, 0.3
    pos_diff = (int(away_pos) - int(home_pos)) / 20.0
    home_p += pos_diff * 0.2; away_p -= pos_diff * 0.2
    pts_diff = (float(home_pts) - float(away_pts)) / 50.0
    home_p += pts_diff * 0.15; away_p -= pts_diff * 0.15
    home_p += (home_form - 0.5) * 0.2
    away_p += (away_form - 0.5) * 0.2
    home_p += h2h * 0.1; away_p -= h2h * 0.1
    home_p *= weather

    total = home_p + away_p + draw_p
    if total <= 0:
        home_p = away_p = draw_p = 1/3
    else:
        home_p, away_p, draw_p = home_p/total, away_p/total, draw_p/total

    home_xg = max(0.5, 1.5 + (home_form - away_form) * 2)
    away_xg = max(0.5, 1.2 + (away_form - home_form) * 2)
    total_xg = home_xg + away_xg
    over25 = 0.6 + (total_xg - 2.5) * 0.15 if total_xg > 2.5 else 0.4 - (2.5 - total_xg) * 0.15
    over25 = max(0.0, min(1.0, over25))
    btts = max(0.1, min(0.9, (home_xg * away_xg) / 4.0))

    conf = calculate_confidence(
        home_p, away_p, draw_p,
        0.8 if standings else 0.3,
        0.7 if team_form else 0.2,
        0.6 if head_to_head else 0.1
    )

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
        if not odds or not pred:
            match["valueBets"] = []
            continue

        value_bets = []
        mw = odds.get("match_winner")
        if mw:
            home_odds, draw_odds, away_odds = mw.get("home"), mw.get("draw"), mw.get("away")
            if all([home_odds, draw_odds, away_odds]):
                home_imp, draw_imp, away_imp = 1/float(home_odds), 1/float(draw_odds), 1/float(away_odds)
                home_pred = pred["match_winner"]["home"]/100.0
                draw_pred = pred["match_winner"]["draw"]/100.0
                away_pred = pred["match_winner"]["away"]/100.0
                em = 1.0 + (edge_min/100.0)
                if home_pred > home_imp*em:
                    value_bets.append({"market":"Match Winner","selection":"Home Win","odds":home_odds,
                                       "predictedProb":f"{home_pred*100:.1f}","impliedProb":f"{home_imp*100:.1f}",
                                       "edge":f"{(home_pred-home_imp)*100:.1f}"})
                if draw_pred > draw_imp*em:
                    value_bets.append({"market":"Match Winner","selection":"Draw","odds":draw_odds,
                                       "predictedProb":f"{draw_pred*100:.1f}","impliedProb":f"{draw_imp*100:.1f}",
                                       "edge":f"{(draw_pred-draw_imp)*100:.1f}"})
                if away_pred > away_imp*em:
                    value_bets.append({"market":"Match Winner","selection":"Away Win","odds":away_odds,
                                       "predictedProb":f"{away_pred*100:.1f}","impliedProb":f"{away_imp*100:.1f}",
                                       "edge":f"{(away_pred-away_imp)*100:.1f}"})
        match["valueBets"] = value_bets
        out.extend([dict(vb, fixture=match) for vb in value_bets])
    log.info("Value bets found: %d (threshold=%s%%)", len(out), edge_min)
    return out

# =========================
# Pipeline
# =========================
def run_pipeline_for_date(d: str) -> Dict[str, Any]:
    log.info("=== Pipeline start for %s ===", d)
    fixtures = get_fixtures_by_date(d)

    if LEAGUE_WHITELIST:
        before = len(fixtures)
        fixtures = [f for f in fixtures if str((f.get("league") or {}).get("id", "")) in LEAGUE_WHITELIST]
        log.info("Whitelist filtered fixtures: %d -> %d", before, len(fixtures))

    if not fixtures:
        msg = f"No fixtures returned for {d}. Check token/plan/date."
        log.warning(msg)
        STATE["predictions"][d] = []
        STATE["value_bets"][d] = []
        STATE["last_run"] = utc_now_iso()
        return {"count": 0, "value_bets": 0}

    # Collect team IDs
    team_ids: List[int] = []
    for fx in fixtures:
        for p in fx.get("participants") or []:
            if "id" in p:
                team_ids.append(int(p["id"]))
    team_ids = sorted(list(set(team_ids)))
    log.info("Unique team IDs: %d", len(team_ids))

    # Standings per league (multi-league aware)
    standings_by_league = get_standings_map(fixtures)

    # Team form (past 180 days)
    start = (date.fromisoformat(d) - timedelta(days=180)).isoformat()
    end = d
    team_form: Dict[int, Dict[str, Any]] = {}
    for tid in team_ids:
        team_form[tid] = get_team_recent_form(tid, start, end, limit=5)

    # Predictions
    results: List[Dict[str, Any]] = []
    for fx in fixtures:
        parts = fx.get("participants") or []
        if len(parts) < 2:
            log.info("Skipping fixture %s (no participants)", fx.get("id"))
            continue
        teamA, teamB = int(parts[0]["id"]), int(parts[1]["id"])
        league_id = str((fx.get("league") or {}).get("id", "")) or ""
        standings_all = standings_by_league.get(league_id, [])
        try:
            h2h = get_head_to_head(teamA, teamB)
        except Exception as e:
            log.warning("H2H error for %s vs %s: %s", teamA, teamB, e)
            h2h = []
        pred = advanced_prediction(fx, standings_all, h2h, team_form)
        if not pred:
            log.info("No prediction produced for fixture %s", fx.get("id"))
            continue
        out_fx = dict(fx)
        out_fx["prediction"] = pred
        out_fx = enrich_fixture_if_needed(out_fx)
        results.append(out_fx)

    # Value bets
    value_bets = calculate_value_bets(results, EDGE_THRESHOLD)

    # Sort & persist
    results.sort(key=lambda r: r["prediction"]["confidence"], reverse=True)
    value_bets.sort(key=lambda v: float(v["edge"]), reverse=True)

    STATE["predictions"][d] = results
    STATE["value_bets"][d] = value_bets
    STATE["last_run"] = utc_now_iso()

    log.info(
        "=== Pipeline done for %s: fixtures=%d predictions=%d value_bets=%d ===",
        d, len(fixtures), len(results), len(value_bets)
    )
    return {"count": len(results), "value_bets": len(value_bets)}

# =========================
# Telegram
# =========================
def send_telegram(text: str):
    if not SEND_TELEGRAM:
        log.info("Telegram disabled; skipping message")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)
        log.info("Telegram sent")
    except Exception as e:
        log.error("Telegram send error: %s", e)

def notify_top_value_bets(d: str, top_n: int = 3):
    vbs = STATE["value_bets"].get(d, [])[:top_n]
    if not vbs:
        send_telegram(f"[{d}] No value bets found (edge ≥ {EDGE_THRESHOLD}%).")
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

# =========================
# Scheduler
# =========================
def scheduler_loop():
    while True:
        try:
            d = date.today().isoformat()
            stats = run_pipeline_for_date(d)
            notify_top_value_bets(d, top_n=3)
            log.info("Scheduler run complete: %s", stats)
        except Exception as e:
            msg = f"scheduler error: {e}"
            log.exception(msg)
            record_error(msg)
        time.sleep(EVERY_MINUTES * 60)

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

# --- Minimal HTML dashboard (served at /) ---
INDEX_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SportMonks Betting Bot</title>
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
<header><h1>SportMonks Betting Bot</h1><div class="muted">Predictions • Value Bets • Health</div></header>
<div class="wrap">
 <div class="card">
  <div class="row">
   <div><label class="muted">Date</label><br/><input type="date" id="dateInput"/></div>
   <div><label class="muted">Auto-refresh (mins)</label><br/>
     <select id="autoSel"><option value="0">Off</option><option value="2">2</option><option value="5">5</option><option value="10">10</option></select>
   </div>
   <div style="margin-top:22px"><button id="runBtn">Run now</button> <button id="reloadBtn">Reload Tables</button></div>
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
    threading.Thread(target=scheduler_loop, daemon=True).start()
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)