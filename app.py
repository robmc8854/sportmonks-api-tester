#!/usr/bin/env python3
"""
WORKING SPORTMONKS BETTING PREDICTOR
Fixed authentication and API endpoints based on official SportMonks v3 documentation.
"""

import json
import logging
import os
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkingSportMonksAPI:
    def __init__(self, api_token: str):
        self.api_token = api_token.strip()
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.session = requests.Session()
        # Use proper Authorization header as per SportMonks docs
        self.session.headers.update({
            "Authorization": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request using correct SportMonks v3 format"""
        try:
            url = f"{self.base_url}/{endpoint}"

            # Add api_token to query params as backup (SportMonks supports both methods)
            query_params = {"api_token": self.api_token}
            if params:
                query_params.update(params)

            response = self.session.get(url, params=query_params, timeout=30)

            logger.info(f"Request: {url} - Status: {response.status_code}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error("401 Unauthorized - Check your API token")
                return {"error": "Invalid API token"}
            elif response.status_code == 403:
                logger.error("403 Forbidden - Endpoint not available on your plan")
                return {"error": "Endpoint not available on your plan"}
            elif response.status_code == 429:
                logger.error("429 Rate Limited - Too many requests")
                return {"error": "Rate limit exceeded"}
            else:
                logger.error(f"API Error {response.status_code}: {response.text}")
                return {"error": f"API Error {response.status_code}"}

        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}

    def test_connection(self) -> Dict:
        """Test basic connection with simplest endpoint"""
        # Try the simplest endpoint first - leagues
        result = self.make_request("leagues", {"per_page": "5"})
        return result

    def get_live_scores(self) -> Dict:
        """Get current live scores"""
        return self.make_request("livescores")

    def get_todays_fixtures(self) -> Dict:
        """Get today's fixtures"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.make_request(f"fixtures/date/{today}")

    def get_tomorrows_fixtures(self) -> Dict:
        """Get tomorrow's fixtures"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        return self.make_request(f"fixtures/date/{tomorrow}")

    def get_fixture_details(self, fixture_id: int) -> Dict:
        """Get detailed fixture information with includes"""
        return self.make_request(f"fixtures/{fixture_id}", {
            "include": "participants,league,venue,state,scores"
        })

    def get_team_details(self, team_id: int) -> Dict:
        """Get team information"""
        return self.make_request(f"teams/{team_id}")

    def get_recent_fixtures_for_team(self, team_id: int, limit: int = 5) -> Dict:
        """Get recent fixtures for a team"""
        return self.make_request(f"teams/{team_id}/fixtures", {
            "per_page": str(limit),
            "include": "scores,participants"
        })

    def analyze_team_form(self, fixtures_data: Dict) -> Dict:
        """Analyze team form from fixtures data"""
        if not fixtures_data or "data" not in fixtures_data:
            return {"wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "form": "No data"}

        wins = draws = losses = goals_for = goals_against = 0

        for fixture in fixtures_data["data"]:
            # Only count finished matches
            state = fixture.get("state", {})
            if not state or state.get("state") != "FT":
                continue

            # Get scores
            scores = fixture.get("scores", [])
            home_score = away_score = 0

            for score in scores:
                if score.get("description") == "CURRENT":
                    home_score = score.get("score", {}).get("home", 0) or 0
                    away_score = score.get("score", {}).get("away", 0) or 0
                    break

            # For now, assume we're analyzing home team (can be improved)
            goals_for += home_score
            goals_against += away_score

            if home_score > away_score:
                wins += 1
            elif home_score == away_score:
                draws += 1
            else:
                losses += 1

        total_games = wins + draws + losses
        if total_games > 0:
            win_rate = (wins / total_games) * 100
            form = "Excellent" if win_rate >= 80 else "Good" if win_rate >= 60 else "Average" if win_rate >= 40 else "Poor"
        else:
            form = "No recent games"

        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "total_games": total_games,
            "form": form,
            "win_rate": round((wins / total_games * 100) if total_games > 0 else 0, 1)
        }

    def predict_match_outcome(self, home_team_form: Dict, away_team_form: Dict) -> Dict:
        """Simple prediction based on team form"""
        home_strength = home_team_form.get("win_rate", 0) / 100
        away_strength = away_team_form.get("win_rate", 0) / 100

        # Add home advantage
        home_strength += 0.1

        # Calculate probabilities
        total_strength = home_strength + away_strength
        if total_strength == 0:
            home_win_prob = away_win_prob = draw_prob = 33.33
        else:
            home_win_prob = (home_strength / total_strength) * 70  # 70% distributed between teams
            away_win_prob = (away_strength / total_strength) * 70
            draw_prob = 30  # 30% draw probability

        # Normalize to 100%
        total_prob = home_win_prob + away_win_prob + draw_prob
        if total_prob > 0:
            home_win_prob = (home_win_prob / total_prob) * 100
            away_win_prob = (away_win_prob / total_prob) * 100
            draw_prob = (draw_prob / total_prob) * 100

        # Determine prediction
        if home_win_prob > away_win_prob and home_win_prob > draw_prob:
            prediction = "HOME_WIN"
            confidence = home_win_prob
        elif away_win_prob > draw_prob:
            prediction = "AWAY_WIN"
            confidence = away_win_prob
        else:
            prediction = "DRAW"
            confidence = draw_prob

        return {
            "prediction": prediction,
            "confidence": round(confidence, 1),
            "probabilities": {
                "home_win": round(home_win_prob, 1),
                "draw": round(draw_prob, 1),
                "away_win": round(away_win_prob, 1)
            }
        }

    def generate_betting_predictions(self) -> List[Dict]:
        """Generate betting predictions for upcoming matches"""
        predictions = []

        # Get tomorrow's fixtures
        fixtures = self.get_tomorrows_fixtures()
        if not fixtures or "data" not in fixtures:
            logger.warning("No fixtures data available")
            return []

        # Limit to first 10 fixtures for performance
        fixture_list = fixtures["data"][:10]

        for fixture in fixture_list:
            try:
                # Get fixture details with participants
                fixture_details = self.get_fixture_details(fixture["id"])

                if not fixture_details or "data" not in fixture_details:
                    continue

                fixture_data = fixture_details["data"]
                participants = fixture_data.get("participants", [])

                if len(participants) < 2:
                    continue

                home_team = away_team = None
                for participant in participants:
                    if participant.get("meta", {}).get("location") == "home":
                        home_team = participant
                    else:
                        away_team = participant

                if not home_team or not away_team:
                    continue

                # Get team forms
                home_fixtures = self.get_recent_fixtures_for_team(home_team["id"], 5)
                away_fixtures = self.get_recent_fixtures_for_team(away_team["id"], 5)

                home_form = self.analyze_team_form(home_fixtures)
                away_form = self.analyze_team_form(away_fixtures)

                # Generate prediction
                prediction = self.predict_match_outcome(home_form, away_form)

                # Only include predictions with reasonable confidence
                if prediction["confidence"] > 35:
                    predictions.append({
                        "fixture_id": fixture["id"],
                        "home_team": home_team.get("name", "Unknown"),
                        "away_team": away_team.get("name", "Unknown"),
                        "league": fixture_data.get("league", {}).get("name", "Unknown"),
                        "kickoff": fixture.get("starting_at", "Unknown"),
                        "prediction": prediction["prediction"],
                        "confidence": prediction["confidence"],
                        "probabilities": prediction["probabilities"],
                        "home_form": home_form,
                        "away_form": away_form
                    })

            except Exception as e:
                logger.error(f"Error processing fixture {fixture.get('id')}: {str(e)}")
                continue

        # Sort by confidence
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        return predictions


# Flask App
app = Flask(__name__)
api: Optional[WorkingSportMonksAPI] = None


@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>Working SportMonks Betting App</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #2c3e50; text-align: center; }
.card { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.btn { background: #3498db; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; font-weight: bold; }
.btn:hover { background: #2980b9; }
.btn.success { background: #27ae60; }
.btn.danger { background: #e74c3c; }
.btn.warning { background: #f39c12; }
input[type="password"] { padding: 12px; border: 1px solid #ddd; border-radius: 4px; width: 300px; margin-right: 10px; }
.prediction { border-left: 4px solid #3498db; padding: 15px; margin: 10px 0; background: #ecf0f1; border-radius: 4px; }
.high-confidence { border-left-color: #27ae60; background: #d5f4e6; }
.medium-confidence { border-left-color: #f39c12; background: #fef9e7; }
.low-confidence { border-left-color: #e74c3c; background: #fdf2f2; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }
.stat { background: #34495e; color: white; padding: 10px; border-radius: 4px; text-align: center; }
.loading { text-align: center; color: #7f8c8d; padding: 20px; }
.error { color: #e74c3c; background: #fdf2f2; padding: 15px; border-radius: 4px; margin: 10px 0; }
.success { color: #27ae60; background: #f0fff4; padding: 15px; border-radius: 4px; margin: 10px 0; }
.warning { color: #f39c12; background: #fef9e7; padding: 15px; border-radius: 4px; margin: 10px 0; }
.test-results { background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 4px; font-family: monospace; margin: 10px 0; }
</style>
</head>
<body>
<div class="container">
<h1>⚽ Working SportMonks Betting App</h1>
<p style="text-align: center; color: #7f8c8d;">Fixed authentication and API endpoints based on official SportMonks v3 documentation</p>

<div class="card">
    <h2>🔐 Setup & Test Connection</h2>
    <input type="password" id="apiToken" placeholder="Enter SportMonks API Token">
    <br><br>
    <button class="btn success" onclick="testConnection()">🧪 Test API Connection</button>
    <button class="btn" onclick="initializeAPI()">✅ Initialize API</button>
    <div id="connectionStatus"></div>
</div>

<div class="card">
    <h2>📊 Available Data</h2>
    <button class="btn" onclick="getLiveScores()">🔴 Live Scores</button>
    <button class="btn" onclick="getTodaysFixtures()">📅 Today's Fixtures</button>
    <button class="btn" onclick="getTomorrowsFixtures()">📅 Tomorrow's Fixtures</button>
    <div id="dataResults"></div>
</div>

<div class="card">
    <h2>🎯 Betting Predictions</h2>
    <button class="btn warning" onclick="generatePredictions()">🚀 Generate Betting Predictions</button>
    <div id="predictionStatus"></div>
    <div id="predictions"></div>
</div>

<div class="card">
    <h2>📈 Statistics</h2>
    <div id="stats">No statistics available yet</div>
</div>
</div>

<script>
async function testConnection() {
    const token = document.getElementById('apiToken').value.trim();
    if (!token) {
        document.getElementById('connectionStatus').innerHTML = '<div class="error">Please enter your API token</div>';
        return;
    }
    
    document.getElementById('connectionStatus').innerHTML = '<div class="loading">Testing connection...</div>';
    
    try {
        const response = await fetch('/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('connectionStatus').innerHTML = '<div class="success">✅ Connection successful! Found ' + data.leagues_count + ' leagues</div>';
        } else {
            document.getElementById('connectionStatus').innerHTML = '<div class="error">❌ Connection failed: ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('connectionStatus').innerHTML = '<div class="error">❌ Network error: ' + error.message + '</div>';
    }
}

async function initializeAPI() {
    const token = document.getElementById('apiToken').value.trim();
    if (!token) {
        document.getElementById('connectionStatus').innerHTML = '<div class="error">Please enter your API token</div>';
        return;
    }
    
    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('connectionStatus').innerHTML = '<div class="success">✅ API initialized successfully!</div>';
        } else {
            document.getElementById('connectionStatus').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('connectionStatus').innerHTML = '<div class="error">❌ Network error: ' + error.message + '</div>';
    }
}

async function getLiveScores() {
    try {
        const response = await fetch('/api/live-scores');
        const data = await response.json();
        
        if (data.success) {
            displayDataResults('Live Scores', data.data);
        } else {
            document.getElementById('dataResults').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('dataResults').innerHTML = '<div class="error">❌ Error: ' + error.message + '</div>';
    }
}

async function getTodaysFixtures() {
    try {
        const response = await fetch('/api/todays-fixtures');
        const data = await response.json();
        
        if (data.success) {
            displayDataResults('Today\\'s Fixtures', data.data);
        } else {
            document.getElementById('dataResults').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('dataResults').innerHTML = '<div class="error">❌ Error: ' + error.message + '</div>';
    }
}

async function getTomorrowsFixtures() {
    try {
        const response = await fetch('/api/tomorrows-fixtures');
        const data = await response.json();
        
        if (data.success) {
            displayDataResults('Tomorrow\\'s Fixtures', data.data);
        } else {
            document.getElementById('dataResults').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('dataResults').innerHTML = '<div class="error">❌ Error: ' + error.message + '</div>';
    }
}

function displayDataResults(title, data) {
    if (!data || !data.data) {
        document.getElementById('dataResults').innerHTML = '<div class="warning">No ' + title.toLowerCase() + ' available</div>';
        return;
    }
    
    const items = data.data;
    let html = '<div class="test-results"><h3>' + title + ' (' + items.length + ' found)</h3>';
    
    items.slice(0, 5).forEach(item => {
        html += '<div style="margin: 10px 0; padding: 10px; background: #34495e; border-radius: 4px;">';
        html += '<strong>' + (item.name || 'Item') + '</strong><br>';
        if (item.participants) {
            const home = item.participants.find(p => p.meta && p.meta.location === 'home');
            const away = item.participants.find(p => p.meta && p.meta.location === 'away');
            html += (home ? home.name : 'Home') + ' vs ' + (away ? away.name : 'Away') + '<br>';
        }
        html += 'ID: ' + item.id;
        html += '</div>';
    });
    
    html += '</div>';
    document.getElementById('dataResults').innerHTML = html;
}

async function generatePredictions() {
    document.getElementById('predictionStatus').innerHTML = '<div class="loading">🔍 Generating betting predictions... This may take a moment...</div>';
    document.getElementById('predictions').innerHTML = '<div class="loading">Analyzing matches...</div>';
    
    try {
        const response = await fetch('/api/predictions', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            displayPredictions(data.predictions);
            displayStats(data.stats);
            document.getElementById('predictionStatus').innerHTML = '<div class="success">✅ ' + data.predictions.length + ' predictions generated!</div>';
        } else {
            document.getElementById('predictionStatus').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
            document.getElementById('predictions').innerHTML = '<div class="error">Failed to generate predictions</div>';
        }
    } catch (error) {
        document.getElementById('predictionStatus').innerHTML = '<div class="error">❌ Error: ' + error.message + '</div>';
    }
}

function displayPredictions(predictions) {
    if (!predictions || predictions.length === 0) {
        document.getElementById('predictions').innerHTML = '<div class="warning">No predictions available for tomorrow\\'s matches</div>';
        return;
    }
    
    let html = '';
    predictions.forEach(pred => {
        const confidenceClass = pred.confidence >= 60 ? 'high-confidence' : pred.confidence >= 45 ? 'medium-confidence' : 'low-confidence';
        
        html += `
            <div class="prediction ${confidenceClass}">
                <h3>${pred.home_team} vs ${pred.away_team}</h3>
                <div class="stats">
                    <div class="stat">
                        <strong>Prediction</strong><br>
                        ${pred.prediction.replace('_', ' ')}
                    </div>
                    <div class="stat">
                        <strong>Confidence</strong><br>
                        ${pred.confidence}%
                    </div>
                    <div class="stat">
                        <strong>League</strong><br>
                        ${pred.league}
                    </div>
                    <div class="stat">
                        <strong>Kickoff</strong><br>
                        ${new Date(pred.kickoff).toLocaleString()}
                    </div>
                </div>
                <div class="stats">
                    <div class="stat">
                        <strong>Home Win</strong><br>
                        ${pred.probabilities.home_win}%
                    </div>
                    <div class="stat">
                        <strong>Draw</strong><br>
                        ${pred.probabilities.draw}%
                    </div>
                    <div class="stat">
                        <strong>Away Win</strong><br>
                        ${pred.probabilities.away_win}%
                    </div>
                </div>
                <p><strong>Form Analysis:</strong> ${pred.home_team}: ${pred.home_form.form} (${pred.home_form.wins}W-${pred.home_form.draws}D-${pred.home_form.losses}L), ${pred.away_team}: ${pred.away_form.form} (${pred.away_form.wins}W-${pred.away_form.draws}D-${pred.away_form.losses}L)</p>
            </div>
        `;
    });
    
    document.getElementById('predictions').innerHTML = html;
}

function displayStats(stats) {
    if (!stats) return;
    
    const html = `
        <div class="stats">
            <div class="stat">
                <strong>Total Predictions</strong><br>
                ${stats.total_predictions}
            </div>
            <div class="stat">
                <strong>High Confidence</strong><br>
                ${stats.high_confidence}
            </div>
            <div class="stat">
                <strong>Average Confidence</strong><br>
                ${stats.avg_confidence}%
            </div>
            <div class="stat">
                <strong>Last Updated</strong><br>
                ${new Date().toLocaleTimeString()}
            </div>
        </div>
    `;
    
    document.getElementById('stats').innerHTML = html;
}
</script>

</body>
</html>
    """


@app.route("/api/test-connection", methods=["POST"])
def test_connection():
    data = request.get_json() or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"success": False, "error": "API token required"})

    try:
        test_api = WorkingSportMonksAPI(api_token)
        result = test_api.test_connection()

        if "error" in result:
            return jsonify({"success": False, "error": result["error"]})

        leagues_count = len(result.get("data", [])) if result.get("data") else 0
        return jsonify({"success": True, "leagues_count": leagues_count, "data": result})

    except Exception as e:
        return jsonify({"success": False, "error": f"Test failed: {str(e)}"})


@app.route("/api/init", methods=["POST"])
def init_api():
    global api
    data = request.get_json() or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"success": False, "error": "API token required"})

    try:
        api = WorkingSportMonksAPI(api_token)
        # Test the connection
        test_result = api.test_connection()

        if "error" in test_result:
            return jsonify({"success": False, "error": test_result["error"]})

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": f"Initialization failed: {str(e)}"})


@app.route("/api/live-scores")
def live_scores():
    global api
    if not api:
        return jsonify({"success": False, "error": "API not initialized"})

    try:
        result = api.get_live_scores()
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]})
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/todays-fixtures")
def todays_fixtures():
    global api
    if not api:
        return jsonify({"success": False, "error": "API not initialized"})

    try:
        result = api.get_todays_fixtures()
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]})
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/tomorrows-fixtures")
def tomorrows_fixtures():
    global api
    if not api:
        return jsonify({"success": False, "error": "API not initialized"})

    try:
        result = api.get_tomorrows_fixtures()
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]})
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/predictions", methods=["POST"])
def get_predictions():
    global api
    if not api:
        return jsonify({"success": False, "error": "API not initialized"})

    try:
        predictions = api.generate_betting_predictions()

        # Calculate stats
        total_predictions = len(predictions)
        high_confidence = len([p for p in predictions if p["confidence"] >= 60])
        avg_confidence = round(sum(p["confidence"] for p in predictions) / total_predictions if total_predictions > 0 else 0, 1)

        stats = {
            "total_predictions": total_predictions,
            "high_confidence": high_confidence,
            "avg_confidence": avg_confidence
        }

        return jsonify({
            "success": True,
            "predictions": predictions,
            "stats": stats
        })
    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        return jsonify({"success": False, "error": f"Failed to generate predictions: {str(e)}"})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

# For Gunicorn
application = app