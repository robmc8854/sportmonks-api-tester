#!/usr/bin/env python3
"""
SPORTMONKS REALITY CHECK
Test every possible endpoint to find what actually works on your plan.
Shows raw responses so you can see exactly what data is available.
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


class SportMonksRealityCheck:
    def __init__(self, api_token: str):
        self.api_token = api_token.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json"
        })
        self.results = {}
        self.working_endpoints = []

    def test_endpoint(self, name: str, url: str, params: Dict = None) -> Dict:
        """Test a single endpoint and return detailed results"""
        try:
            # First try with token in header
            query_params = params or {}

            print(f"Testing {name}: {url}")
            response = self.session.get(url, params=query_params, timeout=30)

            result = {
                "endpoint": name,
                "url": url,
                "status_code": response.status_code,
                "success": False,
                "data": None,
                "error": None,
                "response_text": response.text[:500] if response.text else None
            }

            if response.status_code == 200:
                try:
                    data = response.json()
                    result["success"] = True
                    result["data"] = data
                    self.working_endpoints.append(name)
                    print(f"✅ {name} - SUCCESS")
                except Exception:
                    result["error"] = "Invalid JSON response"
                    print(f"❌ {name} - Invalid JSON")
            else:
                result["error"] = f"HTTP {response.status_code}"
                print(f"❌ {name} - HTTP {response.status_code}")

                # If header auth failed, try with api_token in query params
                if response.status_code in [401, 403]:
                    print(f"Retrying {name} with token in query params...")
                    query_params["api_token"] = self.api_token
                    retry_response = requests.get(url, params=query_params, timeout=30)

                    if retry_response.status_code == 200:
                        try:
                            data = retry_response.json()
                            result["success"] = True
                            result["data"] = data
                            result["status_code"] = 200
                            result["error"] = None
                            self.working_endpoints.append(name)
                            print(f"✅ {name} - SUCCESS (with query param)")
                        except Exception:
                            print(f"❌ {name} - Invalid JSON on retry")
                    else:
                        print(f"❌ {name} - Still failed on retry: {retry_response.status_code}")

            self.results[name] = result
            return result

        except Exception as e:
            result = {
                "endpoint": name,
                "url": url,
                "status_code": None,
                "success": False,
                "data": None,
                "error": str(e),
                "response_text": None
            }
            self.results[name] = result
            print(f"❌ {name} - Exception: {str(e)}")
            return result

    def test_all_endpoints(self) -> Dict:
        """Test every possible SportMonks endpoint"""
        print("🔍 TESTING ALL SPORTMONKS ENDPOINTS")
        print("=" * 50)

        base_urls = [
            "https://api.sportmonks.com/v3/football",
            "https://api.sportmonks.com/v3/core",
            "https://api.sportmonks.com/v3/odds"
        ]

        # Today and tomorrow dates
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Test basic endpoints first
        endpoints_to_test = [
            # Core endpoints
            ("my_subscription", f"{base_urls[1]}/my/subscription"),
            ("my_resources", f"{base_urls[1]}/my/resources"),

            # Football basic
            ("leagues", f"{base_urls[0]}/leagues"),
            ("seasons", f"{base_urls[0]}/seasons"),
            ("teams", f"{base_urls[0]}/teams"),
            ("players", f"{base_urls[0]}/players"),
            ("coaches", f"{base_urls[0]}/coaches"),
            ("venues", f"{base_urls[0]}/venues"),
            ("countries", f"{base_urls[1]}/countries"),
            ("continents", f"{base_urls[1]}/continents"),
            ("regions", f"{base_urls[1]}/regions"),
            ("cities", f"{base_urls[1]}/cities"),
            ("types", f"{base_urls[1]}/types"),

            # Live data
            ("livescores", f"{base_urls[0]}/livescores"),
            ("livescores_inplay", f"{base_urls[0]}/livescores/inplay"),
            ("livescores_latest", f"{base_urls[0]}/livescores/latest"),

            # Fixtures
            ("fixtures_today", f"{base_urls[0]}/fixtures/date/{today}"),
            ("fixtures_tomorrow", f"{base_urls[0]}/fixtures/date/{tomorrow}"),
            ("fixtures_yesterday", f"{base_urls[0]}/fixtures/date/{yesterday}"),
            ("fixtures_between", f"{base_urls[0]}/fixtures/between/{yesterday}/{tomorrow}"),

            # Results
            ("results_today", f"{base_urls[0]}/results/date/{today}"),
            ("results_yesterday", f"{base_urls[0]}/results/date/{yesterday}"),

            # TV Stations
            ("tv_stations", f"{base_urls[0]}/tv-stations"),

            # News
            ("news_pre_match", f"{base_urls[0]}/news/pre-match"),
            ("news_post_match", f"{base_urls[0]}/news/post-match"),

            # Predictions
            ("predictions", f"{base_urls[0]}/predictions"),
            ("predictions_probabilities", f"{base_urls[0]}/predictions/probabilities"),
            ("predictions_value_bets", f"{base_urls[0]}/predictions/value-bets"),

            # Odds endpoints
            ("bookmakers", f"{base_urls[2]}/bookmakers"),
            ("markets", f"{base_urls[2]}/markets"),
            ("odds_pre_match", f"{base_urls[2]}/pre-match"),
            ("odds_inplay", f"{base_urls[2]}/inplay"),

            # Standings
            ("standings", f"{base_urls[0]}/standings"),
            ("topscorers", f"{base_urls[0]}/topscorers"),

            # Statistics
            ("statistics", f"{base_urls[0]}/statistics"),

            # Transfers
            ("transfers", f"{base_urls[0]}/transfers"),

            # Commentary
            ("commentaries", f"{base_urls[0]}/commentaries"),
        ]

        # Test each endpoint
        for name, url in endpoints_to_test:
            self.test_endpoint(name, url, {"per_page": "10"})

        # Test some specific fixture IDs if we found any fixtures
        self._test_specific_fixtures()

        print("=" * 50)
        print(f"✅ WORKING ENDPOINTS: {len(self.working_endpoints)}")
        print(f"❌ FAILED ENDPOINTS: {len(self.results) - len(self.working_endpoints)}")

        return self.generate_report()

    def _test_specific_fixtures(self):
        """Test specific fixture endpoints if we found any fixture IDs"""
        fixture_ids = []

        # Look for fixture IDs in our successful responses
        for endpoint_name, result in self.results.items():
            if result.get("success") and result.get("data"):
                data = result["data"]
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        for item in items[:3]:  # Just test first 3
                            if isinstance(item, dict) and "id" in item:
                                fixture_ids.append(item["id"])

        # Test specific fixture endpoints
        for fid in fixture_ids[:5]:  # Test max 5 fixtures
            self.test_endpoint(f"fixture_{fid}", f"https://api.sportmonks.com/v3/football/fixtures/{fid}")
            self.test_endpoint(
                f"fixture_{fid}_includes",
                f"https://api.sportmonks.com/v3/football/fixtures/{fid}",
                {"include": "participants,league,venue"}
            )

    def generate_report(self) -> Dict:
        """Generate comprehensive report"""
        working_data = {}
        failed_data = {}

        for name, result in self.results.items():
            if result["success"]:
                # Summarize successful data
                data = result.get("data", {})
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        working_data[name] = {
                            "status": "success",
                            "count": len(items),
                            "sample": items[0] if items else None,
                            "all_data": items[:5]  # First 5 items
                        }
                    else:
                        working_data[name] = {
                            "status": "success",
                            "count": 1,
                            "sample": items,
                            "all_data": items
                        }
                else:
                    working_data[name] = {
                        "status": "success",
                        "count": 0,
                        "sample": data,
                        "all_data": data
                    }
            else:
                failed_data[name] = {
                    "status": "failed",
                    "error": result.get("error"),
                    "status_code": result.get("status_code"),
                    "response_preview": result.get("response_text", "")[:200]
                }

        return {
            "working_endpoints": len(self.working_endpoints),
            "failed_endpoints": len(self.results) - len(self.working_endpoints),
            "working_data": working_data,
            "failed_data": failed_data,
            "raw_results": self.results
        }


# Flask App

app = Flask(__name__)
checker: Optional[SportMonksRealityCheck] = None


@app.route("/")
def home():
    return """

<!DOCTYPE html>

<html>
<head>
<title>SportMonks Reality Check</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f0f0; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { color: #2c3e50; text-align: center; }
.card { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.btn { background: #3498db; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
.btn:hover { background: #2980b9; }
.btn.success { background: #27ae60; }
.btn.danger { background: #e74c3c; }
input[type="password"] { padding: 12px; border: 1px solid #ddd; border-radius: 4px; width: 300px; margin-right: 10px; }
.endpoint { margin: 10px 0; padding: 15px; border-radius: 4px; }
.endpoint.success { background: #d4edda; border-left: 4px solid #28a745; }
.endpoint.failed { background: #f8d7da; border-left: 4px solid #dc3545; }
.data-preview { background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 10px; max-height: 200px; overflow-y: auto; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }
.stat { background: #34495e; color: white; padding: 15px; border-radius: 4px; text-align: center; }
.loading { text-align: center; color: #7f8c8d; padding: 20px; }
.error { color: #e74c3c; background: #fdf2f2; padding: 10px; border-radius: 4px; }
.success-msg { color: #27ae60; background: #f0fff4; padding: 10px; border-radius: 4px; }
.raw-data { background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 4px; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 12px; }
</style>
</head>
<body>
<div class="container">
<h1>🔍 SportMonks Reality Check</h1>
<p style="text-align: center; color: #7f8c8d;">Find out exactly what your SportMonks API token can actually access</p>

<div class="card">
    <h2>🔐 API Token Test</h2>
    <input type="password" id="apiToken" placeholder="Enter SportMonks API Token">
    <button class="btn success" onclick="runFullTest()">🚀 Test Everything</button>
    <div id="testStatus"></div>
</div>

<div class="card">
    <h2>📊 Results Summary</h2>
    <div id="summary">Run the test to see what endpoints work</div>
</div>

<div class="card">
    <h2>✅ Working Endpoints</h2>
    <div id="workingEndpoints">No test run yet</div>
</div>

<div class="card">
    <h2>❌ Failed Endpoints</h2>
    <div id="failedEndpoints">No test run yet</div>
</div>

<div class="card">
    <h2>🔧 Raw Data Samples</h2>
    <div id="rawData">No data yet</div>
</div>
</div>

<script>
async function runFullTest() {
    const token = document.getElementById('apiToken').value.trim();
    if (!token) {
        document.getElementById('testStatus').innerHTML = '<div class="error">Please enter your API token</div>';
        return;
    }
    
    document.getElementById('testStatus').innerHTML = '<div class="loading">🔍 Testing all SportMonks endpoints... This may take 1-2 minutes...</div>';
    document.getElementById('summary').innerHTML = '<div class="loading">Testing in progress...</div>';
    document.getElementById('workingEndpoints').innerHTML = '<div class="loading">Testing...</div>';
    document.getElementById('failedEndpoints').innerHTML = '<div class="loading">Testing...</div>';
    
    try {
        const response = await fetch('/api/test-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayResults(data.report);
            document.getElementById('testStatus').innerHTML = '<div class="success-msg">✅ Test completed! See results below.</div>';
        } else {
            document.getElementById('testStatus').innerHTML = '<div class="error">❌ ' + data.error + '</div>';
        }
    } catch (error) {
        document.getElementById('testStatus').innerHTML = '<div class="error">❌ Network error: ' + error.message + '</div>';
    }
}

function displayResults(report) {
    // Summary
    const summaryHtml = `
        <div class="stats">
            <div class="stat">
                <h3>✅ Working Endpoints</h3>
                <div style="font-size: 2em;">${report.working_endpoints}</div>
            </div>
            <div class="stat">
                <h3>❌ Failed Endpoints</h3>
                <div style="font-size: 2em;">${report.failed_endpoints}</div>
            </div>
            <div class="stat">
                <h3>📊 Success Rate</h3>
                <div style="font-size: 2em;">${Math.round((report.working_endpoints / (report.working_endpoints + report.failed_endpoints)) * 100)}%</div>
            </div>
        </div>
    `;
    document.getElementById('summary').innerHTML = summaryHtml;
    
    // Working endpoints
    let workingHtml = '';
    Object.entries(report.working_data).forEach(([name, info]) => {
        workingHtml += `
            <div class="endpoint success">
                <h4>✅ ${name}</h4>
                <p><strong>Items found:</strong> ${info.count}</p>
                ${info.sample ? `
                    <div class="data-preview">
                        <strong>Sample data:</strong>
                        <pre>${JSON.stringify(info.sample, null, 2)}</pre>
                    </div>
                ` : ''}
            </div>
        `;
    });
    document.getElementById('workingEndpoints').innerHTML = workingHtml || '<p>No working endpoints found</p>';

    // Failed endpoints
    let failedHtml = '';
    Object.entries(report.failed_data).forEach(([name, info]) => {
        failedHtml += `
            <div class="endpoint failed">
                <h4>❌ ${name}</h4>
                <p><strong>Error:</strong> ${info.error}</p>
                <p><strong>Status Code:</strong> ${info.status_code}</p>
                ${info.response_preview ? `<p><strong>Response:</strong> ${info.response_preview}</p>` : ''}
            </div>
        `;
    });
    document.getElementById('failedEndpoints').innerHTML = failedHtml || '<p>All endpoints working!</p>';

    // Raw data
    document.getElementById('rawData').innerHTML = `
        <div class="raw-data">
${JSON.stringify(report.working_data, null, 2)}
        </div>
    `;
}
</script>

</body>
</html>
    """


@app.route("/api/test-all", methods=["POST"])
def test_all():
    global checker
    data = request.get_json() or {}
    api_token = data.get("api_token")

    if not api_token:
        return jsonify({"success": False, "error": "API token required"})

    try:
        checker = SportMonksRealityCheck(api_token)
        report = checker.test_all_endpoints()

        return jsonify({
            "success": True,
            "report": report
        })
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return jsonify({"success": False, "error": f"Test failed: {str(e)}"})


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

application = app