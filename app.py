#!/usr/bin/env python3
"""
SportMonks v3 API Web Tester - Railway Deployment
Web interface for testing SportMonks API from iPhone/browser
"""

import io
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from flask import Flask, render_template, jsonify, request, send_file


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
        self.session.params = {"api_token": api_token}

        self.discovered_ids: Dict[str, Optional[str]] = {
            "fixture_id": None,
            "league_id": None,
            "season_id": None,
            "team_id": None,
            "player_id": None,
            "bookmaker_id": None,
            "market_id": None,
            "round_id": None,
            "stage_id": None,
        }

        self.test_results: List[TestResult] = []
        self.testing_progress: Dict[str, Any] = {"current": 0, "total": 0, "status": "idle"}
        self.is_testing: bool = False

    def setup_test_endpoints(self) -> List[EndpointTest]:
        """Define all endpoints to test"""
        today = datetime.now().strftime("%Y-%m-%d")
        endpoints = [
            EndpointTest(
                "Predictions",
                "All Probabilities",
                f"{self.base_url}/predictions/probabilities",
                "Match probabilities for upcoming games",
                ["fixture_id", "predictions", "type_id"],
            ),
            EndpointTest(
                "Predictions",
                "All Value Bets",
                f"{self.base_url}/predictions/valuebets",
                "AI-detected value betting opportunities",
                ["fixture_id", "predictions", "type_id"],
            ),
            EndpointTest(
                "Odds",
                "All Pre-match Odds",
                f"{self.base_url}/odds/pre-match",
                "Current pre-match betting odds",
                ["fixture_id", "market_id", "bookmaker_id", "value"],
            ),
            EndpointTest(
                "Bookmakers",
                "All Bookmakers",
                f"{self.odds_base_url}/bookmakers",
                "Available bookmakers and their IDs",
                ["id", "name", "legacy_id"],
            ),
            EndpointTest(
                "Markets",
                "All Markets",
                f"{self.odds_base_url}/markets",
                "Available betting markets",
                ["id", "name", "has_winning_calculations"],
            ),
            EndpointTest(
                "Fixtures",
                "Today's Fixtures",
                f"{self.base_url}/fixtures/date/{today}",
                "Today's football matches",
                ["id", "name", "starting_at", "localteam_id", "visitorteam_id"],
            ),
            EndpointTest(
                "Live Scores",
                "Live Matches",
                f"{self.base_url}/livescores/inplay",
                "Currently live matches with scores",
                ["id", "name", "time", "scores"],
            ),
            EndpointTest(
                "Leagues",
                "Top Leagues",
                f"{self.base_url}/leagues",
                "Available football leagues",
                ["id", "name", "country_id", "is_cup"],
            ),
        ]
        return endpoints

    def discover_ids_from_response(self, response_data: Dict, endpoint_name: str) -> None:
        """Extract IDs from responses"""
        if not isinstance(response_data, dict) or "data" not in response_data:
            return

        data = response_data["data"]
        if not data:
            return

        items = data if isinstance(data, list) else [data]

        for item in items[:3]:
            if not isinstance(item, dict):
                continue

            # Fixtures
            if ("starting_at" in item or "localteam_id" in item) and not self.discovered_ids["fixture_id"]:
                if "id" in item:
                    self.discovered_ids["fixture_id"] = str(item["id"])

            # Bookmakers
            if endpoint_name == "All Bookmakers" and not self.discovered_ids["bookmaker_id"]:
                if "id" in item:
                    self.discovered_ids["bookmaker_id"] = str(item["id"])

    def analyze_data_structure(self, data: Any) -> Dict:
        """Analyze data structure"""
        if isinstance(data, dict):
            return {
                "type": "dict",
                "key_count": len(data),
                "sample_keys": list(data.keys())[:5],
            }
        elif isinstance(data, list):
            return {
                "type": "list",
                "length": len(data),
                "item_type": type(data[0]).__name__ if data else "unknown",
            }
        else:
            return {"type": type(data).__name__, "sample": str(data)[:50]}

    def test_single_endpoint(self, endpoint: EndpointTest) -> TestResult:
        """Test one endpoint"""
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
                    warnings=[],
                )

            response_data = response.json()
            self.discover_ids_from_response(response_data, endpoint.name)

            data_count = 0
            sample_data: Dict[str, Any] = {}

            if "data" in response_data:
                data = response_data["data"]
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
                sample_data=sample_data