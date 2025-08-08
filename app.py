#!/usr/bin/env python3
"""
COMPLETE PROFESSIONAL SPORTMONKS BETTING BOT ANALYZER
Tests ALL endpoints, analyzes ALL data, generates COMPLETE reports
"""

import requests
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import os
from dataclasses import dataclass, asdict
from flask import Flask, render_template, jsonify, request, send_file
import io


@dataclass
class EndpointResult:
    name: str
    category: str
    url: str
    status_code: int
    success: bool
    data_count: int
    response_time: float
    betting_value: str
    data_quality: int
    sample_data: Dict
    analysis: Dict
    errors: List[str]
    recommendations: List[str]


class CompleteBettingAnalyzer:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_base_url = "https://api.sportmonks.com/v3/odds"

        self.session = requests.Session()
        self.session.params = {'api_token': api_token}
        self.session.headers.update({'Accept': 'application/json'})

        self.test_results: List[EndpointResult] = []
        self.discovered_data = {
            'fixture_ids': [],
            'team_ids': [],
            'league_ids': [],
            'bookmaker_ids': [],
            'market_ids': []
        }
        self.testing_progress = {
            'current': 0,
            'total': 0,
            'status': 'idle',
            'current_test': '',
            'phase': 'preparing'
        }
        self.is_testing = False
        self.complete_analysis = {}

    def get_all_endpoints(self) -> List[Dict]:
        """Get comprehensive list of ALL SportMonks endpoints"""
        today = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        return [
            # CRITICAL BETTING DATA
            {"name": "Live Pre-match Odds", "url": f"{self.base_url}/odds/pre-match", "category": "Odds", "priority": "critical"},
            {"name": "Live In-play Odds", "url": f"{self.base_url}/odds/inplay", "category": "Odds", "priority": "critical"},
            {"name": "All Betting Markets", "url": f"{self.odds_base_url}/markets", "category": "Markets", "priority": "critical"},
            {"name": "All Bookmakers", "url": f"{self.odds_base_url}/bookmakers", "category": "Bookmakers", "priority": "critical"},

            # PREDICTIONS (ALL VARIANTS)
            {"name": "Match Probabilities", "url": f"{self.base_url}/predictions/probabilities", "category": "Predictions", "priority": "critical"},
            {"name": "Value Betting Opportunities", "url": f"{self.base_url}/predictions/valuebets", "category": "Predictions", "priority": "critical"},
            {"name": "AI Predictions", "url": f"{self.base_url}/predictions", "category": "Predictions", "priority": "high"},
            {"name": "Fixture Predictions", "url": f"{self.base_url}/predictions/fixtures", "category": "Predictions", "priority": "high"},
            {"name": "Predictions Alternative 1", "url": f"{self.base_url}/ai/predictions", "category": "Predictions", "priority": "medium"},
            {"name": "Predictions Alternative 2", "url": f"{self.base_url}/predictions/probability", "category": "Predictions", "priority": "medium"},
            {"name": "Value Bets Alternative", "url": f"{self.base_url}/predictions/value-bets", "category": "Predictions", "priority": "medium"},

            # COMPREHENSIVE FIXTURE DATA
            {"name": "Today's Complete Fixtures", "url": f"{self.base_url}/fixtures/date/{today}?include=odds,predictions,probabilities,participants,league,venue,statistics,events", "category": "Fixtures", "priority": "critical"},
            {"name": "Tomorrow's Complete Fixtures", "url": f"{self.base_url}/fixtures/date/{tomorrow}?include=odds,predictions,participants,league", "category": "Fixtures", "priority": "high"},
            {"name": "Today's Basic Fixtures", "url": f"{self.base_url}/fixtures/date/{today}", "category": "Fixtures", "priority": "high"},
            {"name": "Fixtures with Odds Only", "url": f"{self.base_url}/fixtures/date/{today}?include=odds", "category": "Fixtures", "priority": "high"},
            {"name": "Fixtures with Predictions Only", "url": f"{self.base_url}/fixtures/date/{today}?include=predictions", "category": "Fixtures", "priority": "high"},
            {"name": "Yesterday's Results", "url": f"{self.base_url}/fixtures/date/{yesterday}?include=statistics,events", "category": "Fixtures", "priority": "medium"},

            # LIVE DATA
            {"name": "Live Matches Complete", "url": f"{self.base_url}/livescores/inplay?include=odds,events,statistics", "category": "Live", "priority": "critical"},
            {"name": "Live Matches Basic", "url": f"{self.base_url}/livescores/inplay", "category": "Live", "priority": "high"},
            {"name": "All Live Scores", "url": f"{self.base_url}/livescores", "category": "Live", "priority": "high"},

            # TEAM & LEAGUE DATA
            {"name": "All Teams Complete", "url": f"{self.base_url}/teams?include=country,venue,league&per_page=100", "category": "Teams", "priority": "high"},
            {"name": "All Teams Basic", "url": f"{self.base_url}/teams?per_page=100", "category": "Teams", "priority": "high"},
            {"name": "All Leagues Complete", "url": f"{self.base_url}/leagues?include=country,seasons", "category": "Leagues", "priority": "high"},
            {"name": "All Leagues Basic", "url": f"{self.base_url}/leagues", "category": "Leagues", "priority": "high"},
            {"name": "Live Standings", "url": f"{self.base_url}/standings/live", "category": "Standings", "priority": "high"},

            # HISTORICAL DATA
            {"name": "All Seasons", "url": f"{self.base_url}/seasons?include=league", "category": "Seasons", "priority": "medium"},
            {"name": "Historical Odds", "url": f"{self.base_url}/odds/historical", "category": "Odds", "priority": "high"},
            {"name": "Odds Movement", "url": f"{self.base_url}/odds/movement", "category": "Odds", "priority": "medium"},
            {"name": "Closing Odds", "url": f"{self.base_url}/odds/closing", "category": "Odds", "priority": "high"},

            # PLAYER DATA
            {"name": "All Players Sample", "url": f"{self.base_url}/players?include=team,position&per_page=100", "category": "Players", "priority": "medium"},
            {"name": "All Venues", "url": f"{self.base_url}/venues?include=city&per_page=100", "category": "Venues", "priority": "medium"},

            # REFERENCE DATA
            {"name": "All Countries", "url": f"{self.base_url}/countries", "category": "Geography", "priority": "low"},
            {"name": "All Continents", "url": f"{self.base_url}/continents", "category": "Geography", "priority": "low"},

            # ADDITIONAL BETTING DATA
            {"name": "Market Categories", "url": f"{self.odds_base_url}/markets/categories", "category": "Markets", "priority": "high"},
            {"name": "Bookmaker Mapping", "url": f"{self.odds_base_url}/bookmakers/mapping", "category": "Bookmakers", "priority": "medium"},
            {"name": "Betting Trends", "url": f"{self.base_url}/betting/trends", "category": "Betting", "priority": "medium"},

            # ALTERNATIVE ENDPOINTS
            {"name": "Fixtures Alternative", "url": f"{self.base_url}/fixtures", "category": "Fixtures", "priority": "medium"},
            {"name": "Livescores Alternative", "url": f"{self.base_url}/scores/live", "category": "Live", "priority": "medium"},
            {"name": "Odds Alternative", "url": f"{self.odds_base_url}/live", "category": "Odds", "priority": "medium"},
        ]

    def analyze_endpoint_data(self, response_data: Dict, endpoint: Dict) -> Tuple[str, int, Dict, List[str]]:
        """Comprehensive analysis of endpoint data"""
        betting_value = "none"
        quality_score = 0
        analysis = {}
        recommendations = []

        if not isinstance(response_data, dict) or 'data' not in response_data:
            return betting_value, quality_score, analysis, ["❌ Invalid response structure"]

        data = response_data['data']
        if not data:
            return betting_value, quality_score, analysis, ["⚠️ Empty dataset"]

        sample = data[0] if isinstance(data, list) and data else data
        if not isinstance(sample, dict):
            return betting_value, quality_score, analysis, ["❌ Unexpected data format"]

        self.update_discovered_data(data, endpoint)

        # Analyze betting relevance
        critical_fields = ['odds', 'predictions', 'probabilities', 'value', 'bookmaker_id', 'market_id']
        high_value_fields = ['fixture_id', 'starting_at', 'scores', 'statistics', 'participants']
        medium_value_fields = ['league_id', 'team_id', 'events', 'lineup', 'form']

        found_critical = [f for f in critical_fields if f in sample]
        found_high = [f for f in high_value_fields if f in sample]
        found_medium = [f for f in medium_value_fields if f in sample]

        # Calculate quality score
        quality_score = (len(found_critical) * 25) + (len(found_high) * 15) + (len(found_medium) * 8)
        if isinstance(data, list):
            quality_score += min(20, len(data))
        quality_score = min(100, quality_score)

        # Determine betting value
        if len(found_critical) >= 2:
            betting_value = "critical"
        elif len(found_critical) >= 1:
            betting_value = "high"
        elif len(found_high) >= 2:
            betting_value = "medium"
        elif len(found_high) >= 1:
            betting_value = "low"

        analysis = {
            'total_fields': len(sample),
            'critical_betting_fields': found_critical,
            'high_value_fields': found_high,
            'medium_value_fields': found_medium,
            'data_completeness': len(sample) / max(len(critical_fields + high_value_fields), 1) * 100,
            'nested_complexity': sum(1 for v in sample.values() if isinstance(v, (dict, list)))
        }

        # Generate recommendations
        if found_critical:
            if 'odds' in found_critical:
                recommendations.append("🎯 CRITICAL: Odds data available - core betting functionality possible")
            if 'predictions' in found_critical:
                recommendations.append("🤖 CRITICAL: Prediction data available - AI betting possible")

        if endpoint['category'] == 'Odds' and not found_critical:
            recommendations.append("❌ PROBLEM: Odds endpoint with no odds data")

        if quality_score > 70:
            recommendations.append("🚀 EXCELLENT: High-quality data - implement advanced features")
        elif quality_score > 40:
            recommendations.append("✅ GOOD: Solid data quality - suitable for bot development")
        else:
            recommendations.append("⚠️ LIMITED: Basic data only - simple strategies possible")

        return betting_value, quality_score, analysis, recommendations

    def update_discovered_data(self, data: Any, endpoint: Dict):
        """Update discovered IDs"""
        items = data if isinstance(data, list) else [data]

        for item in items[:5]:
            if not isinstance(item, dict):
                continue

            if 'id' in item:
                if endpoint['category'] in ['Fixtures', 'Live'] and item['id'] not in self.discovered_data['fixture_ids']:
                    self.discovered_data['fixture_ids'].append(item['id'])
                elif endpoint['category'] == 'Teams' and item['id'] not in self.discovered_data['team_ids']:
                    self.discovered_data['team_ids'].append(item['id'])
                elif endpoint['category'] == 'Bookmakers' and item['id'] not in self.discovered_data['bookmaker_ids']:
                    self.discovered_data['bookmaker_ids'].append(item['id'])

    def test_single_endpoint(self, endpoint: Dict) -> EndpointResult:
        """Test single endpoint"""
        start_time = time.time()

        try:
            response = self.session.get(endpoint['url'], timeout=20)
            response_time = time.time() - start_time

            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                if response.status_code == 403:
                    error_msg += " - Premium API access required"
                elif response.status_code == 404:
                    error_msg += " - Endpoint not found"
                elif response.status_code == 429:
                    error_msg += " - Rate limit exceeded"

                return EndpointResult(
                    name=endpoint['name'], category=endpoint['category'], url=endpoint['url'],
                    status_code=response.status_code, success=False, data_count=0, response_time=response_time,
                    betting_value="none", data_quality=0, sample_data={}, analysis={},
                    errors=[error_msg], recommendations=[]
                )

            response_data = response.json()
            betting_value, quality_score, analysis, recommendations = self.analyze_endpoint_data(response_data, endpoint)

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

            return EndpointResult(
                name=endpoint['name'], category=endpoint['category'], url=endpoint['url'],
                status_code=response.status_code, success=True, data_count=data_count, response_time=response_time,
                betting_value=betting_value, data_quality=quality_score, sample_data=sample_data, analysis=analysis,
                errors=[], recommendations=recommendations
            )

        except Exception as e:
            return EndpointResult(
                name=endpoint['name'], category=endpoint['category'], url=endpoint['url'],
                status_code=0, success=False, data_count=0, response_time=time.time() - start_time,
                betting_value="none", data_quality=0, sample_data={}, analysis={},
                errors=[f"Error: {str(e)[:100]}"], recommendations=[]
            )

    def run_complete_analysis(self):
        """Run comprehensive analysis"""
        self.is_testing = True
        self.test_results = []
        endpoints = self.get_all_endpoints()

        self.testing_progress = {
            'current': 0, 'total': len(endpoints), 'status': 'running',
            'current_test': 'Starting comprehensive analysis...', 'phase': 'testing'
        }

        try:
            for i, endpoint in enumerate(endpoints):
                if not self.is_testing:
                    break

                self.testing_progress.update({
                    'current': i + 1, 'current_test': f"Testing {endpoint['name']}", 'phase': 'testing'
                })

                result = self.test_single_endpoint(endpoint)
                self.test_results.append(result)
                time.sleep(0.2)

            self.testing_progress.update({
                'phase': 'analyzing', 'current_test': 'Generating betting bot analysis...'
            })

            self.generate_complete_analysis()
            self.testing_progress['status'] = 'completed'

        except Exception as e:
            self.testing_progress['status'] = f'error: {str(e)}'
        finally:
            self.is_testing = False

    def generate_complete_analysis(self):
        """Generate comprehensive analysis"""
        successful_tests = [r for r in self.test_results if r.success]
        failed_tests = [r for r in self.test_results if not r.success]

        critical_sources = [r for r in successful_tests if r.betting_value == "critical"]
        high_value_sources = [r for r in successful_tests if r.betting_value == "high"]
        medium_value_sources = [r for r in successful_tests if r.betting_value == "medium"]

        total_quality = sum(r.data_quality for r in successful_tests)
        max_possible = len(self.test_results) * 100
        overall_score = (total_quality / max_possible * 100) if max_possible > 0 else 0

        if overall_score >= 65 and len(critical_sources) >= 4:
            readiness = "EXCELLENT - Full betting bot ready"
            readiness_level = "excellent"
        elif overall_score >= 45 and len(critical_sources) >= 2:
            readiness = "GOOD - Effective betting bot possible"
            readiness_level = "good"
        elif overall_score >= 25 and len(critical_sources) >= 1:
            readiness = "MODERATE - Basic betting tool possible"
            readiness_level = "moderate"
        else:
            readiness = "INSUFFICIENT - API upgrades required"
            readiness_level = "insufficient"

        capabilities = {
            "odds_access": any("odds" in r.name.lower() and r.success for r in self.test_results),
            "predictions_access": any("prediction" in r.name.lower() and r.success for r in self.test_results),
            "live_data": any("live" in r.name.lower() and r.success for r in self.test_results),
            "fixture_data": any("fixture" in r.name.lower() and r.success for r in self.test_results),
            "bookmaker_data": any("bookmaker" in r.name.lower() and r.success for r in self.test_results),
            "market_data": any("market" in r.name.lower() and r.success for r in self.test_results)
        }

        recommendations = self.generate_recommendations(readiness_level, capabilities)
        development_strategy = self.create_development_strategy(readiness_level, capabilities)
        implementation_roadmap = self.create_roadmap(readiness_level)

        self.complete_analysis = {
            "executive_summary": {
                "overall_readiness": readiness,
                "readiness_level": readiness_level,
                "feasibility_score": round(overall_score, 1),
                "total_endpoints": len(self.test_results),
                "successful_endpoints": len(successful_tests),
                "critical_sources": len(critical_sources),
                "high_value_sources": len(high_value_sources),
                "total_data_items": sum(r.data_count for r in successful_tests)
            },
            "capabilities": capabilities,
            "data_sources": {
                "critical": [{"name": r.name, "category": r.category, "data_count": r.data_count, "quality": r.data_quality} for r in critical_sources],
                "high_value": [{"name": r.name, "category": r.category, "data_count": r.data_count} for r in high_value_sources],
                "failed_critical": [{"name": r.name, "error": r.errors[0] if r.errors else "Unknown"} for r in failed_tests if r.category in ["Odds", "Predictions"]]
            },
            "recommendations": recommendations,
            "development_strategy": development_strategy,
            "implementation_roadmap": implementation_roadmap,
            "discovered_data": {
                "fixtures": len(self.discovered_data['fixture_ids']),
                "teams": len(self.discovered_data['team_ids']),
                "bookmakers": len(self.discovered_data['bookmaker_ids']),
                "markets": len(self.discovered_data['market_ids'])
            },
            "detailed_results": [asdict(r) for r in self.test_results]
        }

    def generate_recommendations(self, readiness_level: str, capabilities: Dict) -> List[str]:
        """Generate strategic recommendations"""
        recommendations = []

        if readiness_level == "excellent":
            recommendations.extend([
                "🚀 BUILD COMPREHENSIVE BOT: Full-featured betting bot possible",
                "🎯 MULTI-STRATEGY APPROACH: Value betting, arbitrage, live betting",
                "🤖 AI PREDICTIONS: Use prediction data for intelligent decisions",
                "💰 MULTI-BOOKMAKER: Compare odds across bookmakers",
                "⚡ REAL-TIME TRADING: Live betting capabilities",
                "📊 ADVANCED ANALYTICS: Performance tracking and optimization"
            ])
        elif readiness_level == "good":
            recommendations.extend([
                "✅ BUILD SOLID BOT: Effective betting bot possible",
                "🎯 FOCUS ON CORE MARKETS: 1X2, Over/Under, Handicap",
                "📈 VALUE BETTING: Use available prediction data",
                "🔧 SOLID INFRASTRUCTURE: Data collection and analysis"
            ])
        elif readiness_level == "moderate":
            recommendations.extend([
                "⚠️ BETTING ASSISTANT: Semi-automated decision support",
                "📊 ODDS MONITORING: Track and alert on odds changes",
                "💡 UPGRADE PLAN: Better API access for automation"
            ])
        else:
            recommendations.extend([
                "🚨 UPGRADE REQUIRED: Current access insufficient",
                "📈 GET PREMIUM PLAN: Need odds and prediction access",
                "🔍 ALTERNATIVE SOURCES: Consider other data providers"
            ])

        if not capabilities["odds_access"]:
            recommendations.append("🚨 CRITICAL: No odds access - essential for betting")
        if not capabilities["predictions_access"]:
            recommendations.append("⚠️ UPGRADE: No predictions - limits intelligence")
        if capabilities["live_data"]:
            recommendations.append("⚡ OPPORTUNITY: Live data available for in-play betting")

        return recommendations

    def create_development_strategy(self, readiness_level: str, capabilities: Dict) -> Dict:
        """Create development strategy"""
        if readiness_level in ["excellent", "good"]:
            return {
                "approach": "Full Automated Betting Bot",
                "timeline": "8-12 weeks",
                "tech_stack": ["Python", "PostgreSQL", "Redis", "React", "Docker"],
                "primary_markets": ["1X2", "Over/Under", "Handicap", "BTTS"],
                "strategies": ["Value Betting", "Odds Comparison", "Live Betting"],
                "estimated_cost": "$3,000-8,000",
                "expected_roi": "Positive within 3-6 months"
            }
        elif readiness_level == "moderate":
            return {
                "approach": "Semi-Automated Assistant",
                "timeline": "4-6 weeks",
                "tech_stack": ["Python", "SQLite", "Web Dashboard"],
                "primary_markets": ["1X2", "Over/Under"],
                "strategies": ["Odds Monitoring", "Manual Decision Support"],
                "estimated_cost": "$1,000-2,500",
                "expected_roi": "Break-even within 2-4 months"
            }
        else:
            return {
                "approach": "API Upgrade Required",
                "timeline": "1-2 weeks to upgrade",
                "estimated_cost": "$200-500/month for API",
                "next_steps": ["Upgrade SportMonks plan", "Re-run analysis"]
            }

    def create_roadmap(self, readiness_level: str) -> List[Dict]:
        """Create implementation roadmap"""
        if readiness_level == "excellent":
            return [
                {"phase": 1, "title": "Data Pipeline", "weeks": "1-3", "tasks": ["Database setup", "Data collection", "Real-time monitoring"]},
                {"phase": 2, "title": "Core Engine", "weeks": "4-6", "tasks": ["Bankroll management", "Risk controls", "Basic strategies"]},
                {"phase": 3, "title": "Advanced Features", "weeks": "7-9", "tasks": ["AI predictions", "Live betting", "Multi-bookmaker"]},
                {"phase": 4, "title": "Production", "weeks": "10-12", "tasks": ["Deployment", "Monitoring", "Optimization"]}
            ]
        elif readiness_level == "good":
            return [
                {"phase": 1, "title": "Foundation", "weeks": "1-2", "tasks": ["Basic data collection", "Simple analysis"]},
                {"phase": 2, "title": "Core Features", "weeks": "3-5", "tasks": ["Betting logic", "Risk management"]},
                {"phase": 3, "title": "Enhancement", "weeks": "6-8", "tasks": ["Advanced strategies", "UI/Dashboard"]}
            ]
        else:
            return [{"phase": 1, "title": "API Upgrade", "weeks": "1", "tasks": ["Upgrade plan", "Re-test endpoints"]}]

    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        if not self.test_results:
            return {'total': 0, 'successful': 0, 'failed': 0, 'success_rate': 0}

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
analyzer: Optional[CompleteBettingAnalyzer] = None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/start-analysis', methods=['POST'])
def start_analysis():
    global analyzer

    data = request.get_json()
    api_token = data.get('api_token', '').strip()

    if not api_token:
        return jsonify({'error': 'API token required'}), 400

    if analyzer and analyzer.is_testing:
        return jsonify({'error': 'Analysis already running'}), 400

    try:
        analyzer = CompleteBettingAnalyzer(api_token)

        thread = threading.Thread(target=analyzer.run_complete_analysis)
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'message': 'Complete analysis started'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/progress')
def get_progress():
    if not analyzer:
        return jsonify({'progress': {'current': 0, 'total': 0, 'status': 'idle'}})
    return jsonify({'progress': analyzer.testing_progress})


@app.route('/api/results')
def get_results():
    if not analyzer:
        return jsonify({'error': 'No analyzer available'}), 400
    if not analyzer.complete_analysis:
        return jsonify({'error': 'Analysis not complete'}), 400

    return jsonify({
        'summary': analyzer.get_summary_stats(),
        'analysis': analyzer.complete_analysis
    })


@app.route('/api/download-report')
def download_report():
    if not analyzer or not analyzer.complete_analysis:
        return jsonify({'error': 'No analysis available'}), 400

    report_data = {
        'timestamp': datetime.now().isoformat(),
        'summary': analyzer.get_summary_stats(),
        'complete_analysis': analyzer.complete_analysis,
        'raw_results': [asdict(r) for r in analyzer.test_results]
    }

    report_json = json.dumps(report_data, indent=2, default=str)
    buffer = io.BytesIO(report_json.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer, mimetype='application/json', as_attachment=True,
        download_name=f'betting_bot_complete_analysis_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    )


@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)