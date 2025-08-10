#!/usr/bin/env python3
"""
WORKING SPORTMONKS BETTING PREDICTOR - USING REAL AVAILABLE DATA
Uses the 55 working endpoints to build actual betting predictions.
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


class RealDataPredictor:
    def __init__(self, api_token: str):
        self.api_token = api_token.strip()
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request using working endpoints only"""
        try:
            url = f"{self.base_url}/{endpoint}"
            query_params = {"api_token": self.api_token}
            if params:
                query_params.update(params)

            response = self.session.get(url, params=query_params, timeout=30)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API Error {response.status_code}: {response.text[:200]}")
                return {"error": f"API Error {response.status_code}"}

        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}

    def get_tomorrows_fixtures_with_participants(self) -> List[Dict]:
        """Get tomorrow's fixtures with team data"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        fixtures_data = self.make_request(f"fixtures/date/{tomorrow}")

        if "error" in fixtures_data or not fixtures_data.get("data"):
            return []

        fixtures = fixtures_data["data"]
        enriched_fixtures: List[Dict] = []

        # Get participants for each fixture
        for fixture in fixtures:
            try:
                fixture_id = fixture["id"]

                # Get participants using working endpoint
                participants_data = self.make_request("fixtures", {
                    "per_page": "1",
                    "include": "participants",
                    "filters": f"fixtures:{fixture_id}"
                })

                if participants_data.get("data") and len(participants_data["data"]) > 0:
                    enriched_fixture = participants_data["data"][0]
                    enriched_fixtures.append(enriched_fixture)

            except Exception as e:
                logger.error(f"Error enriching fixture {fixture.get('id')}: {str(e)}")
                continue

        return enriched_fixtures

    def get_team_recent_fixtures(self, team_id: int, limit: int = 10) -> List[Dict]:
        """Get recent fixtures for a team using teams_with_fixtures endpoint"""
        try:
            team_data = self.make_request("teams", {
                "per_page": "1",
                "include": "fixtures",
                "filters": f"teams:{team_id}"
            })

            if team_data.get("data") and len(team_data["data"]) > 0:
                team = team_data["data"][0]
                fixtures = team.get("fixtures", [])

                # Sort by date and get recent finished matches
                recent_fixtures: List[Dict] = []
                for fixture in fixtures:
                    if fixture.get("state_id") == 5:  # Finished matches
                        recent_fixtures.append(fixture)

                # Sort by starting_at date (most recent first)
                recent_fixtures.sort(key=lambda x: x.get("starting_at", ""), reverse=True)
                return recent_fixtures[:limit]

            return []

        except Exception as e:
            logger.error(f"Error getting team fixtures for {team_id}: {str(e)}")
            return []

    def analyze_team_form(self, team_id: int, team_name: str, recent_fixtures: List[Dict]) -> Dict:
        """Analyze team form from recent fixtures"""
        if not recent_fixtures:
            return {
                "team_id": team_id,
                "team_name": team_name,
                "games_played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goals_for": 0,
                "goals_against": 0,
                "form_rating": 0.5,
                "form_string": "No data",
                "avg_goals_for": 0,
                "avg_goals_against": 0
            }

        wins = draws = losses = goals_for = goals_against = 0
        form_string = ""

        # Get scores for each fixture
        for fixture in recent_fixtures[:5]:  # Last 5 games
            try:
                fixture_id = fixture["id"]

                # Get scores using working endpoint
                scores_data = self.make_request("fixtures", {
                    "per_page": "1",
                    "include": "scores",
                    "filters": f"fixtures:{fixture_id}"
                })

                if not scores_data.get("data") or len(scores_data["data"]) == 0:
                    continue

                fixture_with_scores = scores_data["data"][0]
                scores = fixture_with_scores.get("scores", [])

                if not scores:
                    continue

                # Find current score
                home_score = away_score = 0
                for score in scores:
                    if score.get("description") == "CURRENT":
                        home_score = score.get("score", {}).get("home", 0) or 0
                        away_score = score.get("score", {}).get("away", 0) or 0
                        break

                # Get participants to determine if team was home or away
                participants = fixture_with_scores.get("participants", [])
                is_home = False

                for participant in participants:
                    if participant.get("id") == team_id:
                        is_home = participant.get("meta", {}).get("location") == "home"
                        break

                # Calculate result from team's perspective
                if is_home:
                    team_score = home_score
                    opponent_score = away_score
                else:
                    team_score = away_score
                    opponent_score = home_score

                goals_for += team_score
                goals_against += opponent_score

                if team_score > opponent_score:
                    wins += 1
                    form_string = "W" + form_string
                elif team_score == opponent_score:
                    draws += 1
                    form_string = "D" + form_string
                else:
                    losses += 1
                    form_string = "L" + form_string

            except Exception as e:
                logger.error(f"Error analyzing fixture {fixture.get('id')}: {str(e)}")
                continue

        games_played = wins + draws + losses

        # Calculate form rating (0-1 scale)
        if games_played > 0:
            points = (wins * 3) + draws
            max_points = games_played * 3
            form_rating = points / max_points
        else:
            form_rating = 0.5

        return {
            "team_id": team_id,
            "team_name": team_name,
            "games_played": games_played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "form_rating": round(form_rating, 3),
            "form_string": form_string[:5],  # Last 5 games
            "avg_goals_for": round(goals_for / games_played, 2) if games_played > 0 else 0,
            "avg_goals_against": round(goals_against / games_played, 2) if games_played > 0 else 0
        }

    def get_team_league_position(self, team_id: int) -> int:
        """Get team's current league position from standings"""
        try:
            standings_data = self.make_request("standings", {
                "per_page": "50",
                "filters": f"participants:{team_id}"
            })

            if standings_data.get("data"):
                for standing in standings_data["data"]:
                    if standing.get("participant_id") == team_id:
                        return standing.get("position", 10)  # Default to mid-table

            return 10  # Default position

        except Exception as e:
            logger.error(f"Error getting league position for {team_id}: {str(e)}")
            return 10

    def get_odds_data(self, fixture_id: int) -> Dict:
        """Get odds data for fixture if available"""
        try:
            odds_data = self.make_request("fixtures", {
                "per_page": "1",
                "include": "odds",
                "filters": f"fixtures:{fixture_id}"
            })

            if odds_data.get("data") and len(odds_data["data"]) > 0:
                fixture_with_odds = odds_data["data"][0]
                odds = fixture_with_odds.get("odds", [])

                if odds:
                    # Find 1x2 market odds
                    for odd in odds:
                        if odd.get("market_description") == "1X2" or odd.get("name") == "Match Result":
                            return {
                                "has_odds": True,
                                "odds_data": odd
                            }

            return {"has_odds": False}

        except Exception as e:
            logger.error(f"Error getting odds for fixture {fixture_id}: {str(e)}")
            return {"has_odds": False}

    def predict_match(
        self,
        home_team_form: Dict,
        away_team_form: Dict,
        home_position: int,
        away_position: int,
        odds_data: Dict
    ) -> Dict:
        """Generate match prediction using all available data"""

        # Base prediction on form ratings
        home_rating = home_team_form["form_rating"]
        away_rating = away_team_form["form_rating"]

        # Adjust for league positions (lower position = better team)
        position_factor = 0.1
        home_position_adj = (20 - home_position) / 20 * position_factor  # Normalize to 0-0.1
        away_position_adj = (20 - away_position) / 20 * position_factor

        # Home advantage
        home_advantage = 0.15

        # Calculate adjusted strengths
        home_strength = min(home_rating + home_position_adj + home_advantage, 1.0)
        away_strength = min(away_rating + away_position_adj, 1.0)

        # Convert to probabilities
        total_strength = home_strength + away_strength
        if total_strength > 0:
            home_win_prob = (home_strength / total_strength) * 65  # 65% distributed between teams
            away_win_prob = (away_strength / total_strength) * 65
            draw_prob = 35  # 35% base draw probability
        else:
            home_win_prob = away_win_prob = draw_prob = 33.33

        # Normalize to 100%
        total_prob = home_win_prob + away_win_prob + draw_prob
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

        # Score prediction
        home_goals = home_team_form["avg_goals_for"]
        away_goals = away_team_form["avg_goals_for"]
        home_conceded = home_team_form["avg_goals_against"]
        away_conceded = away_team_form["avg_goals_against"]

        predicted_home_goals = round((home_goals + away_conceded) / 2 * 1.1)  # Home boost
        predicted_away_goals = round((away_goals + home_conceded) / 2)

        # Value bet analysis if odds available (placeholder)
        value_bet = None
        if odds_data.get("has_odds"):
            value_bet = "Check odds manually for value"

        return {
            "prediction": prediction,
            "confidence": round(confidence, 1),
            "probabilities": {
                "home_win": round(home_win_prob, 1),
                "draw": round(draw_prob, 1),
                "away_win": round(away_win_prob, 1)
            },
            "predicted_score": f"{predicted_home_goals}-{predicted_away_goals}",
            "home_strength": round(home_strength, 3),
            "away_strength": round(away_strength, 3),
            "has_odds": odds_data.get("has_odds", False),
            "value_bet": value_bet
        }

    def generate_all_predictions(self) -> List[Dict]:
        """Generate predictions for all tomorrow's matches"""
        print("🎯 GENERATING BETTING PREDICTIONS")
        print("=" * 50)

        # Get tomorrow's fixtures with participants
        fixtures = self.get_tomorrows_fixtures_with_participants()

        if not fixtures:
            print("❌ No fixtures found for tomorrow")
            return []

        print(f"📅 Found {len(fixtures)} fixtures for tomorrow")

        predictions: List[Dict] = []

        for fixture in fixtures:
            try:
                fixture_id = fixture["id"]
                participants = fixture.get("participants", [])

                if len(participants) < 2:
                    print(f"⚠️ Skipping fixture {fixture_id} - insufficient participants")
                    continue

                # Extract teams
                home_team = away_team = None
                for participant in participants:
                    if participant.get("meta", {}).get("location") == "home":
                        home_team = participant
                    else:
                        away_team = participant

                if not home_team or not away_team:
                    print(f"⚠️ Skipping fixture {fixture_id} - could not identify home/away teams")
                    continue

                home_id = home_team["id"]
                away_id = away_team["id"]
                home_name = home_team["name"]
                away_name = away_team["name"]

                print(f"🔍 Analyzing: {home_name} vs {away_name}")

                # Get team data
                home_fixtures = self.get_team_recent_fixtures(home_id)
                away_fixtures = self.get_team_recent_fixtures(away_id)

                home_form = self.analyze_team_form(home_id, home_name, home_fixtures)
                away_form = self.analyze_team_form(away_id, away_name, away_fixtures)

                home_position = self.get_team_league_position(home_id)
                away_position = self.get_team_league_position(away_id)

                odds_data = self.get_odds_data(fixture_id)

                # Generate prediction
                prediction = self.predict_match(home_form, away_form, home_position, away_position, odds_data)

                # Compile full prediction
                full_prediction = {
                    "fixture_id": fixture_id,
                    "home_team": home_name,
                    "away_team": away_name,
                    "league": fixture.get("league", {}).get("name", "Unknown") if fixture.get("league") else "Unknown",
                    "kickoff": fixture.get("starting_at", "Unknown"),
                    "home_position": home_position,
                    "away_position": away_position,
                    "home_form": home_form,
                    "away_form": away_form,
                    **prediction
                }

                predictions.append(full_prediction)
                print(f"✅ Prediction: {prediction['prediction']} ({prediction['confidence']}%)")

            except Exception as e:
                print(f"❌ Error processing fixture {fixture.get('id')}: {str(e)}")
                continue

        # Sort by confidence
        predictions.sort(key=lambda x: x["confidence"], reverse=True)

        print(f"🎯 Generated {len(predictions)} predictions")
        return predictions


# Flask App
app = Flask(__name__)
predictor: Optional[RealDataPredictor] = None


@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>WORKING SportMonks Betting Predictor</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: white; text-align: center; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); margin-bottom: 10px; }
.subtitle { color: #f0f0f0; text-align: center; margin-bottom: 30px; }
.card { background: white; border-radius: 12px; padding: 25px; margin: 20px 0; box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
.btn { background: linear-gradient(45deg, #667eea, #764ba2); color: white; padding: 15px 30px; border: none; border-radius: 8px; cursor: pointer; margin: 8px; font-weight: bold; font-size: 14px; transition: all 0.3s; }
.btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
.btn.success { background: linear-gradient(45deg, #56ab2f, #a8e6cf); }
.btn.warning { background: linear-gradient(45deg, #f093fb, #f5576c); }
input[type="password"] { padding: 15px; border: 2px solid #ddd; border-radius: 8px; width: 350px; margin-right: 15px; font-size: 14px; }
.prediction { border-left: 5px solid #667eea; padding: 20px; margin: 15px 0; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 8px; }
.high-confidence { border-left-color: #56ab2f; background: linear-gradient(135deg, #d4f1d4 0%, #a8e6cf 100%); }
.medium-confidence { border-left-color: #ffa726; background: linear-gradient(135deg, #fff3e0 0%, #ffcc80 100%); }
.low-confidence { border-left-color: #ef5350; background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }
.stat { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 8px; text-align: center; }
.loading { text-align: center; color: #667eea; padding: 30px; animation: pulse 1.5s infinite; font-size: 18px; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.error { color: #d32f2f; background: #ffebee; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 5px solid #d32f2f; }
.success { color: #388e3c; background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 5px solid #388e3c; }
.warning { color: #f57c00; background: #fff3e0; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 5px solid #f57c00; }
.form-badge { display: inline-block; padding: 5px 10px; border-radius: 15px; color: white; font-weight: bold; margin: 2px; }
.form-w { background: #4caf50; }
.form-d { background: #ff9800; }
.form-l { background: #f44336; }
.team-analysis { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; }
</style>
</head>
<body>
<div class="container">
<h1>⚽ WORKING SportMonks Betting Predictor</h1>
<p class="subtitle">Using 55 real working endpoints • Form analysis • League positions • Odds data</p>

<div class="card">
    <h2>🚀 Initialize Predictor</h2>
    <input type="password" id="apiToken" placeholder="Enter your SportMonks API Token">
    <br><br>
    <button class="btn success" onclick="initializePredictor()">✅ Initialize Predictor</button>
    <div id="initStatus"></div>
</div>

<div class="card">
    <h2>🎯 Generate Betting Predictions</h2>
    <p>Analyzes tomorrow's fixtures using team form, league positions, and available odds data.</p>
    <button class="btn warning" onclick="generatePredictions()">🔮 Generate Tomorrow's Predictions</button>
    <div id="predictionStatus"></div>
</div>

<div class="card">
    <h2>📊 Tomorrow's Betting Tips</h2>
    <div id="predictions">Click "Generate Predictions" to see betting analysis for tomorrow's matches</div>
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
    
    document.getElementById('initStatus').innerHTML = '<div class="loading">🔧 Initializing predictor with real SportMonks data...</div>';
    
    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('initStatus').innerHTML = '<div class="success">✅ Predictor initialized! Ready to analyze matches.</div>';
        } else {
            document.getElementById('initStatus').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('initStatus').innerHTML = '<div class="error">❌ Network error: ' + error.message + '</div>';
    }
}

async function generatePredictions() {
    document.getElementById('predictionStatus').innerHTML = '<div class="loading">🎯 Analyzing tomorrow\\'s matches... This may take 30-60 seconds...</div>';
    document.getElementById('predictions').innerHTML = '<div class="loading">⚽ Getting fixtures and analyzing team form...</div>';
    
    try {
        const response = await fetch('/api/predictions', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            displayPredictions(data.predictions);
            displayStats(data.stats);
            document.getElementById('predictionStatus').innerHTML = '<div class="success">✅ Generated ' + data.predictions.length + ' betting predictions!</div>';
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
        document.getElementById('predictions').innerHTML = '<div class="warning">No matches found for tomorrow or unable to analyze fixtures.</div>';
        return;
    }
    
    let html = '';
    predictions.forEach(pred => {
        const confidenceClass = pred.confidence >= 60 ? 'high-confidence' : pred.confidence >= 45 ? 'medium-confidence' : 'low-confidence';
        
        // Generate form badges
        const homeFormBadges = generateFormBadges(pred.home_form.form_string);
        const awayFormBadges = generateFormBadges(pred.away_form.form_string);
        
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
                    <div class="stat">
                        <strong>Has Odds</strong><br>
                        ${pred.has_odds ? '✅ Yes' : '❌ No'}
                    </div>
                </div>
                
                <div class="team-analysis">
                    <strong>${pred.home_team}</strong> (Position: ${pred.home_position})<br>
                    Form: ${homeFormBadges} (${pred.home_form.wins}W-${pred.home_form.draws}D-${pred.home_form.losses}L)<br>
                    Goals: ${pred.home_form.avg_goals_for}/game scored, ${pred.home_form.avg_goals_against}/game conceded
                </div>
                
                <div class="team-analysis">
                    <strong>${pred.away_team}</strong> (Position: ${pred.away_position})<br>
                    Form: ${awayFormBadges} (${pred.away_form.wins}W-${pred.away_form.draws}D-${pred.away_form.losses}L)<br>
                    Goals: ${pred.away_form.avg_goals_for}/game scored, ${pred.away_form.avg_goals_against}/game conceded
                </div>
                
                ${pred.value_bet ? '<p><strong>💰 Value Bet:</strong> ' + pred.value_bet + '</p>' : ''}
            </div>
        `;
    });
    
    document.getElementById('predictions').innerHTML = html;
}

function generateFormBadges(formString) {
    if (!formString) return '<span class="form-badge" style="background:#999;">No data</span>';
    
    return formString.split('').map(letter => {
        const className = letter === 'W' ? 'form-w' : letter === 'D' ? 'form-d' : 'form-l';
        return `<span class="form-badge ${className}">${letter}</span>`;
    }).join('');
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
                <strong>High Confidence (60%+)</strong><br>
                ${stats.high_confidence}
            </div>
            <div class="stat">
                <strong>With Odds Data</strong><br>
                ${stats.with_odds}
            </div>
            <div class="stat">
                <strong>Average Confidence</strong><br>
                ${stats.avg_confidence}%
            </div>
        </div>
    `;
    
    document.getElementById('stats').innerHTML = html;
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
        predictor = RealDataPredictor(api_token)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Initialization failed")
        return jsonify({"success": False, "error": f"Initialization failed: {str(e)}"})


@app.route("/api/predictions", methods=["POST"])
def api_predictions():
    global predictor
    if not predictor:
        return jsonify({"success": False, "error": "Predictor not initialized"})

    try:
        preds = predictor.generate_all_predictions()

        total_predictions = len(preds)
        high_confidence = len([p for p in preds if p.get("confidence", 0) >= 60])
        with_odds = len([p for p in preds if p.get("has_odds")])
        avg_confidence = round(
            (sum(p.get("confidence", 0) for p in preds) / total_predictions) if total_predictions > 0 else 0,
            1
        )

        stats = {
            "total_predictions": total_predictions,
            "high_confidence": high_confidence,
            "with_odds": with_odds,
            "avg_confidence": avg_confidence
        }

        return jsonify({"success": True, "predictions": preds, "stats": stats})

    except Exception as e:
        logger.exception("Prediction generation failed")
        return jsonify({"success": False, "error": f"Prediction generation failed: {str(e)}"})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


# Flask app bootstrap
app = Flask(__name__)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

# For Gunicorn
application = app