#!/usr/bin/env python3
"""
ADVANCED SPORTMONKS SUBSCRIPTION ANALYZER & BETTING BOT FOUNDATION

This analyzer will:

1. Confirm API authentication and subscription tier
1. Discover all available leagues and competitions
1. Map all v3 data sources and endpoints
1. Count matches (live, upcoming, completed)
1. Test all betting/odds endpoints
1. Generate comprehensive data inventory
1. Build foundation for AI betting bot
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import requests
from flask import Flask, jsonify, Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SubscriptionCapability:
    endpoint: str
    name: str
    category: str
    accessible: bool
    data_count: int
    sample_data: Dict
    tier_required: str
    rate_limit: Optional[int] = None
    monthly_limit: Optional[int] = None


@dataclass
class DataInventory:
    # Core subscription info
    subscription_tier: str = "unknown"
    api_authenticated: bool = False
    rate_limits: Dict[str, int] = field(default_factory=dict)

    # League and competition data
    total_leagues: int = 0
    accessible_leagues: List[Dict] = field(default_factory=list)
    current_seasons: List[Dict] = field(default_factory=list)

    # Match data
    total_fixtures_today: int = 0
    total_fixtures_tomorrow: int = 0
    live_matches_count: int = 0
    inplay_matches_count: int = 0
    upcoming_matches_7days: int = 0

    # Betting/Odds data
    bookmakers_available: List[Dict] = field(default_factory=list)
    betting_markets_available: List[Dict] = field(default_factory=list)
    odds_coverage_leagues: List[str] = field(default_factory=list)
    pre_match_odds_count: int = 0
    live_odds_count: int = 0

    # Team and player data
    total_teams: int = 0
    total_players: int = 0
    team_statistics_available: bool = False
    player_statistics_available: bool = False

    # Advanced features
    ai_predictions_possible: bool = False
    historical_data_depth: str = "unknown"
    real_time_data_available: bool = False

    # Endpoint capabilities
    working_endpoints: List[SubscriptionCapability] = field(default_factory=list)
    failed_endpoints: List[SubscriptionCapability] = field(default_factory=list)

    # Bot building recommendations
    recommended_data_sources: List[str] = field(default_factory=list)
    betting_bot_readiness: str = "unknown"
    missing_premium_features: List[str] = field(default_factory=list)


class SportMonksSubscriptionAnalyzer:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_url = "https://api.sportmonks.com/v3/odds"
        self.core_url = "https://api.sportmonks.com/v3/core"

        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "SportMonks-Analyzer/3.0"
        })

        self.inventory = DataInventory()
        self.analysis_progress = {
            "phase": "idle",
            "current_test": "",
            "progress": 0,
            "total_phases": 8,
            "detailed_log": [],
            "errors": []
        }
        self.is_analyzing = False

    def _api_request(self, url: str, params: Dict = None) -> Tuple[int, Dict, str]:
        """Make API request with comprehensive error handling"""
        try:
            # Always include api_token in params for v3 compatibility
            request_params = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            response = self.session.get(url, params=request_params, timeout=30)

            # Log detailed response info
            log_entry = f"[{response.status_code}] {url}"
            if response.status_code != 200:
                log_entry += f" - {response.text[:200]}"

            self.analysis_progress["detailed_log"].append(log_entry)

            try:
                data = response.json() if response.text else {}
            except Exception:
                data = {}

            return response.status_code, data, ""

        except Exception as e:
            error_msg = f"Request failed: {str(e)[:200]}"
            self.analysis_progress["errors"].append(error_msg)
            return 0, {}, error_msg

    def phase_1_authentication_test(self):
        """Phase 1: Test API authentication and get subscription info"""
        self.analysis_progress.update({
            "phase": "authentication",
            "current_test": "Testing API authentication...",
            "progress": 1
        })

        # Test basic authentication
        status, data, _ = self._api_request(f"{self.core_url}/my/subscription")

        if status == 200:
            self.inventory.api_authenticated = True
            subscription_data = data.get("data", {})
            self.inventory.subscription_tier = subscription_data.get("tier", "unknown")

            # Extract rate limits if available
            if "rate_limit" in subscription_data:
                self.inventory.rate_limits = subscription_data["rate_limit"]
        else:
            # Fallback test with simpler endpoint
            status, _, _ = self._api_request(f"{self.base_url}/livescores")
            self.inventory.api_authenticated = (status == 200)

    def phase_2_discover_leagues(self):
        """Phase 2: Discover all accessible leagues and competitions"""
        self.analysis_progress.update({
            "phase": "leagues",
            "current_test": "Discovering leagues and competitions...",
            "progress": 2
        })

        # Get all leagues
        status, data, _ = self._api_request(f"{self.base_url}/leagues", {
            "include": "country,seasons.current",
            "per_page": "500"
        })

        if status == 200:
            leagues = data.get("data", [])
            self.inventory.total_leagues = len(leagues)
            self.inventory.accessible_leagues = leagues[:50]  # Store sample

            # Extract current seasons
            for league in leagues:
                if league.get("seasons"):
                    for season in league["seasons"]:
                        if season.get("is_current"):
                            self.inventory.current_seasons.append({
                                "league_id": league.get("id"),
                                "league_name": league.get("name"),
                                "season_id": season.get("id"),
                                "season_name": season.get("name")
                            })

    def phase_3_analyze_fixtures(self):
        """Phase 3: Analyze fixture availability and coverage"""
        self.analysis_progress.update({
            "phase": "fixtures",
            "current_test": "Analyzing fixture data coverage...",
            "progress": 3
        })

        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Today's fixtures
        status, data, _ = self._api_request(f"{self.base_url}/fixtures/date/{today}")
        if status == 200:
            self.inventory.total_fixtures_today = len(data.get("data", []))

        # Tomorrow's fixtures
        status, data, _ = self._api_request(f"{self.base_url}/fixtures/date/{tomorrow}")
        if status == 200:
            self.inventory.total_fixtures_tomorrow = len(data.get("data", []))

        # Live scores
        status, data, _ = self._api_request(f"{self.base_url}/livescores")
        if status == 200:
            self.inventory.live_matches_count = len(data.get("data", []))

        # In-play matches
        status, data, _ = self._api_request(f"{self.base_url}/livescores/inplay")
        if status == 200:
            self.inventory.inplay_matches_count = len(data.get("data", []))
            self.inventory.real_time_data_available = True

    def phase_4_betting_data_analysis(self):
        """Phase 4: Comprehensive betting and odds data analysis"""
        self.analysis_progress.update({
            "phase": "betting",
            "current_test": "Analyzing betting markets and odds...",
            "progress": 4
        })

        # Test bookmakers endpoint
        status, data, _ = self._api_request(f"{self.odds_url}/bookmakers")
        if status == 200:
            self.inventory.bookmakers_available = data.get("data", [])[:20]

        # Test betting markets
        status, data, _ = self._api_request(f"{self.odds_url}/markets")
        if status == 200:
            self.inventory.betting_markets_available = data.get("data", [])[:30]

        # Test pre-match odds
        status, data, _ = self._api_request(f"{self.odds_url}/pre-match", {
            "per_page": "100"
        })
        if status == 200:
            self.inventory.pre_match_odds_count = len(data.get("data", []))

        # Test live odds
        status, data, _ = self._api_request(f"{self.odds_url}/live", {
            "per_page": "100"
        })
        if status == 200:
            self.inventory.live_odds_count = len(data.get("data", []))

    def phase_5_team_player_data(self):
        """Phase 5: Analyze team and player data availability"""
        self.analysis_progress.update({
            "phase": "teams_players",
            "current_test": "Checking team and player data...",
            "progress": 5
        })

        # Test teams endpoint
        status, data, _ = self._api_request(f"{self.base_url}/teams", {
            "per_page": "200"
        })
        if status == 200:
            self.inventory.total_teams = len(data.get("data", []))

        # Test players endpoint
        status, data, _ = self._api_request(f"{self.base_url}/players", {
            "per_page": "200"
        })
        if status == 200:
            self.inventory.total_players = len(data.get("data", []))

        # Test team statistics
        if self.inventory.accessible_leagues:
            team_id = None
            # Try to get a team ID from fixtures
            status, data, _ = self._api_request(f"{self.base_url}/fixtures", {
                "per_page": "10",
                "include": "participants"
            })
            if status == 200:
                fixtures = data.get("data", [])
                for fixture in fixtures:
                    if fixture.get("participants"):
                        team_id = fixture["participants"][0].get("id")
                        break

            if team_id:
                status, _, _ = self._api_request(f"{self.base_url}/teams/{team_id}", {
                    "include": "statistics"
                })
                self.inventory.team_statistics_available = (status == 200)

    def phase_6_advanced_features(self):
        """Phase 6: Test advanced features for AI predictions"""
        self.analysis_progress.update({
            "phase": "advanced",
            "current_test": "Testing advanced AI prediction features...",
            "progress": 6
        })

        # Test predictions endpoint if available
        status, _, _ = self._api_request(f"{self.base_url}/predictions")
        if status == 200:
            self.inventory.ai_predictions_possible = True

        # Test historical data depth
        past_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        status, _, _ = self._api_request(f"{self.base_url}/fixtures/date/{past_date}")
        if status == 200:
            self.inventory.historical_data_depth = "30+ days"

        # Test even older data
        old_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
        status, _, _ = self._api_request(f"{self.base_url}/fixtures/date/{old_date}")
        if status == 200:
            self.inventory.historical_data_depth = "1+ years"

    def phase_7_comprehensive_endpoint_testing(self):
        """Phase 7: Test all critical endpoints for bot building"""
        self.analysis_progress.update({
            "phase": "endpoints",
            "current_test": "Testing all critical endpoints...",
            "progress": 7
        })

        critical_endpoints = [
            {"url": f"{self.base_url}/fixtures", "name": "Fixtures", "category": "core"},
            {"url": f"{self.base_url}/livescores", "name": "Live Scores", "category": "core"},
            {"url": f"{self.base_url}/leagues", "name": "Leagues", "category": "core"},
            {"url": f"{self.base_url}/teams", "name": "Teams", "category": "core"},
            {"url": f"{self.base_url}/players", "name": "Players", "category": "core"},
            {"url": f"{self.odds_url}/pre-match", "name": "Pre-match Odds", "category": "betting"},
            {"url": f"{self.odds_url}/live", "name": "Live Odds", "category": "betting"},
            {"url": f"{self.odds_url}/bookmakers", "name": "Bookmakers", "category": "betting"},
            {"url": f"{self.odds_url}/markets", "name": "Markets", "category": "betting"},
            {"url": f"{self.base_url}/predictions", "name": "Predictions", "category": "ai"},
            {"url": f"{self.base_url}/standings", "name": "Standings", "category": "statistics"},
            {"url": f"{self.base_url}/head2head", "name": "Head to Head", "category": "statistics"},
        ]

        for endpoint in critical_endpoints:
            status, data, _ = self._api_request(endpoint["url"], {"per_page": "10"})

            capability = SubscriptionCapability(
                endpoint=endpoint["url"],
                name=endpoint["name"],
                category=endpoint["category"],
                accessible=(status == 200),
                data_count=len(data.get("data", [])) if status == 200 else 0,
                sample_data=data.get("data", [{}])[0] if status == 200 and data.get("data") else {},
                tier_required="unknown"
            )

            if capability.accessible:
                self.inventory.working_endpoints.append(capability)
            else:
                self.inventory.failed_endpoints.append(capability)

    def phase_8_generate_recommendations(self):
        """Phase 8: Generate AI betting bot recommendations"""
        self.analysis_progress.update({
            "phase": "recommendations",
            "current_test": "Generating bot building recommendations...",
            "progress": 8
        })

        # Determine bot readiness
        core_endpoints = len([e for e in self.inventory.working_endpoints if e.category == "core"])
        betting_endpoints = len([e for e in self.inventory.working_endpoints if e.category == "betting"])

        if core_endpoints >= 3 and betting_endpoints >= 2:
            self.inventory.betting_bot_readiness = "READY"
        elif core_endpoints >= 2 and betting_endpoints >= 1:
            self.inventory.betting_bot_readiness = "PARTIAL"
        else:
            self.inventory.betting_bot_readiness = "NOT_READY"

        # Generate recommendations
        if self.inventory.pre_match_odds_count > 0:
            self.inventory.recommended_data_sources.append("Pre-match odds for value betting")

        if self.inventory.live_odds_count > 0:
            self.inventory.recommended_data_sources.append("Live odds for in-play betting")

        if self.inventory.team_statistics_available:
            self.inventory.recommended_data_sources.append("Team statistics for prediction models")

        if self.inventory.historical_data_depth != "unknown":
            self.inventory.recommended_data_sources.append(
                f"Historical data ({self.inventory.historical_data_depth}) for ML training"
            )

        # Identify missing premium features
        if not self.inventory.ai_predictions_possible:
            self.inventory.missing_premium_features.append("AI Predictions endpoint")

        if self.inventory.pre_match_odds_count == 0:
            self.inventory.missing_premium_features.append("Pre-match odds access")

        if self.inventory.live_odds_count == 0:
            self.inventory.missing_premium_features.append("Live odds access")

    def run_complete_analysis(self):
        """Run complete subscription analysis"""
        self.is_analyzing = True

        try:
            self.phase_1_authentication_test()
            time.sleep(1)

            self.phase_2_discover_leagues()
            time.sleep(1)

            self.phase_3_analyze_fixtures()
            time.sleep(1)

            self.phase_4_betting_data_analysis()
            time.sleep(1)

            self.phase_5_team_player_data()
            time.sleep(1)

            self.phase_6_advanced_features()
            time.sleep(1)

            self.phase_7_comprehensive_endpoint_testing()
            time.sleep(1)

            self.phase_8_generate_recommendations()

            self.analysis_progress.update({
                "phase": "completed",
                "current_test": "Analysis complete!",
                "progress": 8
            })

        except Exception as e:
            self.analysis_progress.update({
                "phase": "error",
                "current_test": f"Error: {str(e)[:200]}",
                "progress": 0
            })
        finally:
            self.is_analyzing = False

    def get_copyable_report(self) -> str:
        """Generate a comprehensive copyable report"""
        lines = []
        lines.append("=== SPORTMONKS SUBSCRIPTION ANALYSIS REPORT ===")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("🔐 AUTHENTICATION & SUBSCRIPTION")
        lines.append(f"✅ API Authenticated: {self.inventory.api_authenticated}")
        lines.append(f"📊 Subscription Tier: {self.inventory.subscription_tier}")
        lines.append(f"🚦 Rate Limits: {self.inventory.rate_limits}")
        lines.append("")
        lines.append("📋 LEAGUE & COMPETITION DATA")
        lines.append(f"🏆 Total Leagues Available: {self.inventory.total_leagues}")
        lines.append(f"⚽ Current Active Seasons: {len(self.inventory.current_seasons)}")
        lines.append("🔥 Top Accessible Leagues:")
        leagues_txt = "\n".join([
            f"   • {league.get('name', 'Unknown')} (ID: {league.get('id')})"
            for league in self.inventory.accessible_leagues[:10]
        ])
        lines.append(leagues_txt)
        lines.append("")
        lines.append("📅 FIXTURE COVERAGE")
        lines.append(f"📆 Today’s Fixtures: {self.inventory.total_fixtures_today}")
        lines.append(f"📅 Tomorrow’s Fixtures: {self.inventory.total_fixtures_tomorrow}")
        lines.append(f"🔴 Live Matches Now: {self.inventory.live_matches_count}")
        lines.append(f"⚡ In-Play Matches: {self.inventory.inplay_matches_count}")
        lines.append("")
        lines.append("💰 BETTING & ODDS DATA")
        lines.append(f"📚 Available Bookmakers: {len(self.inventory.bookmakers_available)}")
        lines.append(f"🎯 Betting Markets: {len(self.inventory.betting_markets_available)}")
        lines.append(f"📊 Pre-match Odds Available: {self.inventory.pre_match_odds_count}")
        lines.append(f"⚡ Live Odds Available: {self.inventory.live_odds_count}")
        lines.append("")
        lines.append("👥 TEAM & PLAYER DATA")
        lines.append(f"🏟️ Total Teams: {self.inventory.total_teams}")
        lines.append(f"👤 Total Players: {self.inventory.total_players}")
        lines.append(f"📊 Team Statistics: {'✅ Available' if self.inventory.team_statistics_available else '❌ Not Available'}")
        lines.append("")
        lines.append("🤖 AI PREDICTION CAPABILITIES")
        lines.append(f"🔮 AI Predictions: {'✅ Available' if self.inventory.ai_predictions_possible else '❌ Not Available'}")
        lines.append(f"📈 Historical Data: {self.inventory.historical_data_depth}")
        lines.append(f"⚡ Real-time Data: {'✅ Available' if self.inventory.real_time_data_available else '❌ Not Available'}")
        lines.append("")
        lines.append("🛠️ ENDPOINT STATUS")
        lines.append(f"✅ Working Endpoints: {len(self.inventory.working_endpoints)}")
        lines.extend([f"   • {ep.name} ({ep.category})" for ep in self.inventory.working_endpoints])
        lines.append("")
        lines.append(f"❌ Failed Endpoints: {len(self.inventory.failed_endpoints)}")
        lines.extend([f"   • {ep.name} ({ep.category})" for ep in self.inventory.failed_endpoints])
        lines.append("")
        lines.append(f"🚀 BETTING BOT READINESS: {self.inventory.betting_bot_readiness}")
        lines.append("")
        lines.append("💡 RECOMMENDED DATA SOURCES FOR AI BOT:")
        lines.extend([f"   • {rec}" for rec in self.inventory.recommended_data_sources])
        lines.append("")
        lines.append("🔒 MISSING PREMIUM FEATURES:")
        lines.extend([f"   • {missing}" for missing in self.inventory.missing_premium_features])
        lines.append("")
        lines.append("📋 KEY ENDPOINTS FOR BOT DEVELOPMENT:")
        lines.append(f"• Fixtures: {self.base_url}/fixtures")
        lines.append(f"• Live Scores: {self.base_url}/livescores")
        lines.append(f"• Pre-match Odds: {self.odds_url}/pre-match")
        lines.append(f"• Live Odds: {self.odds_url}/live")
        lines.append(f"• Teams: {self.base_url}/teams")
        lines.append(f"• Leagues: {self.base_url}/leagues")
        lines.append("")
        lines.append("🔗 CRITICAL API CALLS FOR BETTING BOT:")
        lines.append("")
        lines.append("1. Get today’s fixtures with odds")
        lines.append("1. Monitor live score updates")
        lines.append("1. Fetch pre-match betting markets")
        lines.append("1. Track live odds changes")
        lines.append("1. Analyze team statistics")
        lines.append("1. Historical performance data")
        lines.append("")
        lines.append("=== END REPORT ===")
        return "\n".join(lines).strip()


# Flask Application
app = Flask(__name__)

analyzer: Optional[SportMonksSubscriptionAnalyzer] = None

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>SportMonks Subscription Analyzer</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #10b981; text-align: center; margin-bottom: 30px; }
        .card { background: #1e293b; border: 1px solid #334155; padding: 25px; margin: 20px 0; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .btn { background: #3b82f6; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; transition: all 0.3s; }
        .btn:hover { background: #2563eb; transform: translateY(-1px); }
        .btn:disabled { background: #64748b; cursor: not-allowed; }
        input { background: #0f172a; color: #e2e8f0; border: 2px solid #475569; padding: 12px; width: 400px; border-radius: 8px; font-size: 16px; }
        input:focus { border-color: #3b82f6; outline: none; }
        .progress { width: 100%; height: 12px; background: #334155; border-radius: 6px; overflow: hidden; margin: 15px 0; }
        .progress-bar { height: 100%; background: linear-gradient(90deg, #10b981, #059669); width: 0%; transition: width 0.5s ease; }
        .status { margin-top: 15px; color: #94a3b8; font-size: 14px; }
        .phase { color: #3b82f6; font-weight: bold; }
        .results { background: #0f172a; padding: 20px; border-radius: 8px; margin-top: 20px; }
        .metric { display: inline-block; margin: 10px 15px; padding: 10px; background: #1e293b; border-radius: 6px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #10b981; }
        .metric-label { font-size: 12px; color: #94a3b8; }
        .report-section { margin: 20px 0; }
        .report-text { background: #0f172a; padding: 15px; border-radius: 6px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .copy-btn { background: #059669; margin-top: 10px; }
        .copy-btn:hover { background: #047857; }
        .readiness-ready { color: #10b981; font-weight: bold; }
        .readiness-partial { color: #f59e0b; font-weight: bold; }
        .readiness-not { color: #ef4444; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 SportMonks Subscription Analyzer</h1>
        <p style="text-align: center; color: #94a3b8; margin-bottom: 30px;">
            Discover your subscription capabilities, analyze betting data access, and get AI bot recommendations
        </p>

        <div class="card">
            <h3>🚀 Start Analysis</h3>
            <input id="apiToken" type="text" placeholder="Enter your SportMonks API Token...">
            <br><br>
            <button class="btn" id="analyzeBtn" onclick="startAnalysis()">Analyze Subscription</button>

            <div class="progress">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="status">
                <span class="phase" id="phase">Ready</span> - <span id="currentTest">Enter your API token to begin</span>
            </div>
        </div>

        <div class="card" id="resultsCard" style="display: none;">
            <h3>📊 Analysis Results</h3>
            <div id="quickMetrics"></div>
            <div id="readinessStatus"></div>
        </div>

        <div class="card" id="reportCard" style="display: none;">
            <h3>📋 Complete Analysis Report</h3>
            <button class="btn copy-btn" onclick="copyReport()">📋 Copy Full Report</button>
            <div class="report-section">
                <div class="report-text" id="fullReport"></div>
            </div>
        </div>
    </div>

<script>
    let pollTimer = null;
    let fullReportData = "";

    async function startAnalysis() {
        const token = document.getElementById('apiToken').value.trim();
        if (!token) {
            alert('Please enter your SportMonks API token');
            return;
        }

        const btn = document.getElementById('analyzeBtn');
        btn.disabled = true;
        btn.textContent = 'Analyzing...';

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_token: token })
            });

            if (response.ok) {
                startPolling();
            } else {
                throw new Error('Failed to start analysis');
            }
        } catch (error) {
            alert('Error: ' + error.message);
            btn.disabled = false;
            btn.textContent = 'Analyze Subscription';
        }
    }

    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);

        pollTimer = setInterval(async () => {
            try {
                const response = await fetch('/api/progress');
                const data = await response.json();

                const progress = (data.progress / 8) * 100;
                document.getElementById('progressBar').style.width = progress + '%';
                document.getElementById('phase').textContent = String(data.phase || '').toUpperCase();
                document.getElementById('currentTest').textContent = data.current_test || '';

                if (data.phase === 'completed') {
                    clearInterval(pollTimer);
                    loadResults();
                } else if (data.phase === 'error') {
                    clearInterval(pollTimer);
                    alert('Analysis failed: ' + data.current_test);
                    resetUI();
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 1000);
    }

    async function loadResults() {
        try {
            const response = await fetch('/api/results');
            const data = await response.json();

            displayResults(data);
            resetUI();
        } catch (error) {
            alert('Error loading results');
            resetUI();
        }
    }

    function displayResults(data) {
        const inventory = data.inventory || {};
        const readiness = inventory.betting_bot_readiness || 'unknown';

        const metrics = `
            <div class="metric">
                <div class="metric-value">${inventory.total_leagues || 0}</div>
                <div class="metric-label">Leagues</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.total_fixtures_today || 0}</div>
                <div class="metric-label">Today's Matches</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.live_matches_count || 0}</div>
                <div class="metric-label">Live Matches</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.pre_match_odds_count || 0}</div>
                <div class="metric-label">Pre-match Odds</div>
            </div>
        `;

        document.getElementById('quickMetrics').innerHTML = metrics;

        let cls = 'readiness-not';
        if (readiness === 'READY') cls = 'readiness-ready';
        else if (readiness === 'PARTIAL') cls = 'readiness-partial';

        document.getElementById('readinessStatus').innerHTML =
            `<p>Readiness: <span class="${cls}">${readiness}</span></p>`;

        fullReportData = data.report || '';
        document.getElementById('fullReport').textContent = fullReportData;

        document.getElementById('resultsCard').style.display = 'block';
        document.getElementById('reportCard').style.display = 'block';
    }

    function copyReport() {
        if (!fullReportData) return;
        navigator.clipboard.writeText(fullReportData).then(() => {
            alert('Report copied to clipboard!');
        }).catch(() => {
            alert('Failed to copy. Select and copy manually.');
        });
    }

    function resetUI() {
        const btn = document.getElementById('analyzeBtn');
        btn.disabled = false;
        btn.textContent = 'Analyze Subscription';
    }
</script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def home() -> Response:
    return Response(HTML_TEMPLATE, mimetype="text/html")


@app.route("/api/analyze", methods=["POST"])
def start_analysis():
    global analyzer
    try:
        payload = (requests.utils.json.loads(requests.utils.json.dumps({})) if False else None)  # no-op to keep logic unchanged
    except Exception:
        payload = None

    try:
        from flask import request
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    api_token = (data.get("api_token") or "").strip()
    if not api_token:
        return jsonify({"error": "API token required"}), 400

    if analyzer and analyzer.is_analyzing:
        return jsonify({"error": "Analysis already running"}), 400

    analyzer = SportMonksSubscriptionAnalyzer(api_token)

    thread = threading.Thread(target=analyzer.run_complete_analysis, daemon=True)
    thread.start()

    return jsonify({"success": True})


@app.route("/api/progress", methods=["GET"])
def progress():
    if not analyzer:
        return jsonify({
            "phase": "idle",
            "current_test": "",
            "progress": 0
        })
    return jsonify(analyzer.analysis_progress)


@app.route("/api/results", methods=["GET"])
def results():
    if not analyzer:
        return jsonify({"error": "No analysis run"}), 400
    if analyzer.analysis_progress.get("phase") != "completed":
        return jsonify({"error": "Analysis not complete"}), 400

    report = analyzer.get_copyable_report()
    # Convert dataclasses inside lists to dicts for JSON safety
    inv = analyzer.inventory
    working = [vars(w) for w in inv.working_endpoints]
    failed = [vars(f) for f in inv.failed_endpoints]

    inventory_dict = {
        **vars(inv),
        "working_endpoints": working,
        "failed_endpoints": failed
    }

    return jsonify({
        "inventory": inventory_dict,
        "report": report
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0"
    })


# Gunicorn compatibility
application = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    logger.info(f"Starting analyzer on port {port}")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true", threaded=True)