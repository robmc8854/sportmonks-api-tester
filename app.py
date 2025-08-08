#!/usr/bin/env python3
"""
SportMonks v3 API Web Tester - Betting Bot Data Analysis
Comprehensive testing for betting prediction bot development
"""

import requests
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
from dataclasses import dataclass, asdict
from flask import Flask, render_template, jsonify, request, send_file
import io


@dataclass
class EndpointTest:
    category: str
    name: str
    url: str
    description: str
    expected_fields: List[str]
    requires_id: bool = False
    test_id: Optional[str] = None


@dataclass
class TestResult:
    endpoint: str
    status_code: int
    success: bool
    data_count: int
    response_time: float
    data_structure: Dict
    sample_data: Dict
    errors: List[str]
    warnings: List[str]


class SportMonksWebTester:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_base_url = "https://api.sportmonks.com/v3/odds"
        self.session = requests.Session()
        self.session.params = {'api_token': api_token}

        self.discovered_ids = {
            'fixture_id': None,
            'league_id': None,
            'season_id': None,
            'team_id': None,
            'player_id': None,
            'bookmaker_id': None,
            'market_id': None,
            'round_id': None,
            'stage_id': None
        }

        self.test_results: List[TestResult] = []
        self.testing_progress = {'current': 0, 'total': 0, 'status': 'idle'}
        self.is_testing = False

    def setup_test_endpoints(self) -> List[EndpointTest]:
        """Comprehensive endpoint testing for betting bot data discovery"""
        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        week_ahead = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        endpoints = [
            # === CORE BETTING DATA (CONFIRMED WORKING) ===
            EndpointTest(
                "Odds",
                "Pre-match Odds",
                f"{self.base_url}/odds/pre-match",
                "Current pre-match betting odds - CRITICAL for betting bot",
                ["fixture_id", "market_id", "bookmaker_id", "value", "handicap", "total"]
            ),

            EndpointTest(
                "Odds",
                "In-play Odds",
                f"{self.base_url}/odds/inplay",
                "Live betting odds during matches",
                ["fixture_id", "market_id", "bookmaker_id", "value"]
            ),

            EndpointTest(
                "Markets",
                "Betting Markets",
                f"{self.odds_base_url}/markets",
                "All available betting markets (1X2, Over/Under, etc.)",
                ["id", "name", "has_winning_calculations", "category"]
            ),

            EndpointTest(
                "Bookmakers",
                "All Bookmakers",
                f"{self.odds_base_url}/bookmakers",
                "Bookmaker list with IDs for odds mapping",
                ["id", "name", "legacy_id"]
            ),

            # === PREDICTION ENDPOINTS (TESTING ALTERNATIVES) ===
            EndpointTest(
                "Predictions",
                "Match Predictions",
                f"{self.base_url}/predictions",
                "General predictions endpoint",
                ["fixture_id", "predictions", "type_id"]
            ),

            EndpointTest(
                "Predictions",
                "Fixture Predictions",
                f"{self.base_url}/predictions/fixtures",
                "Predictions by fixture",
                ["fixture_id", "predictions"]
            ),

            EndpointTest(
                "Predictions",
                "Probabilities Alternative",
                f"{self.base_url}/predictions/probability",
                "Alternative probabilities endpoint",
                ["fixture_id", "probability"]
            ),

            EndpointTest(
                "Predictions",
                "Value Bets Alternative",
                f"{self.base_url}/predictions/value-bets",
                "Alternative value bets endpoint",
                ["fixture_id", "value_bet"]
            ),

            EndpointTest(
                "Predictions",
                "AI Predictions",
                f"{self.base_url}/ai/predictions",
                "AI-powered predictions endpoint",
                ["fixture_id", "ai_prediction"]
            ),

            # === FIXTURE DATA (ESSENTIAL FOR BOT) ===
            EndpointTest(
                "Fixtures",
                "Today's Fixtures",
                f"{self.base_url}/fixtures/date/{today}",
                "Today's matches with teams and timing",
                ["id", "name", "starting_at", "localteam_id", "visitorteam_id", "league_id"]
            ),

            EndpointTest(
                "Fixtures",
                "Tomorrow's Fixtures",
                f"{self.base_url}/fixtures/date/{tomorrow}",
                "Tomorrow's matches for advance betting",
                ["id", "name", "starting_at", "localteam_id", "visitorteam_id"]
            ),

            EndpointTest(
                "Fixtures",
                "Week Ahead Fixtures",
                f"{self.base_url}/fixtures/date/{week_ahead}",
                "Fixtures 7 days ahead",
                ["id", "name", "starting_at"]
            ),

            EndpointTest(
                "Fixtures",
                "Fixtures with Odds",
                f"{self.base_url}/fixtures/date/{today}?include=odds",
                "Today's fixtures WITH odds included",
                ["id", "odds", "starting_at"]
            ),

            EndpointTest(
                "Fixtures",
                "Fixtures with Predictions",
                f"{self.base_url}/fixtures/date/{today}?include=predictions",
                "Today's fixtures WITH predictions included",
                ["id", "predictions", "starting_at"]
            ),

            EndpointTest(
                "Fixtures",
                "Complete Fixture Data",
                f"{self.base_url}/fixtures/date/{today}?include=odds,predictions,participants,league,venue,statistics",
                "Complete fixture data with all betting info",
                ["id", "odds", "predictions", "participants", "league", "venue", "statistics"]
            ),

            # === LIVE DATA FOR IN-PLAY BETTING ===
            EndpointTest(
                "Live",
                "Live Matches",
                f"{self.base_url}/livescores/inplay",
                "Currently live matches with scores",
                ["id", "name", "time", "scores", "events"]
            ),

            EndpointTest(
                "Live",
                "Live Matches with Odds",
                f"{self.base_url}/livescores/inplay?include=odds",
                "Live matches WITH current odds",
                ["id", "odds", "scores", "time"]
            ),

            # === HISTORICAL DATA FOR MODEL TRAINING ===
            EndpointTest(
                "Historical",
                "Yesterday's Results",
                f"{self.base_url}/fixtures/date/{yesterday}",
                "Yesterday's results for model training",
                ["id", "name", "time", "scores"]
            ),

            EndpointTest(
                "Historical",
                "Results with Statistics",
                f"{self.base_url}/fixtures/date/{yesterday}?include=statistics,events",
                "Historical results with detailed stats",
                ["id", "statistics", "events", "scores"]
            ),

            # === TEAM & LEAGUE DATA ===
            EndpointTest(
                "Teams",
                "Teams Sample",
                f"{self.base_url}/teams?per_page=50",
                "Team data for ratings/stats",
                ["id", "name", "country_id", "founded", "venue_id"]
            ),

            EndpointTest(
                "Leagues",
                "Active Leagues",
                f"{self.base_url}/leagues?include=country",
                "League information with countries",
                ["id", "name", "country_id", "is_cup", "country"]
            ),

            # === STANDINGS FOR TEAM STRENGTH ===
            EndpointTest(
                "Standings",
                "League Standings",
                f"{self.base_url}/standings/live/leagues",
                "Current league tables for team strength analysis",
                ["league_id", "standings", "position", "points"]
            ),

            # === SPECIFIC BETTING MARKETS ===
            EndpointTest(
                "Markets",
                "Main Result Market",
                f"{self.odds_base_url}/markets/1",
                "1X2 Market details",
                ["id", "name", "category"]
            ),

            # === PLAYER DATA (for detailed analysis) ===
            EndpointTest(
                "Players",
                "Players Sample",
                f"{self.base_url}/players?per_page=20",
                "Player data for advanced models",
                ["id", "name", "team_id", "position_id"]
            ),

            # === HEAD-TO-HEAD DATA ===
            EndpointTest(
                "H2H",
                "Head to Head",
                f"{self.base_url}/fixtures/head-to-head/1/2",
                "Historical matchups between teams",
                ["fixture_id", "results", "statistics"]
            ),

            # === VENUE DATA ===
            EndpointTest(
                "Venues",
                "Venue Information",
                f"{self.base_url}/venues?per_page=20",
                "Stadium/venue data for home advantage analysis",
                ["id", "name", "capacity", "city_id"]
            ),
        ]

        return endpoints

    def discover_ids_from_response(self, response_data: Dict, endpoint_name: str):
        """Extract IDs from responses for follow-up tests"""
        if not isinstance(response_data, dict) or 'data' not in response_data:
            return

        data = response_data['data']
        if not data:
            return

        items = data if isinstance(data, list) else [data]

        for item in items[:3]:
            if not isinstance(item, dict):
                continue

            # Extract fixture IDs
            if ('starting_at' in item or 'localteam_id' in item) and 'id' in item:
                if not self.discovered_ids['fixture_id']:
                    self.discovered_ids['fixture_id'] = str(item['id'])

            # Extract bookmaker IDs
            if endpoint_name == "All Bookmakers" and 'id' in item:
                if not self.discovered_ids['bookmaker_id']:
                    self.discovered_ids['bookmaker_id'] = str(item['id'])

            # Extract market IDs
            if endpoint_name == "Betting Markets" and 'id' in item:
                if not self.discovered_ids['market_id']:
                    self.discovered_ids['market_id'] = str(item['id'])

            # Extract team IDs
            if 'localteam_id' in item and not self.discovered_ids['team_id']:
                self.discovered_ids['team_id'] = str(item['localteam_id'])

            # Extract league IDs
            if 'league_id' in item and not self.discovered_ids['league_id']:
                self.discovered_ids['league_id'] = str(item['league_id'])

    def analyze_betting_data_structure(self, data: Any) -> Dict:
        """Enhanced analysis specifically for betting data"""
        analysis = {
            "type": type(data).__name__,
            "betting_relevant": False,
            "key_fields": [],
            "sample_values": {},
            "data_quality": "unknown"
        }

        if isinstance(data, dict):
            analysis["type"] = "dict"
            analysis["key_count"] = len(data)

            # Look for betting-specific fields
            betting_fields = [
                'odds', 'predictions', 'bookmaker_id', 'market_id',
                'value', 'handicap', 'total', 'probability', 'fixture_id',
                'starting_at', 'participants', 'scores', 'events'
            ]

            found_betting_fields = [field for field in betting_fields if field in data]

            if found_betting_fields:
                analysis["betting_relevant"] = True
                analysis["key_fields"] = found_betting_fields

                # Sample important values
                for field in found_betting_fields[:5]:
                    value = data[field]
                    if isinstance(value, (str, int, float)):
                        analysis["sample_values"][field] = value
                    elif isinstance(value, dict) and value:
                        analysis["sample_values"][field] = f"dict with {len(value)} keys"
                    elif isinstance(value, list) and value:
                        analysis["sample_values"][field] = f"list with {len(value)} items"

            analysis["all_keys"] = list(data.keys())[:10]

        elif isinstance(data, list):
            analysis["type"] = "list"
            analysis["length"] = len(data)

            if data and isinstance(data[0], dict):
                first_item = data[0]
                betting_fields = [
                    'odds', 'predictions', 'bookmaker_id', 'market_id',
                    'fixture_id', 'starting_at', 'value'
                ]

                found_fields = [field for field in betting_fields if field in first_item]
                if found_fields:
                    analysis["betting_relevant"] = True
                    analysis["key_fields"] = found_fields
                    analysis["item_structure"] = list(first_item.keys())[:10]

        return analysis

    def test_single_endpoint(self, endpoint: EndpointTest) -> TestResult:
        """Test one endpoint with betting-focused analysis"""
        start_time = time.time()

        try:
            response = self.session.get(endpoint.url, timeout=15)
            response_time = time.time() - start_time

            if response.status_code != 200:
                return TestResult(
                    endpoint=endpoint.name,
                    status_code=response.status_code,
                    success=False,
                    data_count=0,
                    response_time=response_time,
                    data_structure={},
                    sample_data={},
                    errors=[f"HTTP {response.status_code}"],
                    warnings=[]
                )

            response_data = response.json()
            self.discover_ids_from_response(response_data, endpoint.name)

            data_count = 0
            sample_data = {}

            if 'data' in response_data:
                data = response_data['data']
                if isinstance(data, list):
                    data_count = len(data)
                    sample_data = data[0] if data else {}
                else:
                    data_count = 1
                    sample_data = data

            return TestResult(
                endpoint=endpoint.name,
                status_code=response.status_code,
                success=True,
                data_count=data_count,
                response_time=response_time,
                data_structure=self.analyze_betting_data_structure(response_data),
                sample_data=sample_data,
                errors=[],
                warnings=[]
            )

        except Exception as e:
            return TestResult(
                endpoint=endpoint.name,
                status_code=0,
                success=False,
                data_count=0,
                response_time=time.time() - start_time,
                data_structure={},
                sample_data={},
                errors=[str(e)[:100]],
                warnings=[]
            )

    def run_tests_async(self):
        """Run comprehensive tests for betting bot analysis"""
        self.is_testing = True
        self.test_results = []
        endpoints = self.setup_test_endpoints()

        self.testing_progress = {
            'current': 0,
            'total': len(endpoints),
            'status': 'running',
            'current_test': ''
        }

        try:
            for i, endpoint in enumerate(endpoints):
                if not self.is_testing:
                    break

                self.testing_progress['current'] = i + 1
                self.testing_progress['current_test'] = endpoint.name

                result = self.test_single_endpoint(endpoint)
                self.test_results.append(result)

                time.sleep(0.3)  # Rate limiting

            self.testing_progress['status'] = 'completed'

        except Exception as e:
            self.testing_progress['status'] = f'error: {str(e)}'
        finally:
            self.is_testing = False

    def analyze_betting_potential(self) -> Dict:
        """Analyze test results specifically for betting bot capabilities"""
        if not self.test_results:
            return {"error": "No test results available"}

        analysis = {
            "bot_readiness": "unknown",
            "available_data": {
                "odds_data": False,
                "prediction_data": False,
                "live_data": False,
                "historical_data": False,
                "team_stats": False
            },
            "betting_markets": [],
            "data_sources": {
                "bookmakers": 0,
                "markets": 0,
                "fixtures_today": 0,
                "fixtures_future": 0
            },
            "critical_gaps": [],
            "bot_recommendations": [],
            "data_quality_score": 0
        }

        successful_endpoints = [r for r in self.test_results if r.success]

        # Analyze each successful endpoint
        for result in successful_endpoints:
            endpoint_name = result.endpoint.lower()

            # Odds data analysis
            if "odds" in endpoint_name or "pre-match" in endpoint_name:
                analysis["available_data"]["odds_data"] = True
                analysis["data_sources"]["odds_records"] = result.data_count

            # Prediction data analysis
            elif "prediction" in endpoint_name or "probability" in endpoint_name:
                analysis["available_data"]["prediction_data"] = True
                analysis["data_sources"]["prediction_records"] = result.data_count

            # Live data analysis
            elif "live" in endpoint_name or "inplay" in endpoint_name:
                analysis["available_data"]["live_data"] = True
                analysis["data_sources"]["live_matches"] = result.data_count

            # Historical data
            elif "historical" in endpoint_name or "yesterday" in endpoint_name:
                analysis["available_data"]["historical_data"] = True
                analysis["data_sources"]["historical_records"] = result.data_count

            # Market analysis
            elif "market" in endpoint_name:
                analysis["data_sources"]["markets"] = result.data_count

            # Bookmaker analysis
            elif "bookmaker" in endpoint_name:
                analysis["data_sources"]["bookmakers"] = result.data_count

            # Fixture analysis
            elif "fixture" in endpoint_name:
                if "today" in endpoint_name:
                    analysis["data_sources"]["fixtures_today"] = result.data_count
                elif "tomorrow" in endpoint_name or "week" in endpoint_name:
                    analysis["data_sources"]["fixtures_future"] = result.data_count

        # Calculate bot readiness score
        score = 0
        if analysis["available_data"]["odds_data"]:
            score += 40  # Most critical
        if analysis["available_data"]["prediction_data"]:
            score += 30  # Very important
        if analysis["available_data"]["live_data"]:
            score += 15  # Good for in-play
        if analysis["data_sources"]["bookmakers"] > 0:
            score += 10  # Need for odds mapping
        if analysis["data_sources"]["fixtures_today"] > 0:
            score += 5   # Basic requirement

        analysis["data_quality_score"] = score

        # Bot readiness assessment
        if score >= 85:
            analysis["bot_readiness"] = "excellent"
        elif score >= 70:
            analysis["bot_readiness"] = "good"
        elif score >= 50:
            analysis["bot_readiness"] = "moderate"
        else:
            analysis["bot_readiness"] = "insufficient"

        # Generate recommendations
        recommendations = []

        if not analysis["available_data"]["odds_data"]:
            analysis["critical_gaps"].append("No odds data - CRITICAL for betting bot")
            recommendations.append("🚨 URGENT: Get access to odds endpoints - essential for betting bot")
        else:
            recommendations.append("✅ Odds data available - good foundation for betting bot")

        if not analysis["available_data"]["prediction_data"]:
            analysis["critical_gaps"].append("No prediction data - limits bot intelligence")
            recommendations.append("⚠️ Consider upgrading API plan for predictions/probabilities")
        else:
            recommendations.append("✅ Prediction data available - enables intelligent betting")

        if analysis["data_sources"]["fixtures_today"] == 0:
            analysis["critical_gaps"].append("No fixture data - can't identify matches")
            recommendations.append("🚨 URGENT: Need fixture data to identify betting opportunities")
        else:
            recommendations.append(f"✅ {analysis['data_sources']['fixtures_today']} fixtures available today")

        if analysis["data_sources"]["bookmakers"] == 0:
            recommendations.append("⚠️ No bookmaker data - will need hardcoded mappings")
        else:
            recommendations.append(f"✅ {analysis['data_sources']['bookmakers']} bookmakers available")

        if analysis["available_data"]["live_data"]:
            recommendations.append("✅ Live data available - enables in-play betting")
        else:
            recommendations.append("ℹ️ No live data - limited to pre-match betting")

        # Strategy recommendations
        if analysis["bot_readiness"] == "excellent":
            recommendations.append("🎯 STRATEGY: Build full-featured bot with pre-match + live betting")
            recommendations.append("🎯 STRATEGY: Implement odds comparison across bookmakers")
            recommendations.append("🎯 STRATEGY: Use predictions for value bet identification")
        elif analysis["bot_readiness"] == "good":
            recommendations.append("🎯 STRATEGY: Focus on pre-match betting with predictions")
            recommendations.append("🎯 STRATEGY: Start with simple markets (1X2, Over/Under)")
        elif analysis["bot_readiness"] == "moderate":
            recommendations.append("🎯 STRATEGY: Build basic odds monitoring bot first")
            recommendations.append("🎯 STRATEGY: Manual decisions, automated odds tracking")
        else:
            recommendations.append("🚨 STRATEGY: Upgrade API access before building bot")
            recommendations.append("🚨 STRATEGY: Consider alternative data sources")

        analysis["bot_recommendations"] = recommendations

        return analysis

    def generate_betting_bot_report(self) -> Dict:
        """Generate comprehensive report for betting bot development"""

        bot_analysis = self.analyze_betting_potential()

        report = {
            "executive_summary": {
                "bot_feasibility": bot_analysis["bot_readiness"],
                "data_quality_score": f"{bot_analysis['data_quality_score']}/100",
                "critical_requirements_met": len([x for x in bot_analysis["available_data"].values() if x]),
                "recommended_next_steps": bot_analysis["bot_recommendations"][:3]
            },

            "data_availability": {
                "odds_endpoints": [r.endpoint for r in self.test_results if r.success and "odds" in r.endpoint.lower()],
                "prediction_endpoints": [r.endpoint for r in self.test_results if r.success and "prediction" in r.endpoint.lower()],
                "fixture_endpoints": [r.endpoint for r in self.test_results if r.success and "fixture" in r.endpoint.lower()],
                "live_endpoints": [r.endpoint for r in self.test_results if r.success and "live" in r.endpoint.lower()]
            },

            "betting_infrastructure": {
                "available_bookmakers": bot_analysis["data_sources"].get("bookmakers", 0),
                "available_markets": bot_analysis["data_sources"].get("markets", 0),
                "todays_fixtures": bot_analysis["data_sources"].get("fixtures_today", 0),
                "future_fixtures": bot_analysis["data_sources"].get("fixtures_future", 0)
            },

            "failed_endpoints": [
                {
                    "endpoint": r.endpoint,
                    "error": r.errors[0] if r.errors else "Unknown error",
                    "status_code": r.status_code,
                    "impact_on_bot": "High" if any(word in r.endpoint.lower() for word in ["prediction", "odds", "fixture"]) else "Medium"
                }
                for r in self.test_results if not r.success
            ],

            "bot_development_roadmap": self._generate_development_roadmap(bot_analysis),

            "sample_data_structures": {
                result.endpoint: result.sample_data if len(str(result.sample_data)) < 1000 else {"note": "Data too large for display"}
                for result in self.test_results if result.success
            }
        }

        return report

    def _generate_development_roadmap(self, bot_analysis: Dict) -> List[Dict]:
        """Generate step-by-step bot development roadmap"""

        roadmap = []

        if bot_analysis["bot_readiness"] in ["excellent", "good"]:
            roadmap = [
                {
                    "phase": 1,
                    "title": "Data Pipeline Setup",
                    "tasks": [
                        "Set up automated odds fetching from pre-match endpoint",
                        "Create database schema for fixtures, odds, and predictions",
                        "Implement data validation and cleaning"
                    ],
                    "estimated_time": "1-2 weeks"
                },
                {
                    "phase": 2,
                    "title": "Basic Betting Logic",
                    "tasks": [
                        "Implement simple value betting algorithm",
                        "Create bankroll management system",
                        "Add basic risk controls"
                    ],
                    "estimated_time": "2-3 weeks"
                },
                {
                    "phase": 3,
                    "title": "Strategy Enhancement",
                    "tasks": [
                        "Integrate prediction data if available",
                        "Add multiple market support",
                        "Implement odds comparison logic"
                    ],
                    "estimated_time": "2-4 weeks"
                },
                {
                    "phase": 4,
                    "title": "Live Trading",
                    "tasks": [
                        "Add live odds monitoring",
                        "Implement automated bet placement",
                        "Create monitoring dashboard"
                    ],
                    "estimated_time": "3-4 weeks"
                }
            ]
        else:
            roadmap = [
                {
                    "phase": 1,
                    "title": "API Access Upgrade",
                    "tasks": [
                        "Upgrade SportMonks plan for prediction access",
                        "Test all premium endpoints",
                        "Document available data sources"
                    ],
                    "estimated_time": "1 week"
                },
                {
                    "phase": 2,
                    "title": "Data Foundation",
                    "tasks": [
                        "Retry comprehensive endpoint testing",
                        "Build basic data collection system",
                        "Validate data quality"
                    ],
                    "estimated_time": "1-2 weeks"
                }
            ]

        return roadmap

    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        if not self.test_results:
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'success_rate': 0,
                'avg_response_time': 0,
                'total_data_items': 0
            }

        successful = sum(1 for r in self.test_results if r.success)
        total = len(self.test_results)

        return {
            'total': total,
            'successful': successful,
            'failed': total - successful,
            'success_rate': round(successful / total * 100, 1) if total > 0 else 0,
            'avg_response_time': round(sum(r.response_time for r in self.test_results if r.success) / max(successful, 1), 2),
            'total_data_items': sum(r.data_count for r in self.test_results)
        }


# Flask Application

app = Flask(__name__)
tester = None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/start-test', methods=['POST'])
def start_test():
    global tester

    data = request.get_json()
    api_token = data.get('api_token', '').strip()

    if not api_token:
        return jsonify({'error': 'API token required'}), 400

    if tester and tester.is_testing:
        return jsonify({'error': 'Test already running'}), 400

    try:
        tester = SportMonksWebTester(api_token)

        thread = threading.Thread(target=tester.run_tests_async)
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'message': 'Comprehensive betting analysis started'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/test-progress')
def get_progress():
    if not tester:
        return jsonify({'progress': {'current': 0, 'total': 0, 'status': 'idle'}})

    return jsonify({
        'progress': tester.testing_progress,
        'discovered_ids': tester.discovered_ids
    })


@app.route('/api/test-results')
def get_results():
    if not tester:
        return jsonify({'results': [], 'summary': {}})

    results_dict = []
    for result in tester.test_results:
        result_dict = asdict(result)
        if len(str(result_dict['sample_data'])) > 500:
            result_dict['sample_data'] = {'truncated': 'Data too large for mobile display'}
        results_dict.append(result_dict)

    return jsonify({
        'results': results_dict,
        'summary': tester.get_summary_stats(),
        'discovered_ids': tester.discovered_ids
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)