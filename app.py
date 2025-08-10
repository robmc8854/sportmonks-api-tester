#!/usr/bin/env python3
"""
SPORTMONKS BETTING PREDICTOR
Complete working app that fetches real data and makes betting predictions.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BettingPredictor:
    def __init__(self, api_token: str):
        self.api_token = api_token.strip()
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json"
        })

    def make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make API request with error handling"""
        try:
            url = f"{self.base_url}/{endpoint}"
            query_params = {"api_token": self.api_token}
            if params:
                query_params.update(params)

            response = self.session.get(url, params=query_params, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API Error {response.status_code}: {response.text}")
                return {}
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {}

    def get_upcoming_fixtures(self, days_ahead: int = 2) -> List[Dict[str, Any]]:
        """Get upcoming fixtures for prediction"""
        fixtures: List[Dict[str, Any]] = []

        for i in range(days_ahead):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            data = self.make_request(f"fixtures/date/{date}")

            if data and "data" in data:
                for fixture in data["data"]:
                    if fixture.get("state", {}).get("state") in ["NS", "TIMED"]:  # Not started
                        fixtures.append(fixture)

        return fixtures[:50]  # Limit to 50 fixtures

    def get_team_form(self, team_id: int, limit: int = 5) -> Dict[str, Any]:
        """Get recent team performance"""
        data = self.make_request(f"teams/{team_id}/fixtures", {"per_page": str(limit)})

        if not data or "data" not in data:
            return {"wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "games_played": 0}

        wins = draws = losses = goals_for = goals_against = 0

        for fixture in data["data"]:
            if fixture.get("state", {}).get("state") != "FT":  # Only finished games
                continue

            scores = fixture.get("scores", [])
            if not scores:
                continue

            home_score = away_score = 0
            for score in scores:
                if score.get("description") == "CURRENT":
                    home_score = score.get("score", {}).get("home", 0) or 0
                    away_score = score.get("score", {}).get("away", 0) or 0
                    break

            # Determine if this team was home or away
            participants = fixture.get("participants", [])
            is_home = False
            for p in participants:
                if p.get("id") == team_id and p.get("meta", {}).get("location") == "home":
                    is_home = True
                    break

            if is_home:
                goals_for += home_score
                goals_against += away_score
                if home_score > away_score:
                    wins += 1
                elif home_score == away_score:
                    draws += 1
                else:
                    losses += 1
            else:
                goals_for += away_score
                goals_against += home_score
                if away_score > home_score:
                    wins += 1
                elif away_score == home_score:
                    draws += 1
                else:
                    losses += 1

        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "games_played": wins + draws + losses
        }

    def calculate_team_strength(self, form: Dict[str, Any]) -> float:
        """Calculate team strength based on recent form"""
        games = form["games_played"]
        if games == 0:
            return 0.5  # Neutral

        # Points system: 3 for win, 1 for draw, 0 for loss
        points = (form["wins"] * 3) + form["draws"]
        max_points = games * 3

        # Goal difference factor
        goal_diff = form["goals_for"] - form["goals_against"]
        goal_factor = min(max(goal_diff / games, -2), 2) / 4  # Normalize between -0.5 and 0.5

        # Base strength from points
        base_strength = points / max_points if max_points > 0 else 0.5

        # Combine with goal factor
        strength = base_strength + goal_factor

        return min(max(strength, 0), 1)  # Keep between 0 and 1

    def predict_match(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        """Predict match outcome"""
        participants = fixture.get("participants", [])
        if len(participants) < 2:
            return {"error": "Insufficient participant data"}

        home_team = None
        away_team = None
        for p in participants:
            if p.get("meta", {}).get("location") == "home":
                home_team = p
            else:
                away_team = p

        if not home_team or not away_team:
            return {"error": "Could not identify home/away teams"}

        # Get team forms
        home_form = self.get_team_form(int(home_team["id"]))
        away_form = self.get_team_form(int(away_team["id"]))

        # Calculate strengths
        home_strength = self.calculate_team_strength(home_form)
        away_strength = self.calculate_team_strength(away_form)

        # Home advantage
        home_advantage = 0.1
        adjusted_home = min(home_strength + home_advantage, 1.0)

        # Calculate probabilities
        total_strength = adjusted_home + away_strength
        if total_strength == 0:
            home_win_prob = away_win_prob = draw_prob = 0.33
        else:
            # 80% allocated to decisive outcomes, 20% to draw baseline
            home_win_prob = adjusted_home / total_strength * 0.8
            away_win_prob = away_strength / total_strength * 0.8
            draw_prob = 0.2

        # Normalize to 100%
        total_prob = home_win_prob + away_win_prob + draw_prob
        if total_prob > 0:
            home_win_prob /= total_prob
            away_win_prob /= total_prob
            draw_prob /= total_prob

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

        # Score prediction based on average goals
        home_avg_goals = home_form["goals_for"] / max(home_form["games_played"], 1)
        away_avg_goals = away_form["goals_for"] / max(away_form["games_played"], 1)

        # Adjust for opponent defense
        home_goals_against_avg = home_form["goals_against"] / max(home_form["games_played"], 1)
        away_goals_against_avg = away_form["goals_against"] / max(away_form["games_played"], 1)

        predicted_home_score = round((home_avg_goals + away_goals_against_avg) / 2 + 0.1)  # Home advantage
        predicted_away_score = round((away_avg_goals + home_goals_against_avg) / 2)

        return {
            "fixture_id": fixture.get("id"),
            "home_team": home_team.get("name"),
            "away_team": away_team.get("name"),
            "kickoff": fixture.get("starting_at"),
            "league": fixture.get("league", {}).get("name", "Unknown"),
            "prediction": prediction,
            "confidence": round(confidence * 100, 1),
            "probabilities": {
                "home_win": round(home_win_prob * 100, 1),
                "draw": round(draw_prob * 100, 1),
                "away_win": round(away_win_prob * 100, 1)
            },
            "predicted_score": f"{predicted_home_score}-{predicted_away_score}",
            "home_form": home_form,
            "away_form": away_form,
            "home_strength": round(home_strength, 3),
            "away_strength": round(away_strength, 3)
        }

    def get_betting_tips(self) -> List[Dict[str, Any]]:
        """Get betting predictions for upcoming matches"""
        fixtures = self.get_upcoming_fixtures()
        predictions: List[Dict[str, Any]] = []

        for fixture in fixtures:
            try:
                prediction = self.predict_match(fixture)
                if "error" not in prediction and prediction["confidence"] > 60:
                    predictions.append(prediction)
            except Exception as e:
                logger.error(f"Error predicting match {fixture.get('id')}: {str(e)}")
                continue

        # Sort by confidence
        predictions.sort(key=lambda x: x["confidence"], reverse=True)
        return predictions[:20]  # Top 20 predictions


# Flask App
app = Flask(__name__)
predictor: Optional[BettingPredictor] = None


@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>SportMonks Betting Predictor</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #2c3e50; text-align: center; }
.card { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.btn { background: #3498db; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
.btn:hover { background: #2980b9; }
.btn.success { background: #27ae60; }
.btn.danger { background: #e74c3c; }
input[type="password"] { padding: 12px; border: 1px solid #ddd; border-radius: 4px; width: 300px; margin-right: 10px; }
.prediction { border-left: 4px solid #3498db; padding: 15px; margin: 10px 0; background: #ecf0f1; }
.high-confidence { border-left-color: #27ae60; }
.medium-confidence { border-left-color: #f39c12; }
.low-confidence { border-left-color: #e74c3c; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }
.stat { background: #34495e; color: white; padding: 10px; border-radius: 4px; text-align: center; }
.loading { text-align: center; color: #7f8c8d; }
.error { color: #e74c3c; background: #fdf2f2; padding: 10px; border-radius: 4px; }
.success { color: #27ae60; background: #f0fff4; padding: 10px; border-radius: 4px; }
</style>
</head>
<body>
<div class="container">
<h1>⚽ SportMonks Betting Predictor</h1>

<div class="card">
    <h2>🔐 Setup</h2>
    <input type="password" id="apiToken" placeholder="Enter SportMonks API Token">
    <button class="btn" onclick="initializePredictor()">Initialize Predictor</button>
    <div id="initStatus"></div>
</div>

<div class="card">
    <h2>🎯 Get Betting Predictions</h2>
    <button class="btn success" onclick="getPredictions()">Generate Predictions</button>
    <button class="btn" onclick="refreshData()">Refresh Data</button>
    <div id="predictionStatus"></div>
</div>

<div class="card">
    <h2>📊 Betting Tips</h2>
    <div id="predictions">Click "Generate Predictions" to see betting tips</div>
</div>

<div class="card">
    <h2>📈 Statistics</h2>
    <div id="stats">No statistics available yet</div>
</div>
</div>

<script>
async function initializePredictor() {
    const token = document.getElementById('apiToken').value.trim();
    if (!token) {
        document.getElementById('initStatus').innerHTML = '<div class="error">Please enter your API token</div>';
        return;
    }

    document.getElementById('initStatus').innerHTML = '<div class="loading">Initializing predictor...</div>';

    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });

        const data = await response.json();

        if (data.success) {
            document.getElementById('initStatus').innerHTML = '<div class="success">✅ Predictor initialized successfully!</div>';
        } else {
            document.getElementById('initStatus').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('initStatus').innerHTML = '<div class="error">❌ Network error: ' + error.message + '</div>';
    }
}

async function getPredictions() {
    document.getElementById('predictionStatus').innerHTML = '<div class="loading">🔍 Analyzing matches and generating predictions...</div>';
    document.getElementById('predictions').innerHTML = '<div class="loading">Processing data...</div>';

    try {
        const response = await fetch('/api/predictions', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            displayPredictions(data.predictions);
            displayStats(data.stats);
            document.getElementById('predictionStatus').innerHTML = '<div class="success">✅ Predictions generated successfully!</div>';
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
        document.getElementById('predictions').innerHTML = '<div class="error">No predictions available. This could mean:<ul><li>No upcoming matches found</li><li>API token has limited access</li><li>SportMonks plan doesn\\'t include required data</li></ul></div>';
        return;
    }

    let html = '';
    predictions.forEach(pred => {
        const confidenceClass = pred.confidence >= 70 ? 'high-confidence' : pred.confidence >= 60 ? 'medium-confidence' : 'low-confidence';

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
                        <strong>Score Prediction</strong><br>
                        ${pred.predicted_score}
                    </div>
                    <div class="stat">
                        <strong>League</strong><br>
                        ${pred.league}
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
                    <div class="stat">
                        <strong>Kickoff</strong><br>
                        ${new Date(pred.kickoff).toLocaleString()}
                    </div>
                </div>
                <p><strong>Analysis:</strong> Home form: ${pred.home_form.wins}W-${pred.home_form.draws}D-${pred.home_form.losses}L, Away form: ${pred.away_form.wins}W-${pred.away_form.draws}D-${pred.away_form.losses}L</p>
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
                <strong>Avg Confidence</strong><br>
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

function refreshData() {
    getPredictions();
}
</script>

</body>
</html>
    """


@app.route("/api/init", methods=["POST"])
def init_predictor():
    global predictor
    data = request.get_json() or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"success": False, "error": "API token required"})

    try:
        predictor = BettingPredictor(api_token)
        # Test the connection
        test = predictor.make_request("leagues", {"per_page": "1"})
        if not test:
            return jsonify({"success": False, "error": "Failed to connect to SportMonks API. Check your token."})

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": f"Initialization failed: {str(e)}"})


@app.route("/api/predictions", methods=["POST"])
def get_predictions():
    global predictor

    if not predictor:
        return jsonify({"success": False, "error": "Predictor not initialized"})

    try:
        predictions = predictor.get_betting_tips()

        # Calculate stats
        total_predictions = len(predictions)
        high_confidence = len([p for p in predictions if p["confidence"] >= 70])
        avg_confidence = round(
            sum(p["confidence"] for p in predictions) / total_predictions if total_predictions > 0 else 0, 1
        )

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