#!/usr/bin/env python3
"""
COMPREHENSIVE SPORTMONKS SUBSCRIPTION ANALYZER - DEPLOYMENT FIXED

Analyzes all your SportMonks components for AI betting bot development.
Fixed deployment issues and syntax errors.
"""

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import requests
from flask import Flask, jsonify, request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ComponentCapability:
    component_name: str
    endpoint_url: str
    category: str
    accessible: bool
    data_count: int
    sample_data: Dict[str, Any]
    api_features: List[str] = field(default_factory=list)
    betting_value: str = "medium"
    ai_potential: str = "medium"


@dataclass
class ComprehensiveInventory:
    # Authentication & Subscription
    subscription_tier: str = "unknown"
    api_authenticated: bool = False
    total_components_enabled: int = 0

    # Core Football Data
    leagues_available: int = 0
    teams_available: int = 0
    players_available: int = 0
    fixtures_today: int = 0
    fixtures_tomorrow: int = 0
    live_matches: int = 0

    # Odds & Betting Components
    bookmakers_count: int = 0
    betting_markets_count: int = 0
    pre_match_odds_count: int = 0
    live_odds_count: int = 0
    predictions_available: bool = False

    # Advanced Analytics
    xg_match_data_available: bool = False
    xg_player_efficiency_available: bool = False
    pressure_index_available: bool = False
    trends_available: bool = False

    # Statistics & Analysis
    match_centre_available: bool = False
    player_profiles_available: bool = False
    team_statistics_available: bool = False
    head2head_available: bool = False
    topscorers_available: bool = False

    # Real-time Features
    live_standings_available: bool = False
    live_commentary_available: bool = False
    events_timeline_available: bool = False
    lineup_data_available: bool = False

    # Supplementary Data
    injuries_suspensions_available: bool = False
    referee_stats_available: bool = False
    tv_stations_available: bool = False
    news_available: bool = False

    # Component Analysis
    working_components: List[ComponentCapability] = field(default_factory=list)
    failed_components: List[ComponentCapability] = field(default_factory=list)
    high_value_components: List[str] = field(default_factory=list)
    ai_ready_features: List[str] = field(default_factory=list)

    # Bot Building Assessment
    bot_readiness_score: float = 0.0
    recommended_strategies: List[str] = field(default_factory=list)
    advanced_features_available: List[str] = field(default_factory=list)


class ComprehensiveSubscriptionAnalyzer:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_url = "https://api.sportmonks.com/v3/odds"
        self.core_url = "https://api.sportmonks.com/v3/core"

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "User-Agent": "SportMonks-Comprehensive-Analyzer/1.0"
        })

        self.inventory = ComprehensiveInventory()
        self.analysis_progress: Dict[str, Any] = {
            "phase": "idle",
            "current_test": "",
            "progress": 0,
            "total_phases": 8,
            "detailed_log": [],
            "errors": []
        }
        self.is_analyzing = False

    def _api_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any], str]:
        """Enhanced API request with comprehensive logging"""
        try:
            request_params: Dict[str, Any] = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            response = self.session.get(url, params=request_params, timeout=30)

            log_entry = f"[{response.status_code}] {url}"
            if response.status_code != 200:
                log_entry += f" - {response.text[:200].replace(chr(10), ' ')}"

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

    def test_component(
        self,
        component_name: str,
        endpoint_url: str,
        category: str,
        params: Optional[Dict[str, Any]] = None,
        ai_potential: str = "medium"
    ) -> ComponentCapability:
        """Test individual component capability"""
        status, data, _ = self._api_request(endpoint_url, params or {"per_page": "25"})

        data_count = 0
        sample_data: Dict[str, Any] = {}
        api_features: List[str] = []

        if status == 200 and isinstance(data, dict) and "data" in data:
            data_items = data["data"]
            if isinstance(data_items, list):
                data_count = len(data_items)
                sample_data = data_items[0] if data_items else {}
            else:
                data_count = 1
                sample_data = data_items if isinstance(data_items, dict) else {}

            if sample_data and isinstance(sample_data, dict):
                api_features = list(sample_data.keys())[:10]

        return ComponentCapability(
            component_name=component_name,
            endpoint_url=endpoint_url,
            category=category,
            accessible=(status == 200),
            data_count=data_count,
            sample_data=sample_data,
            api_features=api_features,
            betting_value="high" if ("odds" in component_name.lower() or "prediction" in component_name.lower()) else "medium",
            ai_potential=ai_potential
        )

    def phase_1_authentication_test(self):
        self.analysis_progress.update({
            "phase": "authentication",
            "current_test": "Testing API authentication...",
            "progress": 1
        })

        status, data, _ = self._api_request(f"{self.core_url}/my/subscription")

        if status == 200:
            self.inventory.api_authenticated = True
            subscription_data = data.get("data", {})
            self.inventory.subscription_tier = subscription_data.get("tier") or subscription_data.get("plan", "Standard+")
        else:
            status, _, _ = self._api_request(f"{self.base_url}/livescores")
            self.inventory.api_authenticated = (status == 200)

    def phase_2_core_football_data(self):
        self.analysis_progress.update({
            "phase": "core_data",
            "current_test": "Testing core football data...",
            "progress": 2
        })

        comp = self.test_component("Leagues", f"{self.base_url}/leagues", "core", {"per_page": "200"}, "high")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.leagues_available = comp.data_count

        comp = self.test_component("Teams", f"{self.base_url}/teams", "core", {"per_page": "200"}, "high")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.teams_available = comp.data_count

        comp = self.test_component("Players", f"{self.base_url}/players", "core", {"per_page": "200"}, "medium")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.players_available = comp.data_count

        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        comp = self.test_component("Today's Fixtures", f"{self.base_url}/fixtures/date/{today}", "core", ai_potential="high")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.fixtures_today = comp.data_count

        comp = self.test_component("Tomorrow's Fixtures", f"{self.base_url}/fixtures/date/{tomorrow}", "core", ai_potential="high")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.fixtures_tomorrow = comp.data_count

        comp = self.test_component("Live Scores", f"{self.base_url}/livescores", "core", ai_potential="high")
        (self.inventory.working_components if comp.accessible else self.inventory.failed_components).append(comp)
        if comp.accessible:
            self.inventory.live_matches = comp.data_count

    def phase_3_odds_and_predictions(self):
        self.analysis_progress.update({
            "phase": "odds_predictions",
            "current_test": "Testing odds and prediction components...",
            "progress": 3
        })

        comp = self.test_component("Bookmakers", f"{self.odds_url}/bookmakers", "betting", ai_potential="high")
        if comp.accessible:
            self.inventory.bookmakers_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Bookmakers Data")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Betting Markets", f"{self.odds_url}/markets", "betting", ai_potential="high")
        if comp.accessible:
            self.inventory.betting_markets_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Betting Markets")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Pre-match Odds", f"{self.odds_url}/pre-match", "betting", {"per_page": "100"}, "high")
        if comp.accessible:
            self.inventory.pre_match_odds_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Pre-match Odds")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Live Odds", f"{self.odds_url}/inplay", "betting", {"per_page": "100"}, "high")
        if comp.accessible:
            self.inventory.live_odds_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Live Odds")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("AI Predictions", f"{self.base_url}/predictions", "ai", ai_potential="high")
        if comp.accessible:
            self.inventory.predictions_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("AI Match Predictions")
        else:
            self.inventory.failed_components.append(comp)

    def phase_4_advanced_analytics(self):
        self.analysis_progress.update({
            "phase": "advanced_analytics",
            "current_test": "Testing advanced analytics (xG, Pressure Index)...",
            "progress": 4
        })

        comp = self.test_component("Expected Goals (xG)", f"{self.base_url}/fixtures", "analytics",
                                   {"include": "xg", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.xg_match_data_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Expected Goals (xG) Analysis")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Player xG Efficiency", f"{self.base_url}/players", "analytics",
                                   {"include": "statistics", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.xg_player_efficiency_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Player xG Efficiency")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Pressure Index", f"{self.base_url}/fixtures", "analytics",
                                   {"include": "pressureIndex", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.pressure_index_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Pressure Index Analytics")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Team Trends", f"{self.base_url}/teams", "analytics",
                                   {"include": "trends", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.trends_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Team Performance Trends")
        else:
            self.inventory.failed_components.append(comp)

    def phase_5_statistics_components(self):
        self.analysis_progress.update({
            "phase": "statistics",
            "current_test": "Testing statistics and analysis components...",
            "progress": 5
        })

        comp = self.test_component("Head to Head", f"{self.base_url}/head2head", "statistics", ai_potential="high")
        if comp.accessible:
            self.inventory.head2head_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Head-to-Head Analysis")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Team Statistics", f"{self.base_url}/teams", "statistics",
                                   {"include": "statistics", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.team_statistics_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Detailed Team Statistics")
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Player Profiles", f"{self.base_url}/players", "statistics",
                                   {"include": "detailedStatistics", "per_page": "25"}, "medium")
        if comp.accessible:
            self.inventory.player_profiles_available = True
            self.inventory.working_components.append(comp)
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Topscorers", f"{self.base_url}/topscorers", "statistics", ai_potential="medium")
        if comp.accessible:
            self.inventory.topscorers_available = True
            self.inventory.working_components.append(comp)
        else:
            self.inventory.failed_components.append(comp)

        comp = self.test_component("Standings", f"{self.base_url}/standings", "statistics", ai_potential="high")
        if comp.accessible:
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("League Standings Analysis")
        else:
            self.inventory.failed_components.append(comp)

    def run_complete_analysis(self):
        self.is_analyzing = True
        try:
            self.phase_1_authentication_test()
            time.sleep(0.5)
            self.phase_2_core_football_data()
            time.sleep(0.5)
            self.phase_3_odds_and_predictions()
            time.sleep(0.5)
            self.phase_4_advanced_analytics()
            time.sleep(0.5)
            self.phase_5_statistics_components()
            time.sleep(0.5)

            self.analysis_progress.update({
                "phase": "scoring",
                "current_test": "Calculating AI bot readiness...",
                "progress": 6
            })

            score = 0.0

            if self.inventory.leagues_available > 0: score += 5
            if self.inventory.teams_available > 0: score += 5
            if self.inventory.fixtures_today > 0: score += 10
            if self.inventory.live_matches >= 0: score += 10

            if self.inventory.bookmakers_count > 0: score += 8
            if self.inventory.betting_markets_count > 0: score += 7
            if self.inventory.pre_match_odds_count > 0: score += 10

            if self.inventory.xg_match_data_available: score += 8
            if self.inventory.pressure_index_available: score += 7
            if self.inventory.trends_available: score += 5
            if self.inventory.predictions_available: score += 5

            if self.inventory.head2head_available: score += 5
            if self.inventory.team_statistics_available: score += 5

            self.inventory.bot_readiness_score = min(score, 100.0)

            self.analysis_progress.update({
                "phase": "strategies",
                "current_test": "Generating betting strategies...",
                "progress": 7
            })

            if self.inventory.pre_match_odds_count > 0:
                self.inventory.recommended_strategies.append("Pre-match Value Betting Analysis")

            if self.inventory.live_odds_count > 0:
                self.inventory.recommended_strategies.append("Live Betting Opportunity Detection")

            if self.inventory.xg_match_data_available:
                self.inventory.recommended_strategies.append("Expected Goals (xG) Based Predictions")
                self.inventory.recommended_strategies.append("Over/Under Goals Market Analysis")

            if self.inventory.trends_available and self.inventory.head2head_available:
                self.inventory.recommended_strategies.append("Team Form & H2H Trend Analysis")

            if len(self.inventory.ai_ready_features) >= 5:
                self.inventory.recommended_strategies.append("Multi-Factor AI Prediction Model")

            self.inventory.total_components_enabled = len(self.inventory.working_components)

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

    def get_comprehensive_report(self) -> str:
        report = f"""
=== COMPREHENSIVE SPORTMONKS SUBSCRIPTION ANALYSIS ===
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔐 AUTHENTICATION & SUBSCRIPTION
✅ API Authenticated: {self.inventory.api_authenticated}
📊 Subscription Tier: {self.inventory.subscription_tier}
🎯 Total Components Working: {self.inventory.total_components_enabled}
📈 AI Bot Readiness Score: {self.inventory.bot_readiness_score:.1f}/100

🏈 CORE FOOTBALL DATA
🏆 Leagues Available: {self.inventory.leagues_available}
👥 Teams Available: {self.inventory.teams_available}
👤 Players Available: {self.inventory.players_available}
📅 Today’s Fixtures: {self.inventory.fixtures_today}
📅 Tomorrow’s Fixtures: {self.inventory.fixtures_tomorrow}
🔴 Live Matches: {self.inventory.live_matches}

💰 ODDS & BETTING COMPONENTS
📚 Bookmakers: {self.inventory.bookmakers_count}
🎯 Betting Markets: {self.inventory.betting_markets_count}
📊 Pre-match Odds: {self.inventory.pre_match_odds_count}
⚡ Live Odds: {self.inventory.live_odds_count}
🤖 AI Predictions: {"✅ Available" if self.inventory.predictions_available else "❌ Not Available"}

📊 ADVANCED ANALYTICS
⚽ Expected Goals (xG): {"✅ Available" if self.inventory.xg_match_data_available else "❌ Not Available"}
👤 Player xG Efficiency: {"✅ Available" if self.inventory.xg_player_efficiency_available else "❌ Not Available"}
📈 Pressure Index: {"✅ Available" if self.inventory.pressure_index_available else "❌ Not Available"}
📉 Performance Trends: {"✅ Available" if self.inventory.trends_available else "❌ Not Available"}

📈 STATISTICS & ANALYSIS
🆚 Head-to-Head: {"✅ Available" if self.inventory.head2head_available else "❌ Not Available"}
👥 Team Statistics: {"✅ Available" if self.inventory.team_statistics_available else "❌ Not Available"}
👤 Player Profiles: {"✅ Available" if self.inventory.player_profiles_available else "❌ Not Available"}
🏆 Topscorers: {"✅ Available" if self.inventory.topscorers_available else "❌ Not Available"}

🚀 HIGH-VALUE COMPONENTS FOR AI BETTING BOT:
{chr(10).join([f"   ✅ {comp}" for comp in self.inventory.high_value_components])}

🤖 AI-READY FEATURES:
{chr(10).join([f"   🎯 {feature}" for feature in self.inventory.ai_ready_features])}

💡 RECOMMENDED BETTING STRATEGIES:
{chr(10).join([f"   🎲 {strategy}" for strategy in self.inventory.recommended_strategies])}

🛠️ WORKING COMPONENTS ({len(self.inventory.working_components)} total):
{chr(10).join([f"   ✅ {comp.component_name} ({comp.category}) - {comp.data_count} items" for comp in self.inventory.working_components])}

❌ FAILED COMPONENTS ({len(self.inventory.failed_components)} total):
{chr(10).join([f"   ❌ {comp.component_name} ({comp.category})" for comp in self.inventory.failed_components])}

📋 CRITICAL API ENDPOINTS FOR BOT DEVELOPMENT:

🔑 CORE DATA ENDPOINTS:
• Leagues: {self.base_url}/leagues
• Teams: {self.base_url}/teams
• Players: {self.base_url}/players
• Today’s Fixtures: {self.base_url}/fixtures/date/{{date}}
• Live Scores: {self.base_url}/livescores

💰 BETTING DATA ENDPOINTS:
• Bookmakers: {self.odds_url}/bookmakers
• Betting Markets: {self.odds_url}/markets
• Pre-match Odds: {self.odds_url}/pre-match
• Live Odds: {self.odds_url}/inplay
• AI Predictions: {self.base_url}/predictions

📊 ADVANCED ANALYTICS ENDPOINTS:
• xG Data: {self.base_url}/fixtures?include=xg
• Pressure Index: {self.base_url}/fixtures?include=pressureIndex
• Team Trends: {self.base_url}/teams?include=trends
• Head-to-Head: {self.base_url}/head2head
• Team Statistics: {self.base_url}/teams?include=statistics

🎯 BOT READINESS ASSESSMENT:
Score: {self.inventory.bot_readiness_score:.1f}/100

"""
        if self.inventory.bot_readiness_score >= 80:
            report += (
                "Status: 🚀 EXCELLENT - Ready for advanced AI betting bot\n"
                "Your subscription provides comprehensive data for building a professional-grade betting system.\n"
            )
        elif self.inventory.bot_readiness_score >= 60:
            report += (
                "Status: 👍 GOOD - Ready for intermediate betting bot\n"
                "You have solid data coverage for building an effective betting analysis system.\n"
            )
        elif self.inventory.bot_readiness_score >= 40:
            report += (
                "Status: ⚠️ BASIC - Limited betting bot capability\n"
                "You have basic data access suitable for simple betting analysis.\n"
            )
        else:
            report += (
                "Status: ❌ LIMITED - Insufficient for comprehensive betting bot\n"
                "Consider upgrading subscription to access more betting and analytics components.\n"
            )

        report += f"""
💼 SAMPLE API CALLS FOR BOT DEVELOPMENT:

1. GET TODAY’S FIXTURES WITH ODDS:
   GET {self.base_url}/fixtures/date/{{today}}?include=odds,participants,league&api_token={{token}}
2. GET LIVE ODDS FOR SPECIFIC MATCH:
   GET {self.odds_url}/inplay/fixtures/{{fixture_id}}?include=bookmaker,market&api_token={{token}}
3. GET xG DATA FOR PREDICTIONS:
   GET {self.base_url}/fixtures?include=xg,statistics&api_token={{token}}
4. GET TEAM H2H FOR ANALYSIS:
   GET {self.base_url}/head2head/{{team1_id}}/{{team2_id}}?api_token={{token}}

=== END COMPREHENSIVE ANALYSIS ===
"""
        return report.strip()


# Flask Application
app = Flask(__name__)
analyzer: Optional[ComprehensiveSubscriptionAnalyzer] = None

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>SportMonks Comprehensive Analyzer</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #f1f5f9; margin: 0; padding: 20px; min-height: 100vh; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #10b981; text-align: center; margin-bottom: 10px; font-size: 2.5rem; font-weight: 700; }
        .subtitle { text-align: center; color: #94a3b8; margin-bottom: 40px; font-size: 1.2rem; }
        .card { background: linear-gradient(145deg, #1e293b, #334155); border: 1px solid #475569; padding: 30px; margin: 25px 0; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }
        .btn { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; padding: 15px 30px; border: none; border-radius: 12px; cursor: pointer; font-size: 16px; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3); }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4); }
        .btn:disabled { background: #64748b; cursor: not-allowed; transform: none; box-shadow: none; }
        input { background: rgba(15, 23, 42, 0.8); color: #f1f5f9; border: 2px solid #475569; padding: 15px 20px; width: 450px; border-radius: 12px; font-size: 16px; transition: all 0.3s ease; }
        input:focus { border-color: #3b82f6; outline: none; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1); }
        .progress { width: 100%; height: 16px; background: rgba(51, 65, 85, 0.5); border-radius: 8px; overflow: hidden; margin: 20px 0; }
        .progress-bar { height: 100%; background: linear-gradient(90deg, #10b981, #059669); width: 0%; transition: width 0.6s ease; border-radius: 8px; }
        .status { margin-top: 20px; color: #cbd5e1; font-size: 14px; line-height: 1.6; }
        .phase { color: #3b82f6; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 25px 0; }
        .metric { background: rgba(15, 23, 42, 0.6); padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #334155; }
        .metric-value { font-size: 2rem; font-weight: 700; color: #10b981; margin-bottom: 5px; }
        .metric-label { font-size: 0.875rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
        .readiness-score { font-size: 3rem; font-weight: 800; text-align: center; margin: 20px 0; }
        .score-excellent { color: #10b981; }
        .score-good { color: #f59e0b; }
        .score-basic { color: #f97316; }
        .score-limited { color: #ef4444; }
        .report-section { margin: 30px 0; }
        .report-text { background: rgba(15, 23, 42, 0.8); padding: 25px; border-radius: 12px; font-family: 'Monaco', 'Menlo', monospace; font-size: 13px; white-space: pre-wrap; max-height: 500px; overflow-y: auto; border: 1px solid #334155; }
        .copy-btn { background: linear-gradient(135deg, #059669, #047857); margin-top: 15px; }
        .copy-btn:hover { box-shadow: 0 8px 25px rgba(5, 150, 105, 0.4); }
        .features-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 25px 0; }
        .feature-card { background: rgba(30, 41, 59, 0.6); padding: 20px; border-radius: 12px; border: 1px solid #475569; }
        .feature-title { color: #3b82f6; font-weight: 600; margin-bottom: 10px; }
        .feature-list { list-style: none; padding: 0; margin: 0; }
        .feature-list li { padding: 5px 0; color: #cbd5e1; }
        .feature-list li:before { content: "✅ "; margin-right: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 SportMonks Comprehensive Analyzer</h1>
        <p class="subtitle">Complete analysis of your subscription components for advanced AI betting bot development</p>

        <div class="card">
            <h3>🚀 Start Comprehensive Analysis</h3>
            <p style="color: #94a3b8; margin-bottom: 20px;">This will analyze all your enabled components including odds, xG analytics, pressure index, trends, and more.</p>
            <input id="apiToken" type="text" placeholder="Enter your SportMonks API Token...">
            <br><br>
            <button class="btn" id="analyzeBtn" onclick="startAnalysis()">🔍 Analyze All Components</button>
            
            <div class="progress">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="status">
                <div><span class="phase" id="phase">Ready</span> - <span id="currentTest">Enter your API token to begin comprehensive analysis</span></div>
                <div id="progressText" style="margin-top: 10px; font-size: 12px; color: #64748b;"></div>
            </div>
        </div>

        <div class="card" id="resultsCard" style="display: none;">
            <h3>📊 Comprehensive Results</h3>
            
            <div class="readiness-score" id="readinessScore"></div>
            
            <div class="metrics-grid" id="metricsGrid"></div>
            
            <div class="features-grid" id="featuresGrid"></div>
            
            <div id="componentsSummary"></div>
        </div>

        <div class="card" id="reportCard" style="display: none;">
            <h3>📋 Complete Comprehensive Report</h3>
            <p style="color: #94a3b8;">Copy this detailed report for your AI betting bot development</p>
            <button class="btn copy-btn" onclick="copyReport()">📋 Copy Complete Report</button>
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
        btn.innerHTML = '🔄 Analyzing...';

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_token: token })
            });

            if (response.ok) {
                startPolling();
            } else {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || 'Failed to start analysis');
            }
        } catch (error) {
            alert('Error: ' + error.message);
            resetUI();
        }
    }

    function startPolling() {
        if (pollTimer) clearInterval(pollTimer);
        
        pollTimer = setInterval(async () => {
            try {
                const response = await fetch('/api/progress');
                const data = await response.json();
                
                const denom = data.total_phases || 8;
                const pct = Math.min(100, Math.round(100 * (data.progress || 0) / denom));
                document.getElementById('progressBar').style.width = pct + '%';
                document.getElementById('phase').textContent = (data.phase || 'idle').toUpperCase();
                document.getElementById('currentTest').textContent = data.current_test || '';
                document.getElementById('progressText').textContent = `Phase ${data.progress}/${denom}`;
                
                if (data.phase === 'completed') {
                    clearInterval(pollTimer);
                    loadResults();
                } else if (data.phase === 'error') {
                    clearInterval(pollTimer);
                    alert('Analysis failed: ' + (data.current_test || 'Unknown error'));
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
        const inventory = data.inventory;
        
        const score = inventory.bot_readiness_score || 0;
        let scoreClass = 'score-limited';
        let scoreText = 'LIMITED';
        
        if (score >= 80) { scoreClass = 'score-excellent'; scoreText = 'EXCELLENT'; }
        else if (score >= 60) { scoreClass = 'score-good'; scoreText = 'GOOD'; }
        else if (score >= 40) { scoreClass = 'score-basic'; scoreText = 'BASIC'; }
        
        document.getElementById('readinessScore').innerHTML = `
            <div class="${scoreClass}">${score.toFixed(1)}/100</div>
            <div style="font-size: 1.2rem; margin-top: 10px; color: #94a3b8;">Bot Readiness: ${scoreText}</div>
        `;
        
        const metrics = `
            <div class="metric">
                <div class="metric-value">${inventory.total_components_enabled}</div>
                <div class="metric-label">Working Components</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.leagues_available}</div>
                <div class="metric-label">Leagues</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.fixtures_today}</div>
                <div class="metric-label">Today's Matches</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.bookmakers_count}</div>
                <div class="metric-label">Bookmakers</div>
            </div>
            <div class="metric">
                <div class="metric-value">${inventory.pre_match_odds_count}</div>
                <div class="metric-label">Pre-match Odds</div>
            </div>
            <div class="metric">
                <div class="metric-value">${(inventory.ai_ready_features || []).length}</div>
                <div class="metric-label">AI Features</div>
            </div>
        `;
        
        document.getElementById('metricsGrid').innerHTML = metrics;
        
        const features = `
            <div class="feature-card">
                <div class="feature-title">🎯 High-Value Components</div>
                <ul class="feature-list">
                    ${(inventory.high_value_components || []).map(comp => `<li>${comp}</li>`).join('')}
                </ul>
            </div>
            <div class="feature-card">
                <div class="feature-title">🤖 AI-Ready Features</div>
                <ul class="feature-list">
                    ${(inventory.ai_ready_features || []).map(feature => `<li>${feature}</li>`).join('')}
                </ul>
            </div>
            <div class="feature-card">
                <div class="feature-title">🎲 Recommended Strategies</div>
                <ul class="feature-list">
                    ${(inventory.recommended_strategies || []).map(strategy => `<li>${strategy}</li>`).join('')}
                </ul>
            </div>
        `;
        
        document.getElementById('featuresGrid').innerHTML = features;
        
        document.getElementById('componentsSummary').innerHTML = `
            <h4>📈 Subscription Summary</h4>
            <p><strong>Authentication:</strong> ${inventory.api_authenticated ? '✅ Success' : '❌ Failed'}</p>
            <p><strong>Subscription Tier:</strong> ${inventory.subscription_tier}</p>
            <p><strong>Advanced Analytics:</strong> ${inventory.xg_match_data_available ? '✅ xG Available' : '❌ xG Not Available'} | ${inventory.pressure_index_available ? '✅ Pressure Index' : '❌ No Pressure Index'}</p>
            <p><strong>Predictions:</strong> ${inventory.predictions_available ? '✅ AI Predictions Available' : '❌ No AI Predictions'}</p>
        `;
        
        const fullReportData = data.report || '';
        document.getElementById('fullReport').textContent = fullReportData;
        
        document.getElementById('resultsCard').style.display = 'block';
        document.getElementById('reportCard').style.display = 'block';
    }

    function copyReport() {
        const text = document.getElementById('fullReport').textContent || '';
        navigator.clipboard.writeText(text).then(() => {
            const btn = event.target;
            const originalText = btn.textContent;
            btn.textContent = '✅ Copied!';
            setTimeout(() => btn.textContent = originalText, 2000);
        }).catch(() => {
            alert('Failed to copy. Please select and copy manually.');
        });
    }

    function resetUI() {
        const btn = document.getElementById('analyzeBtn');
        btn.disabled = false;
        btn.innerHTML = '🔍 Analyze All Components';
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

    data = request.get_json(silent=True) or {}
    api_token = (data.get("api_token") or "").strip()

    if not api_token:
        return jsonify({"error": "API token required"}), 400

    if analyzer and analyzer.is_analyzing:
        return jsonify({"error": "Analysis already running"}), 400

    try:
        analyzer = ComprehensiveSubscriptionAnalyzer(api_token)
        thread = threading.Thread(target=analyzer.run_complete_analysis, daemon=True)
        thread.start()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/progress", methods=["GET"])
def get_progress():
    if not analyzer:
        return jsonify({"phase": "idle", "current_test": "No analysis running", "progress": 0, "total_phases": 8, "detailed_log": [], "errors": []})
    return jsonify(analyzer.analysis_progress)


@app.route("/api/results", methods=["GET"])
def get_results():
    if not analyzer:
        return jsonify({"error": "No analyzer"}), 400

    return jsonify({
        "inventory": {
            "subscription_tier": analyzer.inventory.subscription_tier,
            "api_authenticated": analyzer.inventory.api_authenticated,
            "total_components_enabled": analyzer.inventory.total_components_enabled,
            "bot_readiness_score": analyzer.inventory.bot_readiness_score,
            "leagues_available": analyzer.inventory.leagues_available,
            "teams_available": analyzer.inventory.teams_available,
            "fixtures_today": analyzer.inventory.fixtures_today,
            "live_matches": analyzer.inventory.live_matches,
            "bookmakers_count": analyzer.inventory.bookmakers_count,
            "betting_markets_count": analyzer.inventory.betting_markets_count,
            "pre_match_odds_count": analyzer.inventory.pre_match_odds_count,
            "live_odds_count": analyzer.inventory.live_odds_count,
            "predictions_available": analyzer.inventory.predictions_available,
            "xg_match_data_available": analyzer.inventory.xg_match_data_available,
            "pressure_index_available": analyzer.inventory.pressure_index_available,
            "trends_available": analyzer.inventory.trends_available,
            "high_value_components": analyzer.inventory.high_value_components,
            "ai_ready_features": analyzer.inventory.ai_ready_features,
            "recommended_strategies": analyzer.inventory.recommended_strategies
        },
        "report": analyzer.get_comprehensive_report()
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

# Gunicorn compatibility
application = app