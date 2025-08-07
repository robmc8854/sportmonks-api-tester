#!/usr/bin/env python3
“””
SportMonks v3 API Web Tester - Railway Deployment
Web interface for testing SportMonks API from iPhone/browser
“””

import requests
import json
import time
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
from dataclasses import dataclass, asdict
from collections import defaultdict
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename
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
def **init**(self, api_token: str):
self.api_token = api_token
self.base_url = “https://api.sportmonks.com/v3/football”
self.odds_base_url = “https://api.sportmonks.com/v3/odds”
self.session = requests.Session()
self.session.params = {‘api_token’: api_token}

```
    # Store discovered IDs and test progress
    self.discovered_ids = {
        'fixture_id': None, 'league_id': None, 'season_id': None,
        'team_id': None, 'player_id': None, 'bookmaker_id': None,
        'market_id': None, 'round_id': None, 'stage_id': None
    }
    
    self.test_results: List[TestResult] = []
    self.rate_limit_info = {}
    self.testing_progress = {'current': 0, 'total': 0, 'status': 'idle'}
    self.is_testing = False
    
def setup_test_endpoints(self) -> List[EndpointTest]:
    """Define all endpoints to test - mobile-optimized selection"""
    endpoints = [
        # Core betting endpoints first
        EndpointTest("Predictions", "All Probabilities", 
                    f"{self.base_url}/predictions/probabilities",
                    "Match probabilities for upcoming games", 
                    ["fixture_id", "predictions", "type_id"]),
        
        EndpointTest("Predictions", "All Value Bets", 
                    f"{self.base_url}/predictions/valuebets",
                    "AI-detected value betting opportunities", 
                    ["fixture_id", "predictions", "type_id"]),
        
        EndpointTest("Odds", "All Pre-match Odds", 
                    f"{self.base_url}/odds/pre-match",
                    "Current pre-match betting odds", 
                    ["fixture_id", "market_id", "bookmaker_id", "value"]),
        
        EndpointTest("Odds", "All In-play Odds", 
                    f"{self.base_url}/odds/inplay",
                    "Live betting odds for ongoing matches", 
                    ["fixture_id", "market_id", "bookmaker_id", "value"]),
        
        EndpointTest("Bookmakers", "All Bookmakers", 
                    f"{self.odds_base_url}/bookmakers",
                    "Available bookmakers and their IDs", 
                    ["id", "name", "legacy_id"]),
        
        EndpointTest("Markets", "All Markets", 
                    f"{self.odds_base_url}/markets",
                    "Available betting markets", 
                    ["id", "name", "has_winning_calculations"]),
        
        EndpointTest("Fixtures", "Today's Fixtures", 
                    f"{self.base_url}/fixtures/date/{datetime.now().strftime('%Y-%m-%d')}",
                    "Today's football matches", 
                    ["id", "name", "starting_at", "localteam_id", "visitorteam_id"]),
        
        EndpointTest("Fixtures", "Next 3 Days", 
                    f"{self.base_url}/fixtures/between/{datetime.now().strftime('%Y-%m-%d')}/{(datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')}",
                    "Upcoming matches in next 3 days", 
                    ["id", "name", "starting_at"]),
        
        EndpointTest("Live Scores", "Live Matches", 
                    f"{self.base_url}/livescores/inplay",
                    "Currently live matches with scores", 
                    ["id", "name", "time", "scores"]),
        
        EndpointTest("Leagues", "Top Leagues", 
                    f"{self.base_url}/leagues",
                    "Available football leagues", 
                    ["id", "name", "country_id", "is_cup"]),
        
        EndpointTest("Teams", "All Teams (Limited)", 
                    f"{self.base_url}/teams?per_page=50",
                    "Football teams (first 50)", 
                    ["id", "name", "country_id", "founded"]),
        
        # Advanced endpoints with discovered IDs
        EndpointTest("Predictions", "Fixture Probabilities", 
                    f"{self.base_url}/predictions/probabilities/fixtures/{{fixture_id}}",
                    "Predictions for specific match", 
                    ["fixture_id", "predictions"], True, "fixture_id"),
        
        EndpointTest("Odds", "Fixture Pre-match Odds", 
                    f"{self.base_url}/odds/pre-match/fixtures/{{fixture_id}}",
                    "Pre-match odds for specific fixture", 
                    ["fixture_id", "market_id", "bookmaker_id"], True, "fixture_id"),
        
        EndpointTest("Combined", "Full Betting Data", 
                    f"{self.base_url}/fixtures/{{fixture_id}}?include=odds.bookmaker,odds.market,predictions,probabilities,participants",
                    "Complete betting info for one match", 
                    ["id", "odds", "predictions", "participants"], True, "fixture_id"),
    ]
    
    return endpoints

def discover_ids_from_response(self, response_data: Dict, endpoint_name: str):
    """Extract IDs from responses"""
    if not isinstance(response_data, dict) or 'data' not in response_data:
        return
    
    data = response_data['data']
    if not data:
        return
        
    items = data if isinstance(data, list) else [data]
    
    for item in items[:3]:  # Check fewer items for mobile performance
        if not isinstance(item, dict):
            continue
            
        # Extract IDs efficiently
        if 'starting_at' in item or 'localteam_id' in item:
            if not self.discovered_ids['fixture_id'] and 'id' in item:
                self.discovered_ids['fixture_id'] = str(item['id'])
        
        if endpoint_name == "All Bookmakers" and not self.discovered_ids['bookmaker_id']:
            if 'id' in item:
                self.discovered_ids['bookmaker_id'] = str(item['id'])
        
        if endpoint_name == "All Markets" and not self.discovered_ids['market_id']:
            if 'id' in item:
                self.discovered_ids['market_id'] = str(item['id'])
        
        if 'league_id' in item and not self.discovered_ids['league_id']:
            self.discovered_ids['league_id'] = str(item['league_id'])
        
        if 'season_id' in item and not self.discovered_ids['season_id']:
            self.discovered_ids['season_id'] = str(item['season_id'])

def analyze_data_structure(self, data: Any, max_depth: int = 2) -> Dict:
    """Simplified data structure analysis for mobile"""
    if isinstance(data, dict):
        return {
            "type": "dict",
            "key_count": len(data),
            "sample_keys": list(data.keys())[:5]
        }
    elif isinstance(data, list):
        return {
            "type": "list", 
            "length": len(data),
            "item_type": type(data[0]).__name__ if data else "unknown"
        }
    else:
        return {"type": type(data).__name__, "sample": str(data)[:50]}

def test_single_endpoint(self, endpoint: EndpointTest) -> TestResult:
    """Test one endpoint - optimized for web"""
    url = endpoint.url
    errors = []
    
    # Handle ID substitution
    if endpoint.requires_id and endpoint.test_id:
        required_ids = endpoint.test_id.split(',')
        for id_key in required_ids:
            placeholder = f"{{{id_key}}}"
            if placeholder in url:
                if self.discovered_ids[id_key]:
                    url = url.replace(placeholder, self.discovered_ids[id_key])
                else:
                    return TestResult(
                        endpoint=endpoint.name,
                        status_code=0, success=False, data_count=0, response_time=0,
                        data_structure={}, sample_data={},
                        errors=[f"ID {id_key} not available"], warnings=[]
                    )
    
    start_time = time.time()
    
    try:
        response = self.session.get(url, timeout=15)
        response_time = time.time() - start_time
        
        if response.status_code != 200:
            return TestResult(
                endpoint=endpoint.name, status_code=response.status_code,
                success=False, data_count=0, response_time=response_time,
                data_structure={}, sample_data={},
                errors=[f"HTTP {response.status_code}"], warnings=[]
            )
        
        response_data = response.json()
        self.discover_ids_from_response(response_data, endpoint.name)
        
        # Extract key info
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
            data_structure=self.analyze_data_structure(response_data),
            sample_data=sample_data,
            errors=[],
            warnings=[]
        )
        
    except Exception as e:
        return TestResult(
            endpoint=endpoint.name, status_code=0, success=False,
            data_count=0, response_time=time.time() - start_time,
            data_structure={}, sample_data={},
            errors=[str(e)[:100]], warnings=[]
        )

def run_tests_async(self):
    """Run tests in background thread"""
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
            if not self.is_testing:  # Allow stopping
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

def get_summary_stats(self) -> Dict:
    """Get summary statistics for mobile display"""
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
```

# Flask Web Application

app = Flask(**name**)
tester = None

@app.errorhandler(500)
def internal_error(error):
return jsonify({‘error’: ‘Internal server error’}), 500

@app.errorhandler(404)
def not_found(error):
return jsonify({‘error’: ‘Not found’}), 404

@app.route(’/’)
def home():
return render_template(‘index.html’)

@app.route(’/api/start-test’, methods=[‘POST’])
def start_test():
global tester

```
data = request.get_json()
api_token = data.get('api_token', '').strip()

if not api_token:
    return jsonify({'error': 'API token required'}), 400

if tester and tester.is_testing:
    return jsonify({'error': 'Test already running'}), 400

try:
    tester = SportMonksWebTester(api_token)
    
    # Start testing in background thread
    thread = threading.Thread(target=tester.run_tests_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Test started'})
    
except Exception as e:
    return jsonify({'error': str(e)}), 500
```

@app.route(’/api/test-progress’)
def get_progress():
if not tester:
return jsonify({‘progress’: {‘current’: 0, ‘total’: 0, ‘status’: ‘idle’}})

```
return jsonify({
    'progress': tester.testing_progress,
    'discovered_ids': tester.discovered_ids
})
```

@app.route(’/api/test-results’)
def get_results():
if not tester:
return jsonify({‘results’: [], ‘summary’: {}})

```
# Convert dataclass results to dict
results_dict = []
for result in tester.test_results:
    result_dict = asdict(result)
    # Truncate sample data for mobile
    if len(str(result_dict['sample_data'])) > 500:
        result_dict['sample_data'] = {'truncated': 'Data too large for mobile display'}
    results_dict.append(result_dict)

return jsonify({
    'results': results_dict,
    'summary': tester.get_summary_stats(),
    'discovered_ids': tester.discovered_ids
})
```

@app.route(’/api/stop-test’, methods=[‘POST’])
def stop_test():
global tester
if tester:
tester.is_testing = False
return jsonify({‘success’: True, ‘message’: ‘Test stopped’})
return jsonify({‘error’: ‘No test running’}), 400

@app.route(’/api/download-report’)
def download_report():
if not tester or not tester.test_results:
return jsonify({‘error’: ‘No results available’}), 400

```
# Generate JSON report
report_data = {
    'timestamp': datetime.now().isoformat(),
    'summary': tester.get_summary_stats(),
    'discovered_ids': tester.discovered_ids,
    'results': [asdict(result) for result in tester.test_results]
}

# Create downloadable file
report_json = json.dumps(report_data, indent=2, default=str)

# Create in-memory file
buffer = io.BytesIO(report_json.encode('utf-8'))
buffer.seek(0)

return send_file(
    buffer,
    mimetype='application/json',
    as_attachment=True,
    download_name='sportmonks_test_results.json'
)
```

@app.route(’/health’)
def health_check():
return jsonify({
‘status’: ‘healthy’,
‘timestamp’: datetime.now().isoformat(),
‘testing_status’: tester.testing_progress[‘status’] if tester else ‘idle’
})

if **name** == ‘**main**’:
port = int(os.environ.get(‘PORT’, 5000))
debug = os.environ.get(‘FLASK_ENV’) != ‘production’
app.run(host=‘0.0.0.0’, port=port, debug=debug)
