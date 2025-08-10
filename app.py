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
                except:
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
                        except:
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

        # Dates
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        endpoints_to_test = [
            ("my_subscription", f"{base_urls[1]}/my/subscription"),
            ("my_resources", f"{base_urls[1]}/my/resources"),
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
            ("livescores", f"{base_urls[0]}/livescores"),
            ("livescores_inplay", f"{base_urls[0]}/livescores/inplay"),
            ("livescores_latest", f"{base_urls[0]}/livescores/latest"),
            ("fixtures_today", f"{base_urls[0]}/fixtures/date/{today}"),
            ("fixtures_tomorrow", f"{base_urls[0]}/fixtures/date/{tomorrow}"),
            ("fixtures_yesterday", f"{base_urls[0]}/fixtures/date/{yesterday}"),
            ("fixtures_between", f"{base_urls[0]}/fixtures/between/{yesterday}/{tomorrow}"),
            ("results_today", f"{base_urls[0]}/results/date/{today}"),
            ("results_yesterday", f"{base_urls[0]}/results/date/{yesterday}"),
            ("tv_stations", f"{base_urls[0]}/tv-stations"),
            ("news_pre_match", f"{base_urls[0]}/news/pre-match"),
            ("news_post_match", f"{base_urls[0]}/news/post-match"),
            ("predictions", f"{base_urls[0]}/predictions"),
            ("predictions_probabilities", f"{base_urls[0]}/predictions/probabilities"),
            ("predictions_value_bets", f"{base_urls[0]}/predictions/value-bets"),
            ("bookmakers", f"{base_urls[2]}/bookmakers"),
            ("markets", f"{base_urls[2]}/markets"),
            ("odds_pre_match", f"{base_urls[2]}/pre-match"),
            ("odds_inplay", f"{base_urls[2]}/inplay"),
            ("standings", f"{base_urls[0]}/standings"),
            ("topscorers", f"{base_urls[0]}/topscorers"),
            ("statistics", f"{base_urls[0]}/statistics"),
            ("transfers", f"{base_urls[0]}/transfers"),
            ("commentaries", f"{base_urls[0]}/commentaries"),
        ]

        for name, url in endpoints_to_test:
            self.test_endpoint(name, url, {"per_page": "10"})

        self._test_specific_fixtures()

        print("=" * 50)
        print(f"✅ WORKING ENDPOINTS: {len(self.working_endpoints)}")
        print(f"❌ FAILED ENDPOINTS: {len(self.results) - len(self.working_endpoints)}")

        return self.generate_report()

    def _test_specific_fixtures(self):
        """Test specific fixture endpoints if we found any fixture IDs"""
        fixture_ids = []
        for endpoint_name, result in self.results.items():
            if result.get("success") and result.get("data"):
                data = result["data"]
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        for item in items[:3]:
                            if isinstance(item, dict) and "id" in item:
                                fixture_ids.append(item["id"])

        for fid in fixture_ids[:5]:
            self.test_endpoint(f"fixture_{fid}", f"https://api.sportmonks.com/v3/football/fixtures/{fid}")
            self.test_endpoint(f"fixture_{fid}_includes", f"https://api.sportmonks.com/v3/football/fixtures/{fid}", {"include": "participants,league,venue"})

    def generate_report(self) -> Dict:
        """Generate comprehensive report"""
        working_data = {}
        failed_data = {}

        for name, result in self.results.items():
            if result["success"]:
                data = result.get("data", {})
                if isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        working_data[name] = {
                            "status": "success",
                            "count": len(items),
                            "sample": items[0] if items else None,
                            "all_data": items[:5]
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


# For Gunicorn
application = app