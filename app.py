import os
import time
import threading
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, jsonify, request, Response
from dateutil import tz

# -----------------------------
# Config & Globals
# -----------------------------
APP_TZ = os.getenv("APP_TIMEZONE", "Europe/London")
BASE_URL = "https://api.sportmonks.com/v3"
RAW_TOKEN = os.getenv("SPORTMONKS_API_TOKEN", "")
SPORTMONKS_TOKEN = RAW_TOKEN.strip().replace("\n", "").replace("\r", "").replace("=", "")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
SEND_TELEGRAM = bool(TELEGRAM_TOKEN and CHAT_ID)

EVERY_MINUTES = int(os.getenv("EVERY_MINUTES", "60"))
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "5"))
LEAGUE_WHITELIST = {x.strip() for x in os.getenv("LEAGUE_WHITELIST", "").split(",") if x.strip()}

INCLUDES_FIXTURE = "participants,scores,state,league,venue,weatherreport,events,statistics.type,lineups.player,odds"
INCLUDES_LIVE = "participants,scores,state,league,events,statistics.type,odds"

STATE: Dict[str, Any] = {"last_run": None, "predictions": {}, "value_bets": {}, "errors": []}

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
    params = {"include": INCLUDES_FIXTURE, "per_page": 100}
    if league_id:
        params["filter[league_id]"] = league_id
    data = sportmonks_get(f"football/fixtures/date/{d}", params)
    return data.get("data", [])

def get_season_for_league(league_id: str) -> Optional[str]:
    data = sportmonks_get("football/seasons", {"filter[league_id]": league_id, "include": "league", "per_page": 1})
    seasons = data.get("data", [])
    return str(seasons[0]["id"]) if seasons else None

def get_standings_for_season(season_id: str) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/standings/seasons/{season_id}", {"include": "participant"})
    blocks = data.get("data", [])
    if not blocks: return []
    return blocks[0].get("standings", [])

def get_team_recent_form(team_id: int, start: str, end: str, limit: int = 5) -> Dict[str, Any]:
    data = sportmonks_get(f"football/fixtures/between/{start}/{end}/{team_id}", {"include": "participants,scores", "per_page": limit})
    fixtures = data.get("data", [])
    wins = draws = losses = 0
    for fx in fixtures:
        team_score = opp_score = 0
        for s in fx.get("scores", []):
            total = (s.get("score") or {}).get("total", 0)
            if s.get("participant_id") == team_id: team_score = total
            else: opp_score = total
        if team_score > opp_score: wins += 1
        elif team_score == opp_score: draws += 1
        else: losses += 1
    total_games = wins + draws + losses
    form_score = (wins*3 + draws)/(total_games*3) if total_games>0 else 0.5
    return {"wins": wins, "draws": draws, "losses": losses, "formScore": form_score, "form": f"{wins}W-{draws}D-{losses}L"}

def get_head_to_head(team_a: int, team_b: int) -> List[Dict[str, Any]]:
    data = sportmonks_get(f"football/fixtures/head-to-head/{team_a}/{team_b}", {"include": "participants,scores"})
    return data.get("data", [])

# -----------------------------
# Prediction math
# -----------------------------
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

def calculate_confidence(home_p: float, away_p: float, draw_p: float, standings_rel: float, form_rel: float, h2h_rel: float) -> float:
    max_p = max(home_p, away_p, draw_p)
    decisiveness = (max_p - (1/3)) / (2/3)
    data_rel = (standings_rel + form_rel + h2h_rel)/3.0
    return max(0.1, min(0.95, decisiveness*0.7 + data_rel*0.3))

def advanced_prediction(fixture: Dict[str, Any], standings: List[Dict[str, Any]], head_to_head: List[Dict[str, Any]], team_form: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
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
    if total <= 0: home_p = away_p = draw_p = 1/3
    else: home_p, away_p, draw_p = home_p/total, away_p/total, draw_p/total

    home_xg = max(0.5, 1.5 + (home_form - away_form) * 2)
    away_xg = max(0.5, 1.2 + (away_form - home_form) * 2)
    total_xg = home_xg + away_xg
    over25 = 0.6 + (total_xg - 2.5) * 0.15 if total_xg > 2.5 else 0.4 - (2.5 - total_xg) * 0.15
    over25 = max(0.0, min(1.0, over25))
    btts = max(0.1, min(0.9, (home_xg * away_xg) / 4.0))

    conf = calculate_confidence(home_p, away_p, draw_p, 0.8 if standings else 0.3, 0.7 if team_form else 0.2, 0.6 if head_to_head else 0.1)

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
    return out

# -----------------------------
# Pipeline
# -----------------------------
def run_pipeline_for_date(d: str) -> Dict[str, Any]:
    log.info(f"Running predictions for {d}")
    fixtures = get_fixtures_by_date(d)
    if LEAGUE_WHITELIST:
        fixtures = [f for f in fixtures if str((f.get("league") or {}).get("id", "")) in LEAGUE_WHITELIST]

    team_ids: List[int] = []
    for fx in fixtures:
        for p in fx.get("participants") or []:
            if "id" in p: team_ids.append(int(p["id"]))
    team_ids = sorted(list(set(team_ids)))

    standings_all: List[Dict[str, Any]] = []
    if fixtures:
        first_league_id = str((fixtures[0].get("league") or {}).get("id", ""))
        if first_league_id:
            season_id = get_season_for_league(first_league_id)
            if season_id:
                standings_all = get_standings_for_season(season_id)

    today = date.fromisoformat(d)
    start, end = (today - timedelta(days=180)).isoformat(), d
    team_form: Dict[int, Dict[str, Any]] = {tid: get_team_recent_form(tid, start, end, 5) for tid in team_ids}

    results: List[Dict[str, Any]] = []
    for fx in fixtures:
        parts = fx.get("participants") or []
        if len(parts) < 2: continue
        teamA, teamB = int(parts[0]["id"]), int(parts[1]["id"])
        try: h2h = get_head_to_head(teamA, teamB)
        except Exception: h2h = []
        pred = advanced_prediction(fx, standings_all, h2h, team_form)
        if not pred: continue
        out_fx = dict(fx); out_fx["prediction"] = pred
        results.append(out_fx)

    value_bets = calculate_value_bets(results, EDGE_THRESHOLD)
    results.sort(key=lambda r: r["prediction"]["confidence"], reverse=True)
    value_bets.sort(key=lambda v: float(v["edge"]), reverse=True)

    STATE["predictions"][d] = results
    STATE["value_bets"][d] = value_bets
    STATE["last_run"] = utc_now_iso()
    return {"count": len(results), "value_bets": len(value_bets)}

# -----------------------------
# Telegram
# -----------------------------
def send_telegram(text: str):
    if not SEND_TELEGRAM: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        log.error(f"Telegram send error: {e}")

def notify_top_value_bets(d: str, top_n: int = 3):
    if not SEND_TELEGRAM: return
    vbs = STATE["value_bets"].get(d, [])[:top_n]
    if not vbs:
        send_telegram(f"[{d}] No value bets found (edge >= {EDGE_THRESHOLD}%)."); return
    lines = [f"[{d}] Top Value Bets (edge ≥ {EDGE_THRESHOLD}%):"]
    for vb in vbs:
        fx = vb["fixture"]
        home = fx["participants"][0]["name"]; away = fx["participants"][1]["name"]
        when = fx.get("starting_at"); edge = vb["edge"]
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
            log.error(msg); STATE["errors"].append({"t": utc_now_iso(), "msg": msg})
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
    d = request.args.get("date") or date.today().isoformat()
    stats = run_pipeline_for_date(d)
    notify_top_value_bets(d, top_n=3)
    return jsonify({"ok": True, "date": d, "stats": stats})

@app.route("/predictions")
def predictions():
    d = request.args.get("date") or date.today().isoformat()
    return jsonify({"date": d, "count": len(STATE["predictions"].get(d, [])), "items": STATE["predictions"].get(d, []), "last_run": STATE["last_run"]})

@app.route("/value-bets")
def value_bets():
    d = request.args.get("date") or date.today().isoformat()
    return jsonify({"date": d, "count": len(STATE["value_bets"].get(d, [])), "items": STATE["value_bets"].get(d, []), "edge_threshold": EDGE_THRESHOLD, "last_run": STATE["last_run"]})

# ---------- NEW: minimal dashboard ----------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>SportMonks Betting Bot</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0}
    header{padding:24px;text-align:center;background:linear-gradient(90deg,#2563eb,#7c3aed)}
    h1{margin:0;font-size:28px}
    .wrap{max-width:1100px;margin:20px auto;padding:0 16px}
    .card{background:#111827;border:1px solid #374151;border-radius:12px;padding:16px;margin-bottom:16px}
    .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
    input,button,select{background:#1f2937;color:#e5e7eb;border:1px solid #374151;border-radius:8px;padding:10px}
    button{cursor:pointer}
    table{width:100%;border-collapse:collapse}
    th,td{border-bottom:1px solid #374151;padding:8px;text-align:left;font-size:14px}
    .pill{padding:2px 8px;border-radius:999px;font-size:12px}
    .pill.green{background:#065f46;color:#a7f3d0}
    .pill.yellow{background:#78350f;color:#fde68a}
    .pill.red{background:#7f1d1d;color:#fecaca}
    .muted{color:#9ca3af}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    @media (max-width:900px){.grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
  <header>
    <h1>SportMonks Betting Bot</h1>
    <div class="muted">Predictions • Value Bets • Live health</div>
  </header>

  <div class="wrap">
    <div class="card">
      <div class="row">
        <div>
          <label class="muted">Date</label><br/>
          <input type="date" id="dateInput"/>
        </div>
        <div>
          <label class="muted">Auto-refresh (mins)</label><br/>
          <select id="autoSel">
            <option value="0">Off</option>
            <option value="2">2</option>
            <option value="5">5</option>
            <option value="10">10</option>
          </select>
        </div>
        <div style="margin-top:22px">
          <button id="runBtn">Run now</button>
          <button id="reloadBtn">Reload Tables</button>
        </div>
        <div class="muted" id="status" style="margin-left:auto"></div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>Predictions</h3>
        <div class="muted" id="predMeta"></div>
        <div style="overflow:auto;max-height:60vh">
          <table id="predTable">
            <thead>
              <tr><th>Match</th><th>League</th><th>Start</th><th>Home%</th><th>Draw%</th><th>Away%</th><th>O/U 2.5</th><th>BTTS</th><th>Conf</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h3>Value Bets</h3>
        <div class="muted" id="vbMeta"></div>
        <div style="overflow:auto;max-height:60vh">
          <table id="vbTable">
            <thead>
              <tr><th>Match</th><th>Market</th><th>Pick</th><th>Odds</th><th>Model%</th><th>Implied%</th><th>Edge</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>Health</h3>
      <pre id="health" class="muted" style="white-space:pre-wrap"></pre>
    </div>
  </div>

<script>
const $ = (sel)=>document.querySelector(sel);
const fmt = (n)=> (n==null?'':(typeof n==='number'?n.toFixed(0):n));
const today = new Date().toISOString().split('T')[0];
$("#dateInput").value = today;

let timer = null;
$("#autoSel").addEventListener("change", ()=>{
  if (timer) clearInterval(timer);
  const mins = parseInt($("#autoSel").value || "0", 10);
  if (mins>0) timer = setInterval(loadAll, mins*60*1000);
});

$("#runBtn").addEventListener("click", async ()=>{
  const d = $("#dateInput").value || today;
  $("#status").textContent = "Running…";
  await fetch(`/refresh?date=${d}`);
  $("#status").textContent = "Done";
  loadAll();
});

$("#reloadBtn").addEventListener("click", loadAll);

async function loadPredictions() {
  const d = $("#dateInput").value || today;
  const r = await fetch(`/predictions?date=${d}`); const j = await r.json();
  $("#predMeta").textContent = `${j.count} matches | last run ${j.last_run||'-'}`;
  const tb = $("#predTable tbody"); tb.innerHTML = "";
  (j.items||[]).forEach(fx=>{
    const p = fx.prediction||{};
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${fx.participants?.[0]?.name||'?' } vs ${fx.participants?.[1]?.name||'?'}</td>
      <td>${fx.league?.name||''}</td>
      <td><span class="muted">${(fx.starting_at||'').replace('T',' ').replace('Z','')}</span></td>
      <td>${fmt(p.match_winner?.home)}</td>
      <td>${fmt(p.match_winner?.draw)}</td>
      <td>${fmt(p.match_winner?.away)}</td>
      <td>${fmt(p.over_under_25?.over)}/${fmt(p.over_under_25?.under)}</td>
      <td>${fmt(p.both_teams_score?.yes)}/${fmt(p.both_teams_score?.no)}</td>
      <td><span class="pill ${p.confidence>=70?'green':(p.confidence>=50?'yellow':'red')}">${fmt(p.confidence)}%</span></td>
    `;
    tb.appendChild(row);
  });
}

async function loadValueBets() {
  const d = $("#dateInput").value || today;
  const r = await fetch(`/value-bets?date=${d}`); const j = await r.json();
  $("#vbMeta").textContent = `${j.count} opportunities | threshold ${j.edge_threshold}% | last run ${j.last_run||'-'}`;
  const tb = $("#vbTable tbody"); tb.innerHTML = "";
  (j.items||[]).forEach(vb=>{
    const fx = vb.fixture||{};
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${fx.participants?.[0]?.name||'?'} vs ${fx.participants?.[1]?.name||'?'}</td>
      <td>${vb.market}</td>
      <td>${vb.selection}</td>
      <td>${vb.odds}</td>
      <td>${vb.predictedProb}%</td>
      <td>${vb.impliedProb}%</td>
      <td><b>${vb.edge}%</b></td>
    `;
    tb.appendChild(row);
  });
}

async function loadHealth() {
  const r = await fetch('/healthz'); const j = await r.json();
  $("#health").textContent = JSON.stringify(j, null, 2);
}

async function loadAll() {
  await Promise.all([loadPredictions(), loadValueBets(), loadHealth()]);
}

loadAll();
</script>
</body>
</html>
"""

@app.route("/")
def ui():
    return Response(INDEX_HTML, mimetype="text/html")

if __name__ == "__main__":
    threading.Thread(target=scheduler_loop, daemon=True).start()
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port)