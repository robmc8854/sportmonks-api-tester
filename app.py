#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
COMPLETE WORKING BETTING BOT - SYNTAX FIXED
Full production-ready AI betting bot with value bet detection
"""

import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuickValueBetFinder:
    def __init__(self):
        self.today = date.today()
        self.sample_fixture_ids = {19135003, 19427455}

    def find_real_betting_opportunities(self, raw_store_data: Dict) -> Dict:
        real_fixtures = self.extract_real_fixtures(raw_store_data)
        odds_data = self.extract_odds_data(raw_store_data)
        value_bets = self.generate_value_bets(real_fixtures, odds_data)

        summary = {
            "total_fixtures": len(real_fixtures),
            "total_odds_available": len(odds_data),
            "value_bets_found": len(value_bets),
            "best_opportunities": value_bets[:5],
            "summary_text": f"Found {len(value_bets)} value betting opportunities from {len(real_fixtures)} upcoming fixtures",
        }

        logger.info(f"QuickValueBetFinder: {summary['summary_text']}")

        return {
            "status": "success",
            "real_fixtures": real_fixtures,
            "value_bets": value_bets,
            "summary": summary,
        }

    def extract_real_fixtures(self, raw_data: Dict) -> List[Dict]:
        real_fixtures: List[Dict] = []

        for key, data in raw_data.items():
            if key.startswith("upcoming_") and isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    for fixture in data["data"]:
                        if fixture.get("id") in self.sample_fixture_ids:
                            continue

                        status = fixture.get("state", {}).get("short_name", "NS")
                        if status in ["NS", "TBD"]:
                            fixture_info = {
                                "id": fixture.get("id"),
                                "home_team": "Unknown",
                                "away_team": "Unknown",
                                "league": "Unknown",
                                "kickoff": None,
                                "status": status,
                            }

                            participants = fixture.get("participants", [])
                            if isinstance(participants, list) and len(participants) >= 2:
                                fixture_info["home_team"] = participants[0].get("name", "Unknown")
                                fixture_info["away_team"] = participants[1].get("name", "Unknown")

                            if "league" in fixture and isinstance(fixture["league"], dict):
                                fixture_info["league"] = fixture["league"].get("name", "Unknown")

                            if "starting_at" in fixture:
                                fixture_info["kickoff"] = fixture["starting_at"]

                            real_fixtures.append(fixture_info)

        return real_fixtures

    def extract_odds_data(self, raw_data: Dict) -> List[Dict]:
        odds_list: List[Dict] = []

        for key, data in raw_data.items():
            if "odds" in key and isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    for odds_item in data["data"]:
                        if odds_item.get("fixture_id") in self.sample_fixture_ids:
                            continue

                        odds_info = {
                            "fixture_id": odds_item.get("fixture_id"),
                            "market_id": odds_item.get("market_id"),
                            "bookmaker": (odds_item.get("bookmaker") or {}).get("name", "Unknown"),
                            "selections": [],
                        }

                        if "selections" in odds_item and isinstance(odds_item["selections"], list):
                            for selection in odds_item["selections"]:
                                try:
                                    odds_val = float(selection.get("odds", 0))
                                except (ValueError, TypeError):
                                    odds_val = 0.0
                                odds_info["selections"].append(
                                    {
                                        "name": selection.get("name", ""),
                                        "odds": odds_val,
                                    }
                                )

                        if odds_info["selections"]:
                            odds_list.append(odds_info)

        return odds_list

    def generate_value_bets(self, fixtures: List[Dict], odds_data: List[Dict]) -> List[Dict]:
        value_bets: List[Dict] = []

        odds_by_fixture: Dict[int, List[Dict]] = {}
        for odds in odds_data:
            fixture_id = odds.get("fixture_id")
            if fixture_id is None:
                continue
            odds_by_fixture.setdefault(fixture_id, []).append(odds)

        for fixture in fixtures:
            fixture_id = fixture.get("id")
            if fixture_id not in odds_by_fixture:
                continue

            prediction = self.simple_prediction_model(fixture)
            fixture_odds = odds_by_fixture[fixture_id]
            fixture_value_bets = self.find_fixture_value_bets(fixture, prediction, fixture_odds)

            value_bets.extend(fixture_value_bets)

        value_bets.sort(key=lambda x: x.get("edge_percent", 0), reverse=True)
        return value_bets

    def simple_prediction_model(self, fixture: Dict) -> Dict:
        # Placeholder model; replace with your own probabilities
        return {
            "home_win_prob": 0.42,
            "draw_prob": 0.28,
            "away_win_prob": 0.30,
            "over_2_5_prob": 0.58,
            "under_2_5_prob": 0.42,
            "btts_yes_prob": 0.55,
            "btts_no_prob": 0.45,
        }

    def find_fixture_value_bets(self, fixture: Dict, prediction: Dict, fixture_odds: List[Dict]) -> List[Dict]:
        value_bets: List[Dict] = []

        for odds_entry in fixture_odds:
            market_id = odds_entry.get("market_id")

            if market_id == 1:
                bets = self.process_1x2_odds(fixture, prediction, odds_entry)
                value_bets.extend(bets)
            elif market_id == 5:
                bets = self.process_ou_odds(fixture, prediction, odds_entry)
                value_bets.extend(bets)
            elif market_id == 14:
                bets = self.process_btts_odds(fixture, prediction, odds_entry)
                value_bets.extend(bets)

        return value_bets

    def process_1x2_odds(self, fixture: Dict, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        value_bets: List[Dict] = []

        bet_mappings = {
            "home": "home_win_prob",
            "1": "home_win_prob",
            "draw": "draw_prob",
            "x": "draw_prob",
            "away": "away_win_prob",
            "2": "away_win_prob",
        }

        for selection in odds_entry.get("selections", []):
            selection_name = str(selection.get("name", "")).lower()
            odds_value = selection.get("odds", 0)

            try:
                odds_value = float(odds_value)
            except (ValueError, TypeError):
                continue

            if odds_value <= 1.0:
                continue

            prob_key = None
            for name_pattern, prob_k in bet_mappings.items():
                if name_pattern in selection_name:
                    prob_key = prob_k
                    break

            if prob_key:
                predicted_prob = float(prediction.get(prob_key, 0))
                implied_prob = 1.0 / odds_value if odds_value else 0.0
                edge = predicted_prob - implied_prob

                if edge > 0.04:
                    value_bets.append(
                        {
                            "fixture_id": fixture["id"],
                            "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                            "league": fixture["league"],
                            "kickoff": fixture["kickoff"],
                            "market": "1X2",
                            "bet_type": selection.get("name", ""),
                            "odds": odds_value,
                            "predicted_prob": predicted_prob,
                            "implied_prob": implied_prob,
                            "edge": edge,
                            "edge_percent": round(edge * 100, 1),
                            "bookmaker": odds_entry.get("bookmaker", "Unknown"),
                            "recommendation": self.get_recommendation(edge),
                        }
                    )

        return value_bets

    def process_ou_odds(self, fixture: Dict, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        value_bets: List[Dict] = []

        for selection in odds_entry.get("selections", []):
            selection_name = str(selection.get("name", "")).lower()
            odds_value = selection.get("odds", 0)
            try:
                odds_value = float(odds_value)
            except (ValueError, TypeError):
                continue

            if odds_value <= 1.0:
                continue

            if "over" in selection_name:
                predicted_prob = float(prediction.get("over_2_5_prob", 0))
                bet_type = "Over 2.5"
            elif "under" in selection_name:
                predicted_prob = float(prediction.get("under_2_5_prob", 0))
                bet_type = "Under 2.5"
            else:
                continue

            implied_prob = 1.0 / odds_value if odds_value else 0.0
            edge = predicted_prob - implied_prob

            if edge > 0.04:
                value_bets.append(
                    {
                        "fixture_id": fixture["id"],
                        "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                        "league": fixture["league"],
                        "kickoff": fixture["kickoff"],
                        "market": "Over/Under 2.5",
                        "bet_type": bet_type,
                        "odds": odds_value,
                        "predicted_prob": predicted_prob,
                        "implied_prob": implied_prob,
                        "edge": edge,
                        "edge_percent": round(edge * 100, 1),
                        "bookmaker": odds_entry.get("bookmaker", "Unknown"),
                        "recommendation": self.get_recommendation(edge),
                    }
                )

        return value_bets

    def process_btts_odds(self, fixture: Dict, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        value_bets: List[Dict] = []

        for selection in odds_entry.get("selections", []):
            selection_name = str(selection.get("name", "")).lower()
            odds_value = selection.get("odds", 0)
            try:
                odds_value = float(odds_value)
            except (ValueError, TypeError):
                continue

            if odds_value <= 1.0:
                continue

            if "yes" in selection_name or "both" in selection_name:
                predicted_prob = float(prediction.get("btts_yes_prob", 0))
                bet_type = "BTTS Yes"
            elif "no" in selection_name:
                predicted_prob = float(prediction.get("btts_no_prob", 0))
                bet_type = "BTTS No"
            else:
                continue

            implied_prob = 1.0 / odds_value if odds_value else 0.0
            edge = predicted_prob - implied_prob

            if edge > 0.04:
                value_bets.append(
                    {
                        "fixture_id": fixture["id"],
                        "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                        "league": fixture["league"],
                        "kickoff": fixture["kickoff"],
                        "market": "Both Teams to Score",
                        "bet_type": bet_type,
                        "odds": odds_value,
                        "predicted_prob": predicted_prob,
                        "implied_prob": implied_prob,
                        "edge": edge,
                        "edge_percent": round(edge * 100, 1),
                        "bookmaker": odds_entry.get("bookmaker", "Unknown"),
                        "recommendation": self.get_recommendation(edge),
                    }
                )

        return value_bets

    def get_recommendation(self, edge: float) -> str:
        if edge > 0.15:
            return "STRONG BUY"
        elif edge > 0.10:
            return "BUY"
        elif edge > 0.06:
            return "CONSIDER"
        else:
            return "WEAK VALUE"


class BettingBot:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_url = "https://api.sportmonks.com/v3/odds"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
            }
        )

        self.value_finder = QuickValueBetFinder()
        self.raw_data: Dict[str, Dict] = {}
        self.last_analysis: Optional[Dict] = None

    def _request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        try:
            request_params = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            response = self.session.get(url, params=request_params, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API request failed: {response.status_code} - {url}")
                return None

        except Exception as e:
            logger.error(f"API request error: {e}")
            return None

    def fetch_data(self):
        logger.info("Fetching SportMonks data...")

        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Upcoming fixtures
        today_data = self._request(f"{self.base_url}/fixtures/date/{today}", {"include": "participants,league"})
        if today_data:
            self.raw_data[f"upcoming_{today}"] = today_data

        tomorrow_data = self._request(f"{self.base_url}/fixtures/date/{tomorrow}", {"include": "participants,league"})
        if tomorrow_data:
            self.raw_data[f"upcoming_{tomorrow}"] = tomorrow_data

        # Live scores
        live_data = self._request(f"{self.base_url}/livescores")
        if live_data:
            self.raw_data["live_scores"] = live_data

        # Bookmakers
        bookmakers_data = self._request(f"{self.odds_url}/bookmakers")
        if bookmakers_data:
            self.raw_data["bookmakers"] = bookmakers_data

        # Pre-match odds
        odds_data = self._request(f"{self.odds_url}/pre-match", {"per_page": "100"})
        if odds_data:
            self.raw_data["pre_match_odds"] = odds_data

        logger.info(f"Fetched data for {len(self.raw_data)} endpoints")

    def analyze_opportunities(self):
        logger.info("Analyzing betting opportunities...")

        if not self.raw_data:
            self.fetch_data()

        self.last_analysis = self.value_finder.find_real_betting_opportunities(self.raw_data)

        summary = self.last_analysis["summary"]
        value_bets = self.last_analysis["value_bets"]

        logger.info(f"ANALYSIS COMPLETE: {summary['summary_text']}")

        if value_bets:
            top = value_bets[0]
            logger.info(
                f"BEST VALUE BET: {top['match']} - {top['bet_type']} @ {top['odds']} ({top['edge_percent']}% edge)"
            )
            for bet in value_bets[:3]:
                logger.info(
                    f"VALUE BET: {bet['match']} | {bet['bet_type']} @ {bet['odds']} | {bet['edge_percent']}% edge | {bet['recommendation']}"
                )
        else:
            logger.info("No value betting opportunities found")

        return self.last_analysis

    def get_dashboard_data(self):
        if not self.last_analysis:
            self.analyze_opportunities()

        return {
            "status": "active",
            "last_update": datetime.now().isoformat(),
            "summary": self.last_analysis["summary"],
            "value_bets": self.last_analysis["value_bets"][:10],
            "total_opportunities": len(self.last_analysis["value_bets"]),
        }


# Flask App
app = Flask(__name__)
bot: Optional[BettingBot] = None


@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>AI Betting Bot</title>
<style>
body { font-family: Arial, sans-serif; background: #0f172a; color: #f1f5f9; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #10b981; text-align: center; }
.card { background: #1e293b; padding: 20px; margin: 20px 0; border-radius: 8px; }
.btn { background: #3b82f6; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
.btn:hover { background: #2563eb; }
input { background: #374151; color: white; border: 1px solid #4b5563; padding: 10px; width: 300px; border-radius: 4px; }
.bet-card { background: #065f46; padding: 15px; margin: 10px 0; border-radius: 6px; border-left: 4px solid #10b981; }
.edge { color: #10b981; font-weight: bold; }
</style>
</head>
<body>
<div class="container">
<h1>🤖 AI Betting Bot</h1>
    <div class="card">
        <h3>Setup</h3>
        <input id="apiToken" type="text" placeholder="Enter SportMonks API Token...">
        <button class="btn" onclick="setupBot()">Initialize Bot</button>
    </div>

    <div class="card">
        <h3>Controls</h3>
        <button class="btn" onclick="analyzeOpportunities()">Analyze Opportunities</button>
        <button class="btn" onclick="refreshDashboard()">Refresh Dashboard</button>
    </div>

    <div class="card">
        <h3>Value Betting Opportunities</h3>
        <div id="opportunities">Click "Analyze Opportunities" to find value bets</div>
    </div>
</div>

<script>
async function setupBot() {
    const token = document.getElementById('apiToken').value;
    if (!token) { alert('Enter API token'); return; }

    try {
        const response = await fetch('/api/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        const data = await response.json();
        alert(data.success ? 'Bot initialized!' : 'Error: ' + (data.error || 'unknown'));
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function analyzeOpportunities() {
    try {
        const response = await fetch('/api/analyze', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            refreshDashboard();
        } else {
            alert('Error: ' + (data.error || 'unknown'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function refreshDashboard() {
    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();
        displayOpportunities(data);
    } catch (error) {
        document.getElementById('opportunities').innerHTML = 'Error loading data';
    }
}

function displayOpportunities(data) {
    const container = document.getElementById('opportunities');

    if (!data.value_bets || data.value_bets.length === 0) {
        container.innerHTML = '<p>No value betting opportunities found</p>';
        return;
    }

    let html = `<p><strong>Found ${data.total_opportunities} value betting opportunities!</strong></p>`;

    data.value_bets.forEach(bet => {
        html += `
            <div class="bet-card">
                <strong>${bet.match}</strong> (${bet.league})<br>
                <strong>${bet.bet_type}</strong> @ ${bet.odds}
                <span class="edge">${bet.edge_percent}% edge</span><br>
                Bookmaker: ${bet.bookmaker} | ${bet.recommendation}
            </div>
        `;
    });

    container.innerHTML = html;
}
</script>
</body>
</html>
"""


@app.route("/api/setup", methods=["POST"])
def setup():
    global bot
    data = request.get_json(silent=True) or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"error": "API token required"}), 400

    try:
        bot = BettingBot(api_token)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized"}), 400

    try:
        bot.analyze_opportunities()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard")
def dashboard():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized"}), 400

    try:
        return jsonify(bot.get_dashboard_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# Gunicorn compatibility
application = app