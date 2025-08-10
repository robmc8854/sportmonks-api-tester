#!/usr/bin/env python3
"""
DEBUG SPORTMONKS DATA FETCHER
Shows exactly what data is being received from your subscription.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            "User-Agent": "SportMonks-Debug/1.0"
        })

        self.debug_log: List[str] = []
        self.raw_responses: Dict[str, dict] = {}

    def log_debug(self, message: str) -> None:
        """Add debug message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.debug_log.append(log_entry)
        logger.info(log_entry)

    def make_request(self, endpoint_name: str, url: str, params: Optional[Dict] = None) -> Dict:
        """Make API request with detailed logging."""
        self.log_debug(f"🌐 Making request to: {endpoint_name}")
        self.log_debug(f"📍 URL: {url}")

        try:
            request_params = {"api_token": self.api_token}
            if params:
                request_params.update(params)
                self.log_debug(f"📋 Params: {params}")

            response = self.session.get(url, params=request_params, timeout=30)
            self.log_debug(f"📊 Status Code: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    # Store raw response
                    self.raw_responses[endpoint_name] = data

                    # Log data summary
                    if isinstance(data, dict):
                        if "data" in data:
                            data_items = data["data"]
                            if isinstance(data_items, list):
                                self.log_debug(f"✅ Success: {len(data_items)} items received")
                                if data_items:
                                    sample = data_items[0]
                                    self.log_debug(f"📝 Sample item keys: {list(sample.keys())[:10]}")
                                    if isinstance(sample, dict):
                                        if "name" in sample:
                                            self.log_debug(f"🏷️  Sample name: {sample.get('name')}")
                                        if "id" in sample:
                                            self.log_debug(f"🆔 Sample ID: {sample.get('id')}")
                            else:
                                self.log_debug("✅ Success: Single item received")
                        else:
                            self.log_debug(f"✅ Success: Response keys: {list(data.keys())}")
                    return data
                except json.JSONDecodeError:
                    self.log_debug("❌ Failed to parse JSON response")
                    return {}
            else:
                self.log_debug(f"❌ Failed with status {response.status_code}")
                self.log_debug(f"💬 Response: {response.text[:200]}")
                return {}
        except Exception as e:
            self.log_debug(f"🚨 Exception: {str(e)}")
            return {}

    def test_subscription_access(self) -> Dict:
        """Test what your subscription can actually access."""
        self.log_debug("🔍 TESTING SPORTMONKS SUBSCRIPTION ACCESS")
        self.log_debug("=" * 50)

        # Test 1: Subscription info
        self.log_debug("📋 Test 1: Checking subscription details...")
        self.make_request("subscription", f"{self.core_url}/my/subscription")

        # Test 2: Available leagues
        self.log_debug("🏆 Test 2: Fetching available leagues...")
        self.make_request("leagues", f"{self.base_url}/leagues", {"per_page": "50"})

        # Test 3: Today's fixtures
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_debug(f"📅 Test 3: Fetching today's fixtures ({today})...")
        self.make_request(
            "todays_fixtures",
            f"{self.base_url}/fixtures/date/{today}",
            {"include": "participants,league"}
        )

        # Test 4: Tomorrow's fixtures
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.log_debug(f"📅 Test 4: Fetching tomorrow's fixtures ({tomorrow})...")
        self.make_request(
            "tomorrows_fixtures",
            f"{self.base_url}/fixtures/date/{tomorrow}",
            {"include": "participants,league"}
        )

        # Test 5: Live scores
        self.log_debug("⚡ Test 5: Fetching live scores...")
        self.make_request("live_scores", f"{self.base_url}/livescores")

        # Test 6: Teams
        self.log_debug("👥 Test 6: Fetching teams...")
        self.make_request("teams", f"{self.base_url}/teams", {"per_page": "25"})

        # Test 7: Players
        self.log_debug("👤 Test 7: Fetching players...")
        self.make_request("players", f"{self.base_url}/players", {"per_page": "25"})

        # Test 8: Bookmakers
        self.log_debug("📚 Test 8: Fetching bookmakers...")
        self.make_request("bookmakers", f"{self.odds_url}/bookmakers")

        # Test 9: Betting markets
        self.log_debug("🎯 Test 9: Fetching betting markets...")
        self.make_request("markets", f"{self.odds_url}/markets")

        # Test 10: Pre-match odds
        self.log_debug("💰 Test 10: Fetching pre-match odds...")
        self.make_request("pre_match_odds", f"{self.odds_url}/pre-match", {"per_page": "50"})

        # Test 11: Live odds
        self.log_debug("⚡ Test 11: Fetching live odds...")
        self.make_request("live_odds", f"{self.odds_url}/inplay", {"per_page": "50"})

        # Test 12: Standings
        self.log_debug("🏆 Test 12: Fetching standings...")
        self.make_request("standings", f"{self.base_url}/standings", {"per_page": "25"})

        self.log_debug("=" * 50)
        self.log_debug("🎯 SUBSCRIPTION ANALYSIS COMPLETE")

        return self.generate_subscription_summary()

    def generate_subscription_summary(self) -> Dict:
        """Generate comprehensive summary of what's available."""
        summary: Dict = {
            "total_endpoints_tested": len(self.raw_responses),
            "successful_endpoints": 0,
            "failed_endpoints": 0,
            "available_data": {},
            "subscription_details": {},
            "debug_log": self.debug_log,
            "raw_data_sample": {}
        }

        for endpoint_name, data in self.raw_responses.items():
            if data and isinstance(data, dict):
                summary["successful_endpoints"] += 1

                if "data" in data:
                    data_items = data["data"]
                    if isinstance(data_items, list):
                        item_count = len(data_items)
                        summary["available_data"][endpoint_name] = {
                            "status": "success",
                            "count": item_count,
                            "sample": data_items[0] if data_items else None
                        }
                    else:
                        summary["available_data"][endpoint_name] = {
                            "status": "success",
                            "count": 1,
                            "sample": data_items
                        }
                else:
                    summary["available_data"][endpoint_name] = {
                        "status": "success",
                        "count": 0,
                        "sample": data
                    }

                # Safe, truncated sample
                s = json.dumps(data) if not isinstance(data, str) else data
                summary["raw_data_sample"][endpoint_name] = (s[:500] + "...") if len(s) > 500 else s
            else:
                summary["failed_endpoints"] += 1
                summary["available_data"][endpoint_name] = {
                    "status": "failed",
                    "count": 0,
                    "sample": None
                }

        if "subscription" in self.raw_responses:
            sub_data = self.raw_responses["subscription"]
            if isinstance(sub_data, dict) and "data" in sub_data:
                summary["subscription_details"] = sub_data["data"]

        return summary

    def find_available_fixtures_with_odds(self) -> Dict:
        """Find fixtures that have odds available."""
        self.log_debug("🔍 SEARCHING FOR FIXTURES WITH AVAILABLE ODDS")

        available_opportunities: List[Dict] = []
        fixture_refs: List[Dict] = []

        # Gather fixtures from today and tomorrow
        for endpoint in ["todays_fixtures", "tomorrows_fixtures"]:
            data = self.raw_responses.get(endpoint)
            if isinstance(data, dict) and "data" in data:
                fixtures = data["data"]
                for fixture in fixtures:
                    if isinstance(fixture, dict) and "id" in fixture:
                        ref = {
                            "id": fixture["id"],
                            "home_team": "Unknown",
                            "away_team": "Unknown",
                            "league": "Unknown",
                            "kickoff": fixture.get("starting_at", "Unknown")
                        }
                        participants = fixture.get("participants", [])
                        if isinstance(participants, list) and len(participants) >= 2:
                            ref["home_team"] = participants[0].get("name", "Unknown")
                            ref["away_team"] = participants[1].get("name", "Unknown")
                        if "league" in fixture and isinstance(fixture["league"], dict):
                            ref["league"] = fixture["league"].get("name", "Unknown")
                        fixture_refs.append(ref)

        self.log_debug(f"📊 Found {len(fixture_refs)} total fixtures")

        # Match fixtures to available odds
        odds_available = 0
        odds_fixture_ids = set()

        if "pre_match_odds" in self.raw_responses:
            odds_data = self.raw_responses["pre_match_odds"]
            if isinstance(odds_data, dict) and "data" in odds_data:
                for odds_item in odds_data["data"]:
                    if isinstance(odds_item, dict) and "fixture_id" in odds_item:
                        odds_fixture_ids.add(odds_item["fixture_id"])

        self.log_debug(f"💰 Found odds for {len(odds_fixture_ids)} fixtures")

        for fixture in fixture_refs:
            if fixture["id"] in odds_fixture_ids:
                available_opportunities.append(fixture)
                odds_available += 1

        self.log_debug(f"🎯 RESULT: {odds_available} fixtures have odds available")

        return {
            "total_fixtures": len(fixture_refs),
            "fixtures_with_odds": odds_available,
            "opportunities": available_opportunities[:10],  # Top 10
            "all_fixtures": fixture_refs[:20]               # First 20
        }


# -----------------------------
# Flask application & routes
# -----------------------------

app = Flask(__name__)
debugger: Optional[SportMonksDebugger] = None

HOME_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>SportMonks Debugger</title>
    <style>
      body { font-family: system-ui, Arial, sans-serif; background:#0a0a0a; color:#e5e7eb; padding:24px }
      .card { background:#111; border:1px solid #333; border-radius:12px; padding:20px; max-width:980px; margin:auto }
      h1 { color:#00ffff; margin:0 0 12px 0; }
      input, button { font-size:16px; padding:10px; border-radius:8px; border:1px solid #333 }
      input { background:#0b1220; color:#e5e7eb; width:380px }
      button { background:#2563eb; color:white; border:none; cursor:pointer; margin-left:8px }
      button:hover { filter:brightness(1.1) }
      pre { background:#000; border:1px solid #333; padding:12px; border-radius:8px; max-height:380px; overflow:auto }
      .row { margin:10px 0 }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>🔍 SportMonks Subscription Debugger</h1>
      <div class="row">
        <input id="apiToken" type="password" placeholder="Enter SportMonks API token…">
        <button onclick="init()">Initialize</button>
        <button onclick="testAll()">Test All Endpoints</button>
        <button onclick="findOpps()">Find Opportunities</button>
      </div>
      <h3>Log</h3>
      <pre id="log">Waiting…</pre>
      <h3>Summary</h3>
      <pre id="summary">No summary yet…</pre>
      <h3>Opportunities</h3>
      <pre id="opps">No data yet…</pre>
      <h3>Raw Data (sample)</h3>
      <pre id="raw">No data yet…</pre>
    </div>
    <script>
      async function init() {
        const token = document.getElementById('apiToken').value.trim();
        if (!token) { alert('Enter token'); return; }
        const r = await fetch('/api/init', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ api_token: token }) });
        const j = await r.json();
        write('log', JSON.stringify(j, null, 2));
      }
      async function testAll() {
        const r = await fetch('/api/test-subscription', { method:'POST' });
        const j = await r.json();
        write('summary', JSON.stringify(j, null, 2));
        pollLog();
        showRaw();
      }
      async function findOpps() {
        const r = await fetch('/api/find-opportunities', { method:'POST' });
        const j = await r.json();
        write('opps', JSON.stringify(j, null, 2));
      }
      async function pollLog() {
        try {
          const r = await fetch('/api/debug-log');
          const j = await r.json();
          write('log', (j.log || []).join('\\n'));
        } catch {}
      }
      async function showRaw() {
        const r = await fetch('/api/raw-data');
        const j = await r.json();
        write('raw', JSON.stringify(j, null, 2));
      }
      function write(id, text) { document.getElementById(id).textContent = text; }
    </script>
  </body>
</html>
"""

@app.route("/")
def home():
    return HOME_HTML


@app.route("/api/init", methods=["POST"])
def init_debugger():
    global debugger
    data = request.get_json(silent=True) or {}
    api_token = (data.get("api_token") or "").strip()

    if not api_token:
        return jsonify({"error": "API token required"}), 400

    try:
        debugger = SportMonksDebugger(api_token)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-subscription", methods=["POST"])
def test_subscription():
    if not debugger:
        return jsonify({"error": "Debugger not initialized"}), 400
    try:
        summary = debugger.test_subscription_access()
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/find-opportunities", methods=["POST"])
def find_opportunities():
    if not debugger:
        return jsonify({"error": "Debugger not initialized"}), 400
    try:
        opportunities = debugger.find_available_fixtures_with_odds()
        return jsonify({"success": True, "opportunities": opportunities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug-log")
def get_debug_log():
    if not debugger:
        return jsonify({"log": ["Debugger not initialized"]})
    return jsonify({"log": debugger.debug_log})


@app.route("/api/raw-data")
def get_raw_data():
    if not debugger:
        return jsonify({"error": "Debugger not initialized"})
    return jsonify(debugger.raw_responses)


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)

# Gunicorn compatibility
application = app