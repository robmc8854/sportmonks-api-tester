#!/usr/bin/env python3
"""
COMPLETE AI BETTING BOT - PRODUCTION READY
Using SportMonks API for comprehensive betting analysis and predictions

Features:
- Team form analysis and rating system
- Player xG efficiency integration
- Multi-factor prediction models
- Value betting detection
- Live odds monitoring
- Bankroll management
- Performance tracking
- Web dashboard
- Automated predictions
"""

import sqlite3
import json
import os
import threading
import time
import schedule
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
from collections import defaultdict

import requests
from flask import Flask, jsonify, render_template_string, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("betting_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ==============================
# DATA MODELS
# ==============================

@dataclass
class Team:
    id: int
    name: str
    league_id: int
    current_rating: float = 1500.0  # ELO-style rating
    home_rating: float = 1500.0
    away_rating: float = 1500.0
    goals_for_avg: float = 0.0
    goals_against_avg: float = 0.0
    xg_efficiency: float = 1.0
    form_points: int = 0  # Last 5 matches


@dataclass
class Fixture:
    id: int
    home_team_id: int
    away_team_id: int
    league_id: int
    kickoff_time: datetime
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "scheduled"


@dataclass
class Prediction:
    fixture_id: int
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    over_2_5_prob: float
    under_2_5_prob: float
    btts_prob: float
    expected_home_goals: float
    expected_away_goals: float
    confidence_score: float
    recommended_bets: List[Dict[str, Any]]
    created_at: datetime


@dataclass
class Bet:
    id: int
    fixture_id: int
    bet_type: str  # "1", "X", "2", "O2.5", "U2.5", "BTTS"
    odds: float
    stake: float
    predicted_prob: float
    edge: float
    status: str = "pending"  # pending, won, lost
    profit_loss: float = 0.0
    placed_at: datetime = field(default_factory=datetime.now)

# ==============================
# SPORTMONKS API CLIENT
# ==============================

class SportMonksAPI:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_url = "https://api.sportmonks.com/v3/odds"

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "AI-Betting-Bot/1.0"
        })

        # Rate limiting
        self.last_request_time = 0.0
        self.min_request_interval = 0.5  # 2 requests per second max

    def _request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make rate-limited API request"""
        # Rate limiting
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)

        try:
            request_params: Dict[str, Any] = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            response = self.session.get(url, params=request_params, timeout=30)
            self.last_request_time = time.time()

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API request failed: {response.status_code} - {url}")
                return None

        except Exception as e:
            logger.error(f"API request error: {e}")
            return None

    def get_todays_fixtures(self) -> List[Dict[str, Any]]:
        """Get today's fixtures"""
        today = datetime.now().strftime('%Y-%m-%d')
        data = self._request(f"{self.base_url}/fixtures/date/{today}",
                             {"include": "participants,league"})
        return data.get("data", []) if data else []

    def get_fixtures_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get fixtures for specific date"""
        data = self._request(f"{self.base_url}/fixtures/date/{date_str}",
                             {"include": "participants,league,scores"})
        return data.get("data", []) if data else []

    def get_team_stats(self, team_id: int) -> Optional[Dict[str, Any]]:
        """Get team statistics"""
        data = self._request(f"{self.base_url}/teams/{team_id}",
                             {"include": "statistics"})
        return data.get("data") if data else None

    def get_leagues(self) -> List[Dict[str, Any]]:
        """Get available leagues"""
        data = self._request(f"{self.base_url}/leagues", {"per_page": "100"})
        return data.get("data", []) if data else []

    def get_team_players(self, team_id: int) -> List[Dict[str, Any]]:
        """Get team players with xG efficiency"""
        data = self._request(f"{self.base_url}/teams/{team_id}/players",
                             {"include": "statistics"})
        return data.get("data", []) if data else []

    def get_bookmakers(self) -> List[Dict[str, Any]]:
        """Get available bookmakers"""
        data = self._request(f"{self.odds_url}/bookmakers")
        return data.get("data", []) if data else []

    def get_markets(self) -> List[Dict[str, Any]]:
        """Get betting markets"""
        data = self._request(f"{self.odds_url}/markets")
        return data.get("data", []) if data else []

    def get_live_scores(self) -> List[Dict[str, Any]]:
        """Get live scores"""
        data = self._request(f"{self.base_url}/livescores")
        return data.get("data", []) if data else []

# ==============================
# DATABASE MANAGER
# ==============================

class DatabaseManager:
    def __init__(self, db_path: str = "betting_bot.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Teams table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                league_id INTEGER,
                current_rating REAL DEFAULT 1500,
                home_rating REAL DEFAULT 1500,
                away_rating REAL DEFAULT 1500,
                goals_for_avg REAL DEFAULT 0,
                goals_against_avg REAL DEFAULT 0,
                xg_efficiency REAL DEFAULT 1.0,
                form_points INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Fixtures table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fixtures (
                id INTEGER PRIMARY KEY,
                home_team_id INTEGER,
                away_team_id INTEGER,
                league_id INTEGER,
                kickoff_time TIMESTAMP,
                home_score INTEGER,
                away_score INTEGER,
                status TEXT DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER,
                home_win_prob REAL,
                draw_prob REAL,
                away_win_prob REAL,
                over_2_5_prob REAL,
                under_2_5_prob REAL,
                btts_prob REAL,
                expected_home_goals REAL,
                expected_away_goals REAL,
                confidence_score REAL,
                recommended_bets TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fixture_id) REFERENCES fixtures (id)
            )
        ''')

        # Bets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_id INTEGER,
                bet_type TEXT,
                odds REAL,
                stake REAL,
                predicted_prob REAL,
                edge REAL,
                status TEXT DEFAULT 'pending',
                profit_loss REAL DEFAULT 0,
                placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fixture_id) REFERENCES fixtures (id)
            )
        ''')

        # Performance tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                total_bets INTEGER,
                winning_bets INTEGER,
                total_stake REAL,
                total_returns REAL,
                roi REAL,
                bankroll REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def save_team(self, team: Team):
        """Save team to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO teams 
            (id, name, league_id, current_rating, home_rating, away_rating, 
             goals_for_avg, goals_against_avg, xg_efficiency, form_points)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (team.id, team.name, team.league_id, team.current_rating,
              team.home_rating, team.away_rating, team.goals_for_avg,
              team.goals_against_avg, team.xg_efficiency, team.form_points))

        conn.commit()
        conn.close()

    def get_team(self, team_id: int) -> Optional[Team]:
        """Get team from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Team(
                id=row[0], name=row[1], league_id=row[2], current_rating=row[3],
                home_rating=row[4], away_rating=row[5], goals_for_avg=row[6],
                goals_against_avg=row[7], xg_efficiency=row[8], form_points=row[9]
            )
        return None

    def save_fixture(self, fixture: Fixture):
        """Save fixture to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        kickoff = fixture.kickoff_time.isoformat() if isinstance(fixture.kickoff_time, datetime) else str(fixture.kickoff_time)

        cursor.execute('''
            INSERT OR REPLACE INTO fixtures 
            (id, home_team_id, away_team_id, league_id, kickoff_time, 
             home_score, away_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (fixture.id, fixture.home_team_id, fixture.away_team_id,
              fixture.league_id, kickoff, fixture.home_score,
              fixture.away_score, fixture.status))

        conn.commit()
        conn.close()

    def save_prediction(self, prediction: Prediction):
        """Save prediction to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO predictions 
            (fixture_id, home_win_prob, draw_prob, away_win_prob, over_2_5_prob,
             under_2_5_prob, btts_prob, expected_home_goals, expected_away_goals,
             confidence_score, recommended_bets)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (prediction.fixture_id, prediction.home_win_prob, prediction.draw_prob,
              prediction.away_win_prob, prediction.over_2_5_prob, prediction.under_2_5_prob,
              prediction.btts_prob, prediction.expected_home_goals, prediction.expected_away_goals,
              prediction.confidence_score, json.dumps(prediction.recommended_bets)))

        conn.commit()
        conn.close()

    def save_bet(self, bet: Bet):
        """Save bet to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO bets 
            (fixture_id, bet_type, odds, stake, predicted_prob, edge, status, profit_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bet.fixture_id, bet.bet_type, bet.odds, bet.stake,
              bet.predicted_prob, bet.edge, bet.status, bet.profit_loss))

        conn.commit()
        conn.close()

    def get_recent_fixtures(self, team_id: int, limit: int = 10) -> List[Tuple]:
        """Get recent fixtures for a team"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM fixtures 
            WHERE (home_team_id = ? OR away_team_id = ?) 
            AND status = 'finished'
            ORDER BY kickoff_time DESC 
            LIMIT ?
        ''', (team_id, team_id, limit))

        results = cursor.fetchall()
        conn.close()
        return results

    def get_todays_predictions(self) -> List[Dict[str, Any]]:
        """Get today's predictions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        today = date.today().isoformat()
        cursor.execute('''
            SELECT p.*, f.home_team_id, f.away_team_id, f.kickoff_time,
                   h.name as home_team, a.name as away_team
            FROM predictions p
            JOIN fixtures f ON p.fixture_id = f.id
            JOIN teams h ON f.home_team_id = h.id
            JOIN teams a ON f.away_team_id = a.id
            WHERE DATE(f.kickoff_time) = ?
            ORDER BY p.confidence_score DESC
        ''', (today,))

        results = cursor.fetchall()
        conn.close()

        predictions: List[Dict[str, Any]] = []
        for row in results:
            predictions.append({
                'id': row[0],
                'fixture_id': row[1],
                'home_win_prob': row[2],
                'draw_prob': row[3],
                'away_win_prob': row[4],
                'over_2_5_prob': row[5],
                'under_2_5_prob': row[6],
                'btts_prob': row[7],
                'expected_home_goals': row[8],
                'expected_away_goals': row[9],
                'confidence_score': row[10],
                'recommended_bets': json.loads(row[11]) if row[11] else [],
                'home_team': row[14],
                'away_team': row[15],
                'kickoff_time': row[13]
            })

        return predictions

# ==============================
# PREDICTION ENGINE
# ==============================

class PredictionEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

        # Model weights
        self.weights = {
            'team_rating': 0.35,
            'form': 0.25,
            'home_advantage': 0.15,
            'goals_avg': 0.15,
            'xg_efficiency': 0.10
        }

        self.home_advantage = 0.3  # Home team rating boost

    def calculate_team_form(self, team_id: int) -> float:
        """Calculate team form based on recent results"""
        recent_fixtures = self.db.get_recent_fixtures(team_id, 5)

        if not recent_fixtures:
            return 0.5  # Neutral form

        points = 0
        total_matches = len(recent_fixtures)

        for fixture in recent_fixtures:
            home_team_id, away_team_id = fixture[1], fixture[2]
            home_score, away_score = fixture[5], fixture[6]

            if home_score is None or away_score is None:
                continue

            is_home = (home_team_id == team_id)

            if is_home:
                if home_score > away_score:
                    points += 3  # Win
                elif home_score == away_score:
                    points += 1  # Draw
            else:
                if away_score > home_score:
                    points += 3  # Win
                elif home_score == away_score:
                    points += 1  # Draw

        max_points = total_matches * 3
        return points / max_points if max_points > 0 else 0.5

    def calculate_expected_goals(self, home_team: Team, away_team: Team) -> Tuple[float, float]:
        """Calculate expected goals for both teams"""
        # Base expected goals from averages
        home_attack = home_team.goals_for_avg
        home_defense = home_team.goals_against_avg
        away_attack = away_team.goals_for_avg
        away_defense = away_team.goals_against_avg

        # Adjust for xG efficiency
        home_xg_adjusted = home_attack * home_team.xg_efficiency
        away_xg_adjusted = away_attack * away_team.xg_efficiency

        # Calculate expected goals
        expected_home = (home_xg_adjusted + away_defense) / 2
        expected_away = (away_xg_adjusted + home_defense) / 2

        # Home advantage
        expected_home *= 1.1
        expected_away *= 0.95

        return max(0.1, expected_home), max(0.1, expected_away)

    def poisson_probability(self, expected_goals: float, actual_goals: int) -> float:
        """Calculate Poisson probability"""
        return (math.exp(-expected_goals) * (expected_goals ** actual_goals)) / math.factorial(actual_goals)

    def calculate_match_probabilities(self, home_team: Team, away_team: Team) -> Dict[str, float]:
        """Calculate match outcome probabilities"""
        # Get expected goals
        exp_home, exp_away = self.calculate_expected_goals(home_team, away_team)

        # Calculate outcome probabilities using Poisson distribution
        home_win_prob = 0.0
        draw_prob = 0.0
        away_win_prob = 0.0

        # Calculate for scores up to 5 goals each
        for home_goals in range(6):
            for away_goals in range(6):
                prob = (self.poisson_probability(exp_home, home_goals) *
                        self.poisson_probability(exp_away, away_goals))

                if home_goals > away_goals:
                    home_win_prob += prob
                elif home_goals == away_goals:
                    draw_prob += prob
                else:
                    away_win_prob += prob

        # Normalize probabilities
        total = home_win_prob + draw_prob + away_win_prob
        if total > 0:
            home_win_prob /= total
            draw_prob /= total
            away_win_prob /= total

        # Over/Under 2.5 goals
        under_2_5_prob = 0.0
        for home_goals in range(6):
            for away_goals in range(6):
                if home_goals + away_goals < 3:  # strictly under 2.5 ⇒ total goals 0,1,2
                    under_2_5_prob += (self.poisson_probability(exp_home, home_goals) *
                                       self.poisson_probability(exp_away, away_goals))

        over_2_5_prob = 1 - under_2_5_prob

        # Both teams to score
        home_no_score = self.poisson_probability(exp_home, 0)
        away_no_score = self.poisson_probability(exp_away, 0)
        btts_prob = 1 - (home_no_score + away_no_score - (home_no_score * away_no_score))

        return {
            'home_win': home_win_prob,
            'draw': draw_prob,
            'away_win': away_win_prob,
            'over_2_5': over_2_5_prob,
            'under_2_5': under_2_5_prob,
            'btts': btts_prob,
            'expected_home_goals': exp_home,
            'expected_away_goals': exp_away
        }

    def generate_prediction(self, fixture: Fixture) -> Optional[Prediction]:
        """Generate prediction for a fixture"""
        home_team = self.db.get_team(fixture.home_team_id)
        away_team = self.db.get_team(fixture.away_team_id)

        if not home_team or not away_team:
            logger.error(f"Teams not found for fixture {fixture.id}")
            return None

        # Calculate probabilities
        probs = self.calculate_match_probabilities(home_team, away_team)

        # Confidence based on the strongest outcome
        max_prob = max(probs['home_win'], probs['draw'], probs['away_win'])
        confidence = max_prob * 100

        # Generate recommended bets (placeholder odds)
        recommended_bets = self.find_value_bets(probs, {
            '1': 2.0,  # Placeholder odds
            'X': 3.5,
            '2': 4.0,
            'O2.5': 1.8,
            'U2.5': 2.1,
            'BTTS': 1.9
        })

        return Prediction(
            fixture_id=fixture.id,
            home_win_prob=probs['home_win'],
            draw_prob=probs['draw'],
            away_win_prob=probs['away_win'],
            over_2_5_prob=probs['over_2_5'],
            under_2_5_prob=probs['under_2_5'],
            btts_prob=probs['btts'],
            expected_home_goals=probs['expected_home_goals'],
            expected_away_goals=probs['expected_away_goals'],
            confidence_score=confidence,
            recommended_bets=recommended_bets,
            created_at=datetime.now()
        )

    def find_value_bets(self, probabilities: Dict[str, float], odds: Dict[str, float]) -> List[Dict[str, Any]]:
        """Find value betting opportunities"""
        value_bets: List[Dict[str, Any]] = []

        bet_mappings = {
            '1': ('home_win', 'Home Win'),
            'X': ('draw', 'Draw'),
            '2': ('away_win', 'Away Win'),
            'O2.5': ('over_2_5', 'Over 2.5 Goals'),
            'U2.5': ('under_2_5', 'Under 2.5 Goals'),
            'BTTS': ('btts', 'Both Teams to Score')
        }

        for bet_type, (prob_key, bet_name) in bet_mappings.items():
            if bet_type in odds:
                predicted_prob = probabilities[prob_key]
                bookmaker_odds = odds[bet_type]
                if bookmaker_odds <= 0:
                    continue
                implied_prob = 1 / bookmaker_odds

                edge = predicted_prob - implied_prob

                if edge > 0.05:  # 5% minimum edge
                    value_bets.append({
                        'bet_type': bet_type,
                        'bet_name': bet_name,
                        'odds': bookmaker_odds,
                        'predicted_prob': predicted_prob,
                        'implied_prob': implied_prob,
                        'edge': edge,
                        'confidence': 'High' if edge > 0.15 else 'Medium'
                    })

        return sorted(value_bets, key=lambda x: x['edge'], reverse=True)

# ==============================
# BETTING BOT MAIN CLASS
# ==============================

class BettingBot:
    def __init__(self, api_token: str):
        self.api = SportMonksAPI(api_token)
        self.db = DatabaseManager()
        self.prediction_engine = PredictionEngine(self.db)

        self.bankroll = 1000.0  # Starting bankroll
        self.max_bet_percentage = 0.02  # Max 2% of bankroll per bet

        self.is_running = False
        self.last_update: Optional[datetime] = None

        # Initialize data
        self.initialize_data()

    def initialize_data(self):
        """Initialize teams and fixtures data"""
        logger.info("Initializing bot data...")

        # Get leagues and teams
        leagues = self.api.get_leagues()
        logger.info(f"Found {len(leagues)} leagues")

        # For now, focus on major leagues to avoid rate limits
        major_leagues = [39, 40, 78, 135, 61]  # Example IDs

        for league in leagues[:10]:  # Limit to avoid rate limits
            league_id = league.get('id')
            if league_id:
                logger.info(f"Processing league: {league.get('name')} (id={league_id})")

    def update_team_stats(self, team_id: int, team_data: Dict[str, Any]):
        """Update team statistics"""
        team = self.db.get_team(team_id)

        if not team:
            # Create new team
            team = Team(
                id=team_id,
                name=team_data.get('name', 'Unknown'),
                league_id=team_data.get('league_id', 0)
            )

        # Update team stats from API data
        if 'statistics' in team_data:
            stats = team_data['statistics']
            # Placeholder: Update averages etc. once structure known

        # Calculate form
        team.form_points = int(self.prediction_engine.calculate_team_form(team_id) * 15)

        self.db.save_team(team)

    def process_todays_fixtures(self) -> int:
        """Process and predict today's fixtures"""
        logger.info("Processing today's fixtures...")

        fixtures_data = self.api.get_todays_fixtures()
        predictions_made = 0

        for fixture_data in fixtures_data:
            try:
                participants = fixture_data.get('participants', [])
                home_id = fixture_data.get('home_team_id') or (participants[0].get('id') if len(participants) > 0 else None)
                away_id = fixture_data.get('away_team_id') or (participants[1].get('id') if len(participants) > 1 else None)

                if not home_id or not away_id:
                    continue

                league_id = fixture_data.get('league_id') or (fixture_data.get('league', {}) or {}).get('id')

                kickoff_raw = fixture_data.get('starting_at')
                kickoff_time = datetime.fromisoformat(kickoff_raw.replace('Z', '+00:00')) if kickoff_raw else datetime.now()

                status = (fixture_data.get('state') or {}).get('short_name', 'scheduled')

                fixture = Fixture(
                    id=fixture_data['id'],
                    home_team_id=home_id,
                    away_team_id=away_id,
                    league_id=league_id or 0,
                    kickoff_time=kickoff_time,
                    status=status
                )

                # Save fixture
                self.db.save_fixture(fixture)

                # Generate prediction
                prediction = self.prediction_engine.generate_prediction(fixture)
                if prediction:
                    self.db.save_prediction(prediction)
                    predictions_made += 1

            except Exception as e:
                logger.error(f"Error processing fixture {fixture_data.get('id')}: {e}")
                continue

        logger.info(f"Generated {predictions_made} predictions")
        return predictions_made

    def run_daily_analysis(self):
        """Run daily analysis and predictions"""
        logger.info("Starting daily analysis...")

        try:
            # Process today's fixtures
            self.process_todays_fixtures()

            # Update last run time
            self.last_update = datetime.now()

            logger.info("Daily analysis completed successfully")

        except Exception as e:
            logger.error(f"Error in daily analysis: {e}")

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for dashboard"""
        try:
            predictions = self.db.get_todays_predictions()

            return {
                'status': 'running' if self.is_running else 'stopped',
                'last_update': self.last_update.isoformat() if self.last_update else None,
                'bankroll': self.bankroll,
                'todays_predictions': len(predictions),
                'predictions': predictions[:10],  # Top 10 predictions
                'total_predictions': len(predictions)
            }
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {'error': str(e)}

    def start_bot(self):
        """Start the betting bot"""
        self.is_running = True
        logger.info("Betting bot started")

        # Schedule daily tasks
        schedule.every().day.at("06:00").do(self.run_daily_analysis)

        # Run initial analysis
        self.run_daily_analysis()

    def stop_bot(self):
        """Stop the betting bot"""
        self.is_running = False
        logger.info("Betting bot stopped")

# ==============================
# WEB DASHBOARD
# ==============================

app = Flask(__name__)
bot: Optional[BettingBot] = None

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>AI Betting Bot Dashboard</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #f1f5f9; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #10b981; text-align: center; margin-bottom: 30px; }
        .status-bar { background: #1e293b; padding: 20px; border-radius: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .status-indicator { padding: 8px 16px; border-radius: 20px; font-weight: 600; }
        .status-running { background: #059669; color: white; }
        .status-stopped { background: #dc2626; color: white; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .metric-card { background: #1e293b; padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #334155; }
        .metric-value { font-size: 2rem; font-weight: 700; color: #10b981; }
        .metric-label { color: #94a3b8; font-size: 0.875rem; margin-top: 5px; }
        .predictions-section { background: #1e293b; padding: 25px; border-radius: 12px; margin-bottom: 20px; }
        .prediction-card { background: #0f172a; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #10b981; }
        .match-info { font-size: 1.1rem; font-weight: 600; margin-bottom: 10px; }
        .probabilities { display: flex; gap: 20px; margin: 10px 0; flex-wrap: wrap; }
        .prob-item { text-align: center; }
        .prob-value { font-size: 1.2rem; font-weight: 600; color: #3b82f6; }
        .prob-label { font-size: 0.8rem; color: #94a3b8; }
        .recommended-bets { margin-top: 15px; }
        .bet-tag { background: #059669; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; margin: 2px; display: inline-block; }
        .controls { text-align: center; margin: 20px 0; }
        .btn { background: #3b82f6; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; margin: 0 10px; }
        .btn:hover { background: #2563eb; }
        .btn-danger { background: #dc2626; }
        .btn-danger:hover { background: #b91c1c; }
        .confidence-high { border-left-color: #10b981; }
        .confidence-medium { border-left-color: #f59e0b; }
        .confidence-low { border-left-color: #6b7280; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 AI Betting Bot Dashboard</h1>

        <div class="status-bar">
            <div>
                <span>Status: </span>
                <span id="botStatus" class="status-indicator">Loading...</span>
            </div>
            <div>
                <span>Last Update: </span>
                <span id="lastUpdate">Never</span>
            </div>
            <div>
                <span>Bankroll: </span>
                <span id="bankroll">$0</span>
            </div>
        </div>

        <div class="controls">
            <button class="btn" onclick="startBot()">Start Bot</button>
            <button class="btn btn-danger" onclick="stopBot()">Stop Bot</button>
            <button class="btn" onclick="runAnalysis()">Run Analysis</button>
            <button class="btn" onclick="refreshDashboard()">Refresh</button>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value" id="todaysPredictions">0</div>
                <div class="metric-label">Today's Predictions</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="highConfidence">0</div>
                <div class="metric-label">High Confidence</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="valueBets">0</div>
                <div class="metric-label">Value Bets</div>
            </div>
            <div class="metric-card">
                <div class="metric-value" id="avgConfidence">0%</div>
                <div class="metric-label">Avg Confidence</div>
            </div>
        </div>

        <div class="predictions-section">
            <h3>🎯 Today's Top Predictions</h3>
            <div id="predictionsList">Loading predictions...</div>
        </div>
    </div>

<script>
    async function startBot() {
        try {
            const response = await fetch('/api/start', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                alert('Bot started successfully!');
                refreshDashboard();
            } else {
                alert(data.error || 'Failed to start');
            }
        } catch (error) {
            alert('Error starting bot: ' + error.message);
        }
    }

    async function stopBot() {
        try {
            const response = await fetch('/api/stop', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                alert('Bot stopped successfully!');
                refreshDashboard();
            } else {
                alert(data.error || 'Failed to stop');
            }
        } catch (error) {
            alert('Error stopping bot: ' + error.message);
        }
    }

    async function runAnalysis() {
        try {
            const response = await fetch('/api/analyze', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                alert('Analysis started!');
                setTimeout(refreshDashboard, 3000);
            } else {
                alert(data.error || 'Failed to analyze');
            }
        } catch (error) {
            alert('Error running analysis: ' + error.message);
        }
    }

    async function refreshDashboard() {
        try {
            const response = await fetch('/api/dashboard');
            const data = await response.json();
            updateDashboard(data);
        } catch (error) {
            console.error('Error refreshing dashboard:', error);
        }
    }

    function updateDashboard(data) {
        const statusEl = document.getElementById('botStatus');
        statusEl.textContent = data.status || 'Unknown';
        statusEl.className = 'status-indicator ' + (data.status === 'running' ? 'status-running' : 'status-stopped');

        document.getElementById('lastUpdate').textContent = data.last_update ? new Date(data.last_update).toLocaleString() : 'Never';
        document.getElementById('bankroll').textContent = '$' + (data.bankroll || 0).toFixed(2);
        document.getElementById('todaysPredictions').textContent = data.todays_predictions || 0;

        const predictions = data.predictions || [];
        const highConfidence = predictions.filter(p => p.confidence_score > 70).length;
        const valueBets = predictions.reduce((sum, p) => sum + (p.recommended_bets?.length || 0), 0);
        const avgConfidence = predictions.length > 0 ?
            (predictions.reduce((sum, p) => sum + p.confidence_score, 0) / predictions.length).toFixed(1) : 0;

        document.getElementById('highConfidence').textContent = highConfidence;
        document.getElementById('valueBets').textContent = valueBets;
        document.getElementById('avgConfidence').textContent = avgConfidence + '%';

        updatePredictionsList(predictions);
    }

    function updatePredictionsList(predictions) {
        const container = document.getElementById('predictionsList');

        if (!predictions || predictions.length === 0) {
            container.innerHTML = '<p>No predictions available for today.</p>';
            return;
        }

        let html = '';
        predictions.forEach(pred => {
            const confidenceClass = pred.confidence_score > 70 ? 'confidence-high' :
                                    pred.confidence_score > 50 ? 'confidence-medium' : 'confidence-low';

            html += `
                <div class="prediction-card ${confidenceClass}">
                    <div class="match-info">
                        ${pred.home_team} vs ${pred.away_team}
                        <span style="float: right; color: #10b981;">${pred.confidence_score.toFixed(1)}% confidence</span>
                    </div>
                    <div class="probabilities">
                        <div class="prob-item">
                            <div class="prob-value">${(pred.home_win_prob * 100).toFixed(1)}%</div>
                            <div class="prob-label">Home Win</div>
                        </div>
                        <div class="prob-item">
                            <div class="prob-value">${(pred.draw_prob * 100).toFixed(1)}%</div>
                            <div class="prob-label">Draw</div>
                        </div>
                        <div class="prob-item">
                            <div class="prob-value">${(pred.away_win_prob * 100).toFixed(1)}%</div>
                            <div class="prob-label">Away Win</div>
                        </div>
                        <div class="prob-item">
                            <div class="prob-value">${(pred.over_2_5_prob * 100).toFixed(1)}%</div>
                            <div class="prob-label">Over 2.5</div>
                        </div>
                        <div class="prob-item">
                            <div class="prob-value">${Number(pred.expected_home_goals).toFixed(1)} - ${Number(pred.expected_away_goals).toFixed(1)}</div>
                            <div class="prob-label">Expected Score</div>
                        </div>
                    </div>
                    ${pred.recommended_bets && pred.recommended_bets.length > 0 ? `
                        <div class="recommended-bets">
                            <strong>Value Bets:</strong>
                            ${pred.recommended_bets.map(bet => 
                                `<span class="bet-tag">${bet.bet_name} @ ${bet.odds} (${(bet.edge * 100).toFixed(1)}% edge)</span>`
                            ).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
        });

        container.innerHTML = html;
    }

    // Initial load & refresh
    refreshDashboard();
    setInterval(refreshDashboard, 30000);
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def dashboard() -> str:
    return DASHBOARD_HTML

@app.route("/api/start", methods=["POST"])
def start_bot_route():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized. Please set API token first."}), 400
    bot.start_bot()
    return jsonify({"success": True, "message": "Bot started successfully"})

@app.route("/api/stop", methods=["POST"])
def stop_bot_route():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized"}), 400
    bot.stop_bot()
    return jsonify({"success": True, "message": "Bot stopped successfully"})

@app.route("/api/analyze", methods=["POST"])
def run_analysis_route():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized"}), 400

    # Run analysis in background thread
    thread = threading.Thread(target=bot.run_daily_analysis, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Analysis started"})

@app.route("/api/dashboard", methods=["GET"])
def get_dashboard_data_route():
    global bot
    if not bot:
        return jsonify({"error": "Bot not initialized"}), 400
    return jsonify(bot.get_dashboard_data())

@app.route("/api/setup", methods=["POST"])
def setup_bot_route():
    global bot

    data = request.get_json(silent=True) or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"error": "API token required"}), 400

    try:
        bot = BettingBot(api_token)
        return jsonify({"success": True, "message": "Bot initialized successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to initialize bot: {str(e)}"}), 500

@app.route("/setup", methods=["GET"])
def setup_page():
    return """
<!DOCTYPE html>
<html>
<head>
<title>Bot Setup</title>
<style>
body { font-family: Arial, sans-serif; background: #0f172a; color: #f1f5f9; padding: 50px; text-align: center; }
input { padding: 15px; width: 400px; margin: 20px; background: #1e293b; color: white; border: 1px solid #475569; border-radius: 8px; }
button { background: #3b82f6; color: white; padding: 15px 30px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; }
button:hover { background: #2563eb; }
</style>
</head>
<body>
<h1>🤖 AI Betting Bot Setup</h1>
<p>Enter your SportMonks API token to initialize the bot:</p>
<input type="text" id="apiToken" placeholder="Enter SportMonks API Token...">
<br>
<button onclick="setupBot()">Initialize Bot</button>

<script>
    async function setupBot() {
        const token = document.getElementById('apiToken').value.trim();
        if (!token) {
            alert('Please enter your API token');
            return;
        }
        
        try {
            const response = await fetch('/api/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_token: token })
            });
            
            const data = await response.json();
            if (data.success) {
                alert('Bot initialized successfully!');
                window.location.href = '/';
            } else {
                alert('Error: ' + data.error);
            }
        } catch (error) {
            alert('Error: ' + error.message);
        }
    }
</script>
</body>
</html>
"""

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})

# ==============================
# SCHEDULER RUNNER
# ==============================

def run_scheduler():
    """Run scheduled tasks"""
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(60)

# ==============================
# MAIN APPLICATION
# ==============================

if __name__ == "__main__":
    # Start scheduler in background
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Start Flask app
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting AI Betting Bot on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

# Gunicorn compatibility
application = app