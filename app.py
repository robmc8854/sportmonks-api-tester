Here’s a drop-in, fully corrected app.py that (a) fixes all syntax issues, (b) auto-retries bad includes, (c) enriches fixtures per-fixture with valid semicolon-style includes, and (d) safely probes fixture-level odds when available on your plan. No extra commentary—just paste this as app.py.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DEBUG SPORTMONKS DATA FETCHER
Shows exactly what data is being received from your subscription, enriches fixtures
with valid includes, and (optionally) probes fixture-level odds when available.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests
from flask import Flask, jsonify, request

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Debugger
# -----------------------------------------------------------------------------
class SportMonksDebugger:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_url = "https://api.sportmonks.com/v3/odds"
        self.core_url = "https://api.sportmonks.com/v3/core"

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "SportMonks-Debug/1.1"
        })

        self.debug_log: List[str] = []
        self.raw_responses: Dict[str, Any] = {}

        # Tuning
        self.MAX_ENRICH_FIXTURES = int(os.environ.get("MAX_ENRICH_FIXTURES", "25"))
        # If True, try per-fixture odds include; if plan lacks odds, calls are skipped gracefully
        self.PROBE_FIXTURE_ODDS = os.environ.get("PROBE_FIXTURE_ODDS", "true").lower() == "true"

    # ---------------------- Utilities ----------------------
    def log_debug(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self.debug_log.append(line)
        logger.info(line)

    def _request_once(self, url: str, params: Optional[Dict] = None) -> Optional[requests.Response]:
        try:
            qp = {"api_token": self.api_token}
            if params:
                qp.update(params)
            return self.session.get(url, params=qp, timeout=30)
        except Exception as e:
            self.log_debug(f"🚨 Exception during request: {str(e)[:200]}")
            return None

    def _parse_json(self, resp: Optional[requests.Response]) -> Dict:
        if not resp:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}

    # ---------------------- Smart request with include retry ----------------------
    def make_request(self, endpoint_name: str, url: str, params: Optional[Dict] = None) -> Dict:
        """Make API request with detailed logging and auto-retry when include is invalid (5001)."""
        self.log_debug(f"🌐 Making request to: {endpoint_name}")
        self.log_debug(f"📍 URL: {url}")
        if params:
            self.log_debug(f"📋 Params: {params}")

        resp = self._request_once(url, params)
        if not resp:
            self.log_debug("❌ No response (network/timeout)")
            return {}

        self.log_debug(f"📊 Status Code: {resp.status_code}")

        # Fast path success
        if resp.status_code == 200:
            data = self._parse_json(resp)
            self._store_and_summarize(endpoint_name, data)
            return data

        # If include is not allowed (SportMonks code 5001) try again without include
        if resp.status_code in (400, 404, 422):
            preview = (resp.text or "")[:200]
            data = self._parse_json(resp)
            sm_code = (data or {}).get("code")
            msg = (data or {}).get("message", "")
            if sm_code == 5001 or "include" in msg.lower():
                self.log_debug("↩️  Retrying without 'include' (API says the include is not allowed here)")
                clean_params = dict(params or {})
                clean_params.pop("include", None)
                retry = self._request_once(url, clean_params)
                if retry and retry.status_code == 200:
                    self.log_debug(f"📊 Retry Status Code: {retry.status_code}")
                    data2 = self._parse_json(retry)
                    self._store_and_summarize(endpoint_name, data2)
                    return data2
                else:
                    self.log_debug(f"❌ Retry failed (status {retry.status_code if retry else 'n/a'})")
                    return {}
            else:
                self.log_debug(f"❌ Failed with status {resp.status_code}")
                self.log_debug(f"💬 Response: {preview}")
                return {}
        else:
            self.log_debug(f"❌ Failed with status {resp.status_code}")
            self.log_debug(f"💬 Response: {(resp.text or '')[:200]}")
            return {}

    def _store_and_summarize(self, endpoint_name: str, data: Dict):
        """Store raw response and print small summary in the log."""
        self.raw_responses[endpoint_name] = data
        if not isinstance(data, dict):
            self.log_debug("✅ Success: Non-dict response parsed")
            return
        if "data" in data:
            items = data["data"]
            if isinstance(items, list):
                self.log_debug(f"✅ Success: {len(items)} items received")
                if items:
                    sample = items[0]
                    self.log_debug(f"📝 Sample item keys: {list(sample.keys())[:10]}")
                    if isinstance(sample, dict):
                        if "name" in sample:
                            self.log_debug(f"🏷️  Sample name: {sample.get('name')}")
                        if "id" in sample:
                            self.log_debug(f"🆔 Sample ID: {sample.get('id')}")
            elif isinstance(items, dict):
                self.log_debug("✅ Success: Single item received")
                self.log_debug(f"📝 Keys: {list(items.keys())[:10]}")
            else:
                self.log_debug("✅ Success: 'data' found (unknown structure)")
        else:
            self.log_debug(f"✅ Success: Response keys: {list(data.keys())[:10]}")

    # ---------------------- Subscription sweep + enrichment ----------------------
    def test_subscription_access(self) -> Dict:
        """Test key endpoints and enrich fixtures with valid includes. Optionally probe odds."""
        self.log_debug("🔍 TESTING SPORTMONKS SUBSCRIPTION ACCESS")
        self.log_debug("=" * 50)

        # 1) Subscription info (not on many plans—404 is normal)
        self.log_debug("📋 Test 1: Checking subscription details...")
        sub = self.make_request("subscription", f"{self.core_url}/my/subscription")
        if not sub:
            self.log_debug("ℹ️  Subscription endpoint unavailable or not on your plan (expected for many accounts).")

        # 2) Leagues
        self.log_debug("🏆 Test 2: Fetching available leagues...")
        self.make_request("leagues", f"{self.base_url}/leagues", {"per_page": "50"})

        # 3) Today's fixtures (date endpoint doesn't allow include—retry logic will handle)
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_debug(f"📅 Test 3: Fetching today's fixtures ({today})...")
        fx_today = self.make_request("todays_fixtures", f"{self.base_url}/fixtures/date/{today}", {"include": "participants;league"})

        # 4) Tomorrow's fixtures
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.log_debug(f"📅 Test 4: Fetching tomorrow's fixtures ({tomorrow})...")
        fx_tom = self.make_request("tomorrows_fixtures", f"{self.base_url}/fixtures/date/{tomorrow}", {"include": "participants;league"})

        # 5) Livescores
        self.log_debug("⚡ Test 5: Fetching live scores...")
        self.make_request("live_scores", f"{self.base_url}/livescores")

        # 6) Teams
        self.log_debug("👥 Test 6: Fetching teams...")
        self.make_request("teams", f"{self.base_url}/teams", {"per_page": "25"})

        # 7) Players
        self.log_debug("👤 Test 7: Fetching players...")
        self.make_request("players", f"{self.base_url}/players", {"per_page": "25"})

        # 8) Bookmakers
        self.log_debug("📚 Test 8: Fetching bookmakers...")
        self.make_request("bookmakers", f"{self.odds_url}/bookmakers")

        # 9) Markets
        self.log_debug("🎯 Test 9: Fetching betting markets...")
        self.make_request("markets", f"{self.odds_url}/markets")

        # 10 & 11) Global odds endpoints (often not on base plans) – attempt once; log and continue
        self.log_debug("💰 Test 10: Fetching pre-match odds...")
        pm = self.make_request("pre_match_odds", f"{self.odds_url}/pre-match", {"per_page": "50"})
        if not pm:
            self.log_debug("ℹ️  Pre-match odds endpoint unavailable on your plan (skipping).")

        self.log_debug("⚡ Test 11: Fetching live odds...")
        ip = self.make_request("live_odds", f"{self.odds_url}/inplay", {"per_page": "50"})
        if not ip:
            self.log_debug("ℹ️  Live odds endpoint unavailable on your plan (skipping).")

        # 12) Standings
        self.log_debug("🏆 Test 12: Fetching standings...")
        self.make_request("standings", f"{self.base_url}/standings", {"per_page": "25"})

        # ---- Enrichment: per-fixture GET with valid includes ----
        self._enrich_fixtures_block("todays_fixtures", "fixtures_enriched_today")
        self._enrich_fixtures_block("tomorrows_fixtures", "fixtures_enriched_tomorrow")

        self.log_debug("=" * 50)
        self.log_debug("🎯 SUBSCRIPTION ANALYSIS COMPLETE")
        return self.generate_subscription_summary()

    def _enrich_fixtures_block(self, base_key: str, out_key: str):
        """Take fixtures from date endpoints, enrich each fixture with participants/league/venue/state/scores.
        Optionally include odds (if allowed)."""
        base = self.raw_responses.get(base_key) or {}
        fixtures: List[Dict] = []
        if isinstance(base, dict) and isinstance(base.get("data"), list):
            fixtures = base["data"]

        if not fixtures:
            self.log_debug(f"ℹ️  No fixtures to enrich for {base_key}")
            self.raw_responses[out_key] = {"data": []}
            return

        enrich_ids = [fx.get("id") for fx in fixtures if isinstance(fx, dict) and fx.get("id")]  # type: ignore
        enrich_ids = enrich_ids[: self.MAX_ENRICH_FIXTURES]
        self.log_debug(f"🔧 Enriching {len(enrich_ids)} fixtures via /fixtures/{{id}} includes...")

        enriched: List[Dict] = []
        include_parts = ["participants", "league", "venue", "state", "scores"]
        if self.PROBE_FIXTURE_ODDS:
            # Try odds includes; if the plan doesn't have it, per-call retry will strip it
            include_parts += ["odds.market", "odds.bookmaker"]

        include_str = ";".join(include_parts)

        for fid in enrich_ids:
            fx_url = f"{self.base_url}/fixtures/{fid}"
            fx_data = self.make_request(f"fixture_{fid}", fx_url, {"include": include_str})
            if isinstance(fx_data, dict) and fx_data.get("data"):
                enriched.append(fx_data["data"])

        self.raw_responses[out_key] = {"data": enriched}
        self.log_debug(f"✅ Enriched fixtures stored in '{out_key}'")

    # ---------------------- Summary + Opportunities ----------------------
    def generate_subscription_summary(self) -> Dict:
        """Generate comprehensive summary of what's available."""
        summary: Dict[str, Any] = {
            "total_endpoints_tested": len(self.raw_responses),
            "successful_endpoints": 0,
            "failed_endpoints": 0,
            "available_data": {},
            "subscription_details": {},
            "debug_log": self.debug_log,
            "raw_data_sample": {}
        }

        for endpoint_name, data in self.raw_responses.items():
            ok = bool(data) and isinstance(data, dict)
            if ok:
                summary["successful_endpoints"] += 1
                if "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        cnt = len(items)
                        summary["available_data"][endpoint_name] = {
                            "status": "success",
                            "count": cnt,
                            "sample": items[0] if items else None
                        }
                    else:
                        summary["available_data"][endpoint_name] = {
                            "status": "success",
                            "count": 1,
                            "sample": items
                        }
                else:
                    summary["available_data"][endpoint_name] = {
                        "status": "success",
                        "count": 0,
                        "sample": data
                    }
                text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
                summary["raw_data_sample"][endpoint_name] = (text[:500] + "...") if len(text) > 500 else text
            else:
                summary["failed_endpoints"] += 1
                summary["available_data"][endpoint_name] = {
                    "status": "failed",
                    "count": 0,
                    "sample": None
                }

        if "subscription" in self.raw_responses:
            sub = self.raw_responses["subscription"]
            if isinstance(sub, dict) and "data" in sub:
                summary["subscription_details"] = sub["data"]

        return summary

    def _collect_fixture_cards(self, key_a: str, key_b: str) -> List[Dict]:
        """Return lightweight fixture cards (home, away, league, kickoff, id) from enriched blocks if possible."""
        cards: List[Dict] = []

        def pull(block_key: str):
            blk = self.raw_responses.get(block_key) or {}
            items = blk.get("data") if isinstance(blk, dict) else None
            if isinstance(items, list):
                for fx in items:
                    if not isinstance(fx, dict):
                        continue
                    fx_id = fx.get("id")
                    kickoff = fx.get("starting_at")
                    league_name = (fx.get("league") or {}).get("name") if isinstance(fx.get("league"), dict) else None

                    # Participants can be list or dict keyed differently depending on expanders
                    home = "Unknown"
                    away = "Unknown"
                    parts = fx.get("participants")
                    if isinstance(parts, list) and len(parts) >= 2:
                        home = parts[0].get("name", home) if isinstance(parts[0], dict) else home
                        away = parts[1].get("name", away) if isinstance(parts[1], dict) else away

                    cards.append({
                        "id": fx_id,
                        "home_team": home,
                        "away_team": away,
                        "league": league_name or "Unknown",
                        "kickoff": kickoff or "Unknown"
                    })

        pull(key_a)
        pull(key_b)
        return cards

    def find_available_fixtures_with_odds(self) -> Dict:
        """Identify fixtures with odds included (when available on plan). Also list first fixtures."""
        self.log_debug("🔍 SEARCHING FOR FIXTURES WITH AVAILABLE ODDS")

        # Prefer enriched blocks
        cards = self._collect_fixture_cards("fixtures_enriched_today", "fixtures_enriched_tomorrow")
        if not cards:
            # Fallback to raw date endpoints
            self.log_debug("ℹ️  Enriched fixtures empty; falling back to date endpoints")
            for ep in ("todays_fixtures", "tomorrows_fixtures"):
                base = self.raw_responses.get(ep) or {}
                items = base.get("data") if isinstance(base, dict) else None
                if isinstance(items, list):
                    for fx in items[:20]:
                        if not isinstance(fx, dict):
                            continue
                        parts = fx.get("participants") or []
                        home = parts[0].get("name") if isinstance(parts, list) and len(parts) > 0 and isinstance(parts[0], dict) else "Unknown"
                        away = parts[1].get("name") if isinstance(parts, list) and len(parts) > 1 and isinstance(parts[1], dict) else "Unknown"
                        league_name = (fx.get("league") or {}).get("name") if isinstance(fx.get("league"), dict) else "Unknown"
                        cards.append({
                            "id": fx.get("id"),
                            "home_team": home,
                            "away_team": away,
                            "league": league_name,
                            "kickoff": fx.get("starting_at", "Unknown")
                        })

        total_fixtures = len(cards)

        # Determine odds availability by checking enriched fixture payloads for "odds"
        fixtures_with_odds = 0
        opportunities: List[Dict] = []

        # Scan enriched entries for "odds"
        def scan_enriched(block_key: str):
            nonlocal fixtures_with_odds, opportunities
            blk = self.raw_responses.get(block_key) or {}
            items = blk.get("data") if isinstance(blk, dict) else None
            if not isinstance(items, list):
                return
            for fx in items:
                if not isinstance(fx, dict):
                    continue
                has_odds = False
                odds_obj = fx.get("odds")
                if isinstance(odds_obj, dict):
                    # Some structures: odds -> data(list) or nested by bookmaker, etc.
                    if odds_obj.get("data") and isinstance(odds_obj["data"], list) and len(odds_obj["data"]) > 0:
                        has_odds = True
                elif isinstance(odds_obj, list) and len(odds_obj) > 0:
                    has_odds = True

                if has_odds:
                    fixtures_with_odds += 1
                    # Find the matching card for display
                    fid = fx.get("id")
                    card = next((c for c in cards if c.get("id") == fid), None)
                    if card:
                        opportunities.append(card)

        scan_enriched("fixtures_enriched_today")
        scan_enriched("fixtures_enriched_tomorrow")

        self.log_debug(f"📊 Found {total_fixtures} total fixtures")
        self.log_debug(f"🎯 RESULT: {fixtures_with_odds} fixtures have odds available")

        return {
            "total_fixtures": total_fixtures,
            "fixtures_with_odds": fixtures_with_odds,
            "opportunities": opportunities[:10],
            "all_fixtures": cards[:20]
        }

# -----------------------------------------------------------------------------
# Flask App
# -----------------------------------------------------------------------------
app = Flask(__name__)
debugger: Optional[SportMonksDebugger] = None

@app.route("/", methods=["GET"])
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>SportMonks Debug Dashboard</title>
<style>
body { font-family: monospace; background: #0a0a0a; color: #00ff00; padding: 20px; line-height: 1.4; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { color: #00ffff; text-align: center; border-bottom: 2px solid #00ffff; padding-bottom: 10px; }
.section { background: #111; border: 1px solid #333; padding: 20px; margin: 20px 0; border-radius: 8px; }
.btn { background: #0066cc; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
.btn:hover { background: #0088ff; }
input { background: #222; color: #00ff00; border: 1px solid #555; padding: 12px; width: 400px; border-radius: 4px; }
.log { background: #000; border: 1px solid #333; padding: 15px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; }
.success { color: #00ff00; }
.error { color: #ff4444; }
.warning { color: #ffaa00; }
.info { color: #00aaff; }
.data-item { background: #001122; border-left: 3px solid #0088ff; padding: 10px; margin: 5px 0; }
.endpoint-result { margin: 10px 0; padding: 10px; background: #1a1a1a; border-radius: 4px; }
</style>
</head>
<body>
<div class="container">
<h1>🔍 SportMonks Subscription Debugger</h1>

<div class="section">
    <h3>🚀 Initialize Debug Session</h3>
    <input id="apiToken" type="password" placeholder="Enter your SportMonks API Token...">
    <button class="btn" onclick="initializeDebugger()">Start Debug Analysis</button>
</div>

<div class="section">
    <h3>🎮 Debug Controls</h3>
    <button class="btn" onclick="testSubscription()">Test All Endpoints</button>
    <button class="btn" onclick="findOpportunities()">Find Betting Opportunities</button>
    <button class="btn" onclick="showRawData()">Show Raw Data</button>
    <button class="btn" onclick="clearLog()">Clear Log</button>
</div>

<div class="section">
    <h3>📊 Subscription Summary</h3>
    <div id="summary">Run "Test All Endpoints" to see what your subscription can access</div>
</div>

<div class="section">
    <h3>📈 Betting Opportunities</h3>
    <div id="opportunities">Click "Find Betting Opportunities" to see available matches</div>
</div>

<div class="section">
    <h3>📋 Debug Log</h3>
    <div id="debugLog" class="log">Debug session not started...</div>
</div>

<div class="section">
    <h3>🔧 Raw Data (Sample)</h3>
    <div id="rawData" class="log">No raw data yet...</div>
</div>
</div>

<script>
let pollInterval;

async function initializeDebugger() {
    const token = document.getElementById('apiToken').value.trim();
    if (!token) { alert('Please enter your SportMonks API token'); return; }
    try {
        const r = await fetch('/api/init', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        const data = await r.json();
        if (data.success) {
            updateLog(['✅ Debugger initialized successfully']);
            startLogPolling();
        } else {
            updateLog(['❌ Failed to initialize: ' + data.error]);
        }
    } catch (e) { updateLog(['🚨 Error: ' + e.message]); }
}

async function testSubscription() {
    try {
        updateLog(['🔍 Starting comprehensive subscription test...']);
        const r = await fetch('/api/test-subscription', { method: 'POST' });
        const data = await r.json();
        if (data.success) { displaySummary(data.summary); }
        else { updateLog(['❌ Test failed: ' + data.error]); }
    } catch (e) { updateLog(['🚨 Error: ' + e.message]); }
}

async function findOpportunities() {
    try {
        const r = await fetch('/api/find-opportunities', { method: 'POST' });
        const data = await r.json();
        if (data.success) { displayOpportunities(data.opportunities); }
        else { updateLog(['❌ Failed to find opportunities: ' + data.error]); }
    } catch (e) { updateLog(['🚨 Error: ' + e.message]); }
}

async function showRawData() {
    try {
        const r = await fetch('/api/raw-data');
        const data = await r.json();
        document.getElementById('rawData').textContent = JSON.stringify(data, null, 2);
    } catch (e) { updateLog(['🚨 Error fetching raw data: ' + e.message]); }
}

function startLogPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        try {
            const r = await fetch('/api/debug-log');
            const data = await r.json();
            if (data.log && data.log.length > 0) updateLog(data.log);
        } catch (e) {}
    }, 2000);
}

function updateLog(lines) {
    const el = document.getElementById('debugLog');
    el.textContent = lines.join('\\n');
    el.scrollTop = el.scrollHeight;
}

function displaySummary(summary) {
    const el = document.getElementById('summary');
    let html = `
        <div class="endpoint-result">
            <strong>📊 SUBSCRIPTION ANALYSIS RESULTS</strong><br>
            Endpoints Tested: ${summary.total_endpoints_tested}<br>
            Successful: <span class="success">${summary.successful_endpoints}</span><br>
            Failed: <span class="error">${summary.failed_endpoints}</span>
        </div>
    `;
    Object.entries(summary.available_data).forEach(([ep, info]) => {
        const status = info.status === 'success' ? 'success' : 'error';
        html += `
            <div class="data-item">
                <strong>${ep}</strong>: <span class="${status}">${info.status}</span><br>
                Items: ${info.count}<br>
                ${info.sample ? 'Sample available ✓' : 'No sample data'}
            </div>
        `;
    });
    el.innerHTML = html;
}

function displayOpportunities(opps) {
    const el = document.getElementById('opportunities');
    let html = `
        <div class="endpoint-result">
            <strong>⚽ BETTING OPPORTUNITIES FOUND</strong><br>
            Total Fixtures: ${opps.total_fixtures}<br>
            Fixtures with Odds: <span class="success">${opps.fixtures_with_odds}</span>
        </div>
    `;
    if (opps.opportunities && opps.opportunities.length > 0) {
        html += '<h4>🎯 Available Opportunities:</h4>';
        opps.opportunities.forEach(opp => {
            html += `
                <div class="data-item">
                    <strong>${opp.home_team} vs ${opp.away_team}</strong><br>
                    League: ${opp.league}<br>
                    Kickoff: ${opp.kickoff}<br>
                    ID: ${opp.id}
                </div>
            `;
        });
    } else {
        html += '<p class="warning">No betting opportunities found with available odds</p>';
    }

    if (opps.all_fixtures && opps.all_fixtures.length > 0) {
        html += '<h4>📅 All Upcoming Fixtures (Sample):</h4>';
        opps.all_fixtures.slice(0, 5).forEach(fx => {
            html += `
                <div class="data-item">
                    ${fx.home_team} vs ${fx.away_team} (${fx.league})
                </div>
            `;
        });
    }
    el.innerHTML = html;
}

function clearLog() { document.getElementById('debugLog').textContent = 'Log cleared...'; }
</script>
</body>
</html>
    """

@app.route("/api/init", methods=["POST"])
def init_debugger():
    global debugger
    data = request.get_json(silent=True) or {}
    api_token = data.get("api_token")
    if not api_token:
        return jsonify({"error": "API token required"}), 400
    try:
        debugger = SportMonksDebugger(api_token)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test-subscription", methods=["POST"])
def test_subscription():
    global debugger
    if not debugger:
        return jsonify({"error": "Debugger not initialized"}), 400
    try:
        summary = debugger.test_subscription_access()
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/find-opportunities", methods=["POST"])
def find_opportunities():
    global debugger
    if not debugger:
        return jsonify({"error": "Debugger not initialized"}), 400
    try:
        opps = debugger.find_available_fixtures_with_odds()
        return jsonify({"success": True, "opportunities": opps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/debug-log", methods=["GET"])
def get_debug_log():
    global debugger
    if not debugger:
        return jsonify({"log": ["Debugger not initialized"]})
    return jsonify({"log": debugger.debug_log})

@app.route("/api/raw-data", methods=["GET"])
def get_raw_data():
    global debugger
    if not debugger:
        return jsonify({"error": "Debugger not initialized"})
    return jsonify(debugger.raw_responses)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})

# Gunicorn / Dev
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)

# For Gunicorn
application = app