#!/usr/bin/env python3
"""
DEBUG SPORTMONKS DATA FETCHER
Shows exactly what data is being received from your subscription
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
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

        self.debug_log = []
        self.raw_responses = {}

    def log_debug(self, message: str):
        """Add debug message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.debug_log.append(log_entry)
        logger.info(log_entry)

    def make_request(self, endpoint_name: str, url: str, params: Dict = None) -> Dict:
        """Make API request with detailed logging"""
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
                    self.raw_responses[endpoint_name] = data

                    if isinstance(data, dict):
                        if 'data' in data:
                            items = data['data']
                            if isinstance(items, list):
                                self.log_debug(f"✅ Success: {len(items)} items received")
                                if items:
                                    sample = items[0]
                                    self.log_debug(f"📝 Sample keys: {list(sample.keys())[:10]}")
                                    if 'name' in sample:
                                        self.log_debug(f"🏷️ Sample name: {sample.get('name')}")
                                    if 'id' in sample:
                                        self.log_debug(f"🆔 Sample ID: {sample.get('id')}")
                            else:
                                self.log_debug("✅ Success: Single item received")
                        else:
                            self.log_debug(f"✅ Success: Keys: {list(data.keys())}")
                    return data

                except json.JSONDecodeError:
                    self.log_debug("❌ Failed to parse JSON")
                    return {}
            else:
                self.log_debug(f"❌ Failed with status {response.status_code}")
                self.log_debug(f"💬 Response: {response.text[:200]}")
                return {}

        except Exception as e:
            self.log_debug(f"🚨 Exception: {str(e)}")
            return {}

    def test_subscription_access(self):
        """Test what your subscription can actually access"""
        self.log_debug("🔍 TESTING SPORTMONKS SUBSCRIPTION ACCESS")
        self.log_debug("=" * 50)

        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        tests = [
            ("subscription", f"{self.core_url}/my/subscription"),
            ("leagues", f"{self.base_url}/leagues", {"per_page": "50"}),
            ("todays_fixtures", f"{self.base_url}/fixtures/date/{today}", {"include": "participants,league"}),
            ("tomorrows_fixtures", f"{self.base_url}/fixtures/date/{tomorrow}", {"include": "participants,league"}),
            ("live_scores", f"{self.base_url}/livescores"),
            ("teams", f"{self.base_url}/teams", {"per_page": "25"}),
            ("players", f"{self.base_url}/players", {"per_page": "25"}),
            ("bookmakers", f"{self.odds_url}/bookmakers"),
            ("markets", f"{self.odds_url}/markets"),
            ("pre_match_odds", f"{self.odds_url}/pre-match", {"per_page": "50"}),
            ("live_odds", f"{self.odds_url}/inplay", {"per_page": "50"}),
            ("standings", f"{self.base_url}/standings", {"per_page": "25"}),
        ]

        for name, url, *opt in tests:
            self.make_request(name, url, *(opt or [{}]))

        self.log_debug("=" * 50)
        self.log_debug("🎯 SUBSCRIPTION ANALYSIS COMPLETE")
        return self.generate_subscription_summary()

    def generate_subscription_summary(self):
        """Generate comprehensive summary of what's available"""
        summary = {
            'total_endpoints_tested': len(self.raw_responses),
            'successful_endpoints': 0,
            'failed_endpoints': 0,
            'available_data': {},
            'subscription_details': {},
            'debug_log': self.debug_log,
            'raw_data_sample': {}
        }

        for endpoint, data in self.raw_responses.items():
            if data and isinstance(data, dict):
                summary['successful_endpoints'] += 1
                if 'data' in data:
                    items = data['data']
                    if isinstance(items, list):
                        summary['available_data'][endpoint] = {
                            'status': 'success',
                            'count': len(items),
                            'sample': items[0] if items else None
                        }
                    else:
                        summary['available_data'][endpoint] = {
                            'status': 'success',
                            'count': 1,
                            'sample': items
                        }
                else:
                    summary['available_data'][endpoint] = {
                        'status': 'success',
                        'count': 0,
                        'sample': data
                    }
                summary['raw_data_sample'][endpoint] = str(data)[:500] + "..." if len(str(data)) > 500 else str(data)
            else:
                summary['failed_endpoints'] += 1
                summary['available_data'][endpoint] = {
                    'status': 'failed',
                    'count': 0,
                    'sample': None
                }

        if 'subscription' in self.raw_responses:
            sub_data = self.raw_responses['subscription']
            if isinstance(sub_data, dict) and 'data' in sub_data:
                summary['subscription_details'] = sub_data['data']

        return summary

    def find_available_fixtures_with_odds(self):
        """Find fixtures that have odds available"""
        self.log_debug("🔍 SEARCHING FOR FIXTURES WITH AVAILABLE ODDS")

        available_opportunities = []
        fixture_ids = []

        for endpoint in ['todays_fixtures', 'tomorrows_fixtures']:
            if endpoint in self.raw_responses:
                data = self.raw_responses[endpoint]
                if isinstance(data, dict) and 'data' in data:
                    for fixture in data['data']:
                        if isinstance(fixture, dict) and 'id' in fixture:
                            info = {
                                'id': fixture['id'],
                                'home_team': 'Unknown',
                                'away_team': 'Unknown',
                                'league': 'Unknown',
                                'kickoff': fixture.get('starting_at', 'Unknown')
                            }
                            participants = fixture.get('participants', [])
                            if len(participants) >= 2:
                                info['home_team'] = participants[0].get('name', 'Unknown')
                                info['away_team'] = participants[1].get('name', 'Unknown')
                            if 'league' in fixture:
                                info['league'] = fixture['league'].get('name', 'Unknown')
                            fixture_ids.append(info)

        self.log_debug(f"📊 Found {len(fixture_ids)} total fixtures")

        odds_available = 0
        if 'pre_match_odds' in self.raw_responses:
            odds_data = self.raw_responses['pre_match_odds']
            if isinstance(odds_data, dict) and 'data' in odds_data:
                odds_fixture_ids = {odds_item['fixture_id'] for odds_item in odds_data['data'] if isinstance(odds_item, dict) and 'fixture_id' in odds_item}
                self.log_debug(f"💰 Found odds for {len(odds_fixture_ids)} fixtures")

                for fixture in fixture_ids:
                    if fixture['id'] in odds_fixture_ids:
                        available_opportunities.append(fixture)
                        odds_available += 1

        self.log_debug(f"🎯 RESULT: {odds_available} fixtures have odds available")

        return {
            'total_fixtures': len(fixture_ids),
            'fixtures_with_odds': odds_available,
            'opportunities': available_opportunities[:10],
            'all_fixtures': fixture_ids[:20]
        }


# Flask App
app = Flask(__name__)
debugger: Optional[SportMonksDebugger] = None


@app.route("/api/init", methods=["POST"])
def init_debugger():
    global debugger
    data = request.get_json()
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# Gunicorn entrypoint
application = app