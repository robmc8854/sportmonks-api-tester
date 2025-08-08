#!/usr/bin/env python3
"""
COMPLETE ENHANCED SPORTMONKS BETTING BOT ANALYZER

- Fixed v3 API parameter handling and authentication
- Comprehensive endpoint testing with proper error handling
- AI prediction capabilities for betting analysis (optional)
- Enhanced debugging and subscription tier detection
"""

import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import requests
from flask import Flask, jsonify, request

# ==============================
# Optional imports
# ==============================

try:
    from flask_cors import CORS  # type: ignore
    _HAS_CORS = True
except Exception:
    CORS = None  # type: ignore
    _HAS_CORS = False

try:
    import numpy as np  # type: ignore
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
    _HAS_ML = True
except Exception:
    np = None  # type: ignore
    RandomForestClassifier = None  # type: ignore
    StandardScaler = None  # type: ignore
    _HAS_ML = False

# ==============================
# Configure logging
# ==============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================
# Enhanced Data Models
# ==============================

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
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    subscription_tier_required: str = "basic"
    rate_limit_info: Dict = field(default_factory=dict)

@dataclass
class BettingPrediction:
    fixture_id: int
    home_team: str
    away_team: str
    predicted_outcome: str  # "1", "X", "2"
    confidence: float
    expected_home_goals: float
    expected_away_goals: float
    recommended_bets: List[Dict]
    risk_assessment: str

# ==============================
# Complete Enhanced Analyzer
# ==============================

class CompleteBettingAnalyzer:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_base_url = "https://api.sportmonks.com/v3/odds"

        # Enhanced session setup
        self.session = requests.Session()
        self.session.timeout = 30

        # v3: include both header Bearer and api_token param for compatibility
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SportMonks-Enhanced-Bot/2.0",
        })

        # Core data storage
        self.test_results: List[EndpointResult] = []
        self.discovered_data: Dict[str, List[Any]] = {
            "fixture_ids": [],
            "team_ids": [],
            "league_ids": [],
            "season_ids": [],
            "bookmaker_ids": [],
            "market_ids": [],
            "player_ids": [],
            "venue_ids": [],
        }

        # Progress tracking
        self.testing_progress = {
            "current": 0,
            "total": 0,
            "status": "idle",
            "current_test": "",
            "phase": "idle",
            "detailed_log": [],
            "errors_encountered": 0,
            "success_count": 0,
        }

        self.is_testing = False
        self.complete_analysis: Dict[str, Any] = {}
        self.subscription_info: Dict[str, Any] = {}

        # ML Models (if available)
        if _HAS_ML:
            self.outcome_predictor = None
            self.goals_predictor = None
            self.scaler = StandardScaler()

    # ------------------------------

    def _enhanced_get_json(
        self, url: str, params: Dict = None, timeout: int = 30
    ) -> Tuple[int, Dict, float, Optional[str]]:
        """Enhanced HTTP method with v3 fixes and detailed logging"""
        start = time.time()

        try:
            # Always include api_token in params
            request_params = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            # Make request with both auth methods
            response = self.session.get(url, params=request_params, timeout=timeout)
            elapsed = time.time() - start

            # Enhanced error logging
            if response.status_code != 200:
                error_details = {
                    "url": url,
                    "params": request_params,
                    "status": response.status_code,
                    "content_preview": response.text[:300] if response.text else "No content",
                }

                if response.status_code == 403:
                    logger.warning(f"403 FORBIDDEN - Subscription issue: {url}")
                elif response.status_code == 422:
                    logger.warning(f"422 VALIDATION ERROR - Parameter issue: {error_details}")
                elif response.status_code == 404:
                    logger.warning(f"404 NOT FOUND - Endpoint issue: {url}")
                elif response.status_code == 429:
                    logger.warning(f"429 RATE LIMIT - Slow down requests: {url}")

            # Parse JSON safely
            try:
                json_data = response.json() if response.status_code == 200 else {}
            except Exception:
                json_data = {}

            return response.status_code, json_data, elapsed, None

        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            logger.error(f"TIMEOUT after {timeout}s: {url}")
            return 0, {}, elapsed, f"Request timeout after {timeout}s"

        except requests.exceptions.RequestException as e:
            elapsed = time.time() - start
            logger.error(f"REQUEST ERROR: {url} - {str(e)}")
            return 0, {}, elapsed, f"Request failed: {str(e)[:200]}"

        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"UNEXPECTED ERROR: {url} - {str(e)}")
            return 0, {}, elapsed, f"Unexpected error: {str(e)[:200]}"

    # ------------------------------

    def get_comprehensive_endpoints(self) -> List[Dict]:
        """Comprehensive endpoint list with v3 fixes and proper parameters"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        fb = self.base_url
        ob = self.odds_base_url

        endpoints: List[Dict[str, Any]] = []

        # CRITICAL BETTING DATA
        endpoints += [
            {
                "name": "Today Fixtures Complete",
                "url": f"{fb}/fixtures/date/{today}",
                "params": {"include": "participants,league,venue,state,scores,events.type"},
                "category": "Fixtures",
                "tier": "basic",
                "priority": "critical",
            },
            {
                "name": "Tomorrow Fixtures",
                "url": f"{fb}/fixtures/date/{tomorrow}",
                "params": {"include": "participants,league,venue,state"},
                "category": "Fixtures",
                "tier": "basic",
                "priority": "high",
            },
            {
                "name": "Recent Results",
                "url": f"{fb}/fixtures/date/{yesterday}",
                "params": {"include": "participants,league,scores,events.type"},
                "category": "Fixtures",
                "tier": "basic",
                "priority": "high",
            },
        ]

        # Live data
        endpoints += [
            {
                "name": "Live Scores All",
                "url": f"{fb}/livescores",
                "params": {"include": "participants,league,scores,events.type"},
                "category": "Live",
                "tier": "basic",
                "priority": "critical",
            },
            {
                "name": "Live In-play Only",
                "url": f"{fb}/livescores/inplay",
                "params": {"include": "participants,league,scores,events.type,events.player"},
                "category": "Live",
                "tier": "basic",
                "priority": "critical",
            },
            {
                "name": "Live Latest Updates",
                "url": f"{fb}/livescores/latest",
                "params": {"include": "participants,league,scores"},
                "category": "Live",
                "tier": "basic",
                "priority": "high",
            },
        ]

        # Odds (may require premium)
        endpoints += [
            {
                "name": "Pre-match Odds Active",
                "url": f"{ob}/pre-match",
                "params": {"include": "fixture,bookmaker,market", "per_page": "200"},
                "category": "Odds",
                "tier": "premium",
                "priority": "critical",
            },
            {
                "name": "In-play Odds Live",
                "url": f"{ob}/inplay",
                "params": {"include": "fixture,bookmaker,market", "per_page": "200"},
                "category": "Odds",
                "tier": "premium",
                "priority": "critical",
            },
            {
                "name": "Pre-match Latest Updates",
                "url": f"{ob}/pre-match/latest",
                "params": {"include": "fixture,bookmaker,market", "per_page": "100"},
                "category": "Odds",
                "tier": "premium",
                "priority": "high",
            },
        ]

        # Market / bookmaker refs
        endpoints += [
            {
                "name": "All Markets",
                "url": f"{ob}/markets",
                "params": {"per_page": "250"},
                "category": "Markets",
                "tier": "basic",
                "priority": "high",
            },
            {
                "name": "All Bookmakers",
                "url": f"{ob}/bookmakers",
                "params": {"per_page": "250"},
                "category": "Bookmakers",
                "tier": "basic",
                "priority": "high",
            },
        ]

        # PREMIUM FEATURES (predictions)
        endpoints += [
            {
                "name": "Predictions Probabilities",
                "url": f"{fb}/predictions/probabilities",
                "params": {"include": "fixture,predictions", "per_page": "100"},
                "category": "Predictions",
                "tier": "premium",
                "priority": "critical",
            },
            {
                "name": "Value Bets",
                "url": f"{fb}/predictions/value-bets",
                "params": {"include": "fixture,predictions,odds", "per_page": "100"},
                "category": "Predictions",
                "tier": "premium",
                "priority": "critical",
            },
            {
                "name": "Predictions for Today",
                "url": f"{fb}/predictions/probabilities/fixtures/date/{today}",
                "params": {"include": "fixture,predictions"},
                "category": "Predictions",
                "tier": "premium",
                "priority": "high",
            },
        ]

        # SUBSCRIPTION & DEBUGGING
        endpoints += [
            {
                "name": "My Subscription Info",
                "url": f"{fb}/my/subscription",
                "params": {},
                "category": "Subscription",
                "tier": "basic",
                "priority": "critical",
            },
            {
                "name": "My Available Leagues",
                "url": f"{fb}/my/leagues",
                "params": {"per_page": "250"},
                "category": "Subscription",
                "tier": "basic",
                "priority": "high",
            },
            {
                "name": "My Resources",
                "url": f"{fb}/my/resources",
                "params": {},
                "category": "Subscription",
                "tier": "basic",
                "priority": "medium",
            },
            {
                "name": "My Enrichments",
                "url": f"{fb}/my/enrichments",
                "params": {},
                "category": "Subscription",
                "tier": "basic",
                "priority": "medium",
            },
        ]

        # SUPPORTING DATA
        endpoints += [
            {
                "name": "Active Leagues",
                "url": f"{fb}/leagues",
                "params": {"include": "country,seasons", "filter[active]": "true", "per_page": "100"},
                "category": "Leagues",
                "tier": "basic",
                "priority": "medium",
            },
            {
                "name": "Current Seasons",
                "url": f"{fb}/seasons",
                "params": {"include": "league,stages", "filter[active]": "true", "per_page": "100"},
                "category": "Seasons",
                "tier": "basic",
                "priority": "medium",
            },
            {
                "name": "Teams with Stats",
                "url": f"{fb}/teams",
                "params": {"include": "country,venue,activeSeasons", "per_page": "100"},
                "category": "Teams",
                "tier": "basic",
                "priority": "medium",
            },
            {
                "name": "Live Standings",
                "url": f"{fb}/standings/live",
                "params": {"include": "team,league,season,form.fixtures.participants", "per_page": "100"},
                "category": "Standings",
                "tier": "basic",
                "priority": "medium",
            },
        ]

        # HISTORICAL & ANALYTICAL DATA
        endpoints += [
            {
                "name": "Head-to-Head Sample",
                "url": f"{fb}/head2head/1/2",
                "params": {"include": "participants,scores,league,events.type", "per_page": "10"},
                "category": "Historical",
                "tier": "basic",
                "priority": "low",
            },
            {
                "name": "Players Active",
                "url": f"{fb}/players",
                "params": {"include": "team,position,statistics", "per_page": "100"},
                "category": "Players",
                "tier": "basic",
                "priority": "low",
            },
        ]

        # REFERENCE DATA
        endpoints += [
            {
                "name": "Countries",
                "url": f"{fb}/countries",
                "params": {"per_page": "250"},
                "category": "Reference",
                "tier": "basic",
                "priority": "low",
            },
            {
                "name": "Venues",
                "url": f"{fb}/venues",
                "params": {"include": "city,country", "per_page": "100"},
                "category": "Reference",
                "tier": "basic",
                "priority": "low",
            },
            {
                "name": "States/Statuses",
                "url": f"{fb}/states",
                "params": {"per_page": "100"},
                "category": "Reference",
                "tier": "basic",
                "priority": "low",
            },
        ]

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        endpoints.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))
        return endpoints

    # ------------------------------

    def test_single_endpoint(self, endpoint: Dict) -> EndpointResult:
        """Test single endpoint with comprehensive analysis"""
        url = endpoint["url"]
        params = endpoint.get("params", {})

        # Log attempt
        log_msg = f"Testing: {endpoint['name']} ({endpoint.get('tier', 'unknown')} tier)"
        self.testing_progress["detailed_log"].append(log_msg)
        logger.info(log_msg)

        # Make request
        status_code, response_data, response_time, error = self._enhanced_get_json(url, params)

        # Update progress counters
        if status_code == 200:
            self.testing_progress["success_count"] += 1
        else:
            self.testing_progress["errors_encountered"] += 1

        # Handle failures
        if error or status_code != 200:
            errors: List[str] = []
            recommendations: List[str] = []

            error_msg = error or f"HTTP {status_code}"

            if status_code == 403:
                error_msg += " - Access denied (subscription tier insufficient)"
                recommendations.append("🔒 Consider upgrading subscription or verify API permissions")
            elif status_code == 404:
                error_msg += " - Endpoint not found or deprecated"
                recommendations.append("📍 Check SportMonks API documentation for current endpoints")
            elif status_code == 422:
                error_msg += " - Invalid parameters or filters"
                recommendations.append("🔧 Verify parameter format - use filter[field]=value syntax")
            elif status_code == 429:
                error_msg += " - Rate limit exceeded"
                recommendations.append("⏱️ Implement request throttling or upgrade plan")
            elif status_code == 500:
                error_msg += " - Server error"
                recommendations.append("🔄 Retry later or contact SportMonks support")

            errors.append(error_msg)

            return EndpointResult(
                name=endpoint["name"],
                category=endpoint["category"],
                url=url,
                status_code=status_code,
                success=False,
                data_count=0,
                response_time=response_time,
                betting_value="none",
                data_quality=0,
                sample_data={},
                analysis={"error_details": error_msg},
                errors=errors,
                recommendations=recommendations,
                subscription_tier_required=endpoint.get("tier", "unknown"),
            )

        # Analyze successful response
        betting_value, quality_score, analysis, recommendations = self.analyze_response_data(response_data, endpoint)

        # Extract data info
        data_count = 0
        sample_data: Dict[str, Any] = {}

        if isinstance(response_data, dict) and "data" in response_data:
            data = response_data["data"]
            if isinstance(data, list):
                data_count = len(data)
                sample_data = data[0] if data else {}
            else:
                data_count = 1
                sample_data = data if isinstance(data, dict) else {}

        # Update discovered data
        self.update_discovered_data(response_data, endpoint)

        return EndpointResult(
            name=endpoint["name"],
            category=endpoint["category"],
            url=url,
            status_code=status_code,
            success=True,
            data_count=data_count,
            response_time=response_time,
            betting_value=betting_value,
            data_quality=quality_score,
            sample_data=sample_data,
            analysis=analysis,
            errors=[],
            recommendations=recommendations,
            subscription_tier_required=endpoint.get("tier", "basic"),
        )

    # ------------------------------

    def analyze_response_data(self, response_data: Dict, endpoint: Dict) -> Tuple[str, int, Dict, List[str]]:
        """Analyze response data for betting value and quality"""
        if not isinstance(response_data, dict) or "data" not in response_data:
            return "none", 0, {}, ["❌ Invalid response structure"]

        data = response_data["data"]
        if not data:
            return "none", 0, {}, ["⚠️ Empty dataset - may need specific filters"]

        # Get sample for analysis
        sample = data[0] if isinstance(data, list) and data else data
        if not isinstance(sample, dict):
            return "none", 0, {}, ["❌ Unexpected data format"]

        # Field analysis for betting value
        critical_betting = ["odds", "value", "decimal", "probability", "predictions", "expected_goals"]
        high_value = ["fixture_id", "bookmaker_id", "market_id", "starting_at", "participants", "scores"]
        medium_value = ["league_id", "team_id", "season_id", "events", "statistics", "form"]

        all_fields = self.extract_nested_fields(sample)

        found_critical = [f for f in critical_betting if any(f in field.lower() for field in all_fields)]
        found_high = [f for f in high_value if any(f in field.lower() for field in all_fields)]
        found_medium = [f for f in medium_value if any(f in field.lower() for field in all_fields)]

        # Quality scoring
        quality_score = 0
        quality_score += len(found_critical) * 35  # Critical fields most valuable
        quality_score += len(found_high) * 25
        quality_score += len(found_medium) * 15

        # Data volume bonus
        data_count = len(data) if isinstance(data, list) else 1
        quality_score += min(20, data_count)

        # Completeness bonus
        completeness = self.calculate_data_completeness(sample)
        quality_score += int(completeness * 10)

        quality_score = min(100, quality_score)

        # Betting value classification
        if len(found_critical) >= 3:
            betting_value = "critical"
        elif len(found_critical) >= 1:
            betting_value = "high"
        elif len(found_high) >= 3:
            betting_value = "medium"
        elif len(found_high) >= 1:
            betting_value = "low"
        else:
            betting_value = "none"

        # Generate recommendations
        recommendations: List[str] = []
        if found_critical:
            joined = " ".join(found_critical).lower()
            if "odds" in joined:
                recommendations.append("🎯 Live odds available - implement real-time betting")
            if "prediction" in joined:
                recommendations.append("🤖 AI predictions available - integrate ML models")

        if quality_score > 80:
            recommendations.append("🚀 Excellent data quality - build advanced strategies")
        elif quality_score > 60:
            recommendations.append("✅ Good data - suitable for production betting bot")
        elif quality_score > 30:
            recommendations.append("⚠️ Basic data - simple strategies only")
        else:
            recommendations.append("❌ Limited value - consider other endpoints")

        analysis = {
            "total_fields": len(all_fields),
            "critical_fields": found_critical,
            "high_value_fields": found_high,
            "medium_value_fields": found_medium,
            "data_completeness": round(completeness * 100, 1),
            "data_volume": data_count,
            "sample_structure": list(sample.keys())[:10],
        }

        return betting_value, quality_score, analysis, recommendations

    # ------------------------------

    def extract_nested_fields(self, obj: Any, prefix: str = "") -> List[str]:
        """Extract all field names from nested object structure"""
        fields: List[str] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_name = f"{prefix}.{key}" if prefix else key
                fields.append(field_name)
                if isinstance(value, (dict, list)) and len(str(value)) < 2000:
                    fields.extend(self.extract_nested_fields(value, field_name))
        elif isinstance(obj, list) and obj:
            fields.extend(self.extract_nested_fields(obj[0], f"{prefix}[0]"))
        return fields

    # ------------------------------

    def calculate_data_completeness(self, obj: Dict) -> float:
        """Calculate percentage of fields with meaningful values"""
        total = 0
        filled = 0
        for value in obj.values():
            total += 1
            if value is not None and value != "" and value != []:
                filled += 1
        return filled / max(total, 1)

    # ------------------------------

    def update_discovered_data(self, response_data: Dict, endpoint: Dict):
        """Update discovered IDs for cross-referencing"""
        if not isinstance(response_data, dict) or "data" not in response_data:
            return
        data = response_data["data"]
        items = data if isinstance(data, list) else [data]
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            if "id" in item:
                item_id = item["id"]
                category = endpoint["category"].lower()
                if category in ["fixtures", "live"] and item_id not in self.discovered_data["fixture_ids"]:
                    self.discovered_data["fixture_ids"].append(item_id)
                elif category == "teams" and item_id not in self.discovered_data["team_ids"]:
                    self.discovered_data["team_ids"].append(item_id)
                elif category == "leagues" and item_id not in self.discovered_data["league_ids"]:
                    self.discovered_data["league_ids"].append(item_id)
            for field_name in ["bookmaker_id", "market_id"]:
                if field_name in item:
                    lst_name = f"{field_name}s"
                    if item[field_name] not in self.discovered_data[lst_name]:
                        self.discovered_data[lst_name].append(item[field_name])

    # ==============================
    # ODDS CALCULATION METHODS
    # ==============================

    @staticmethod
    def implied_probability(decimal_odds: float) -> float:
        """Convert decimal odds to implied probability"""
        try:
            return 1.0 / float(decimal_odds) if decimal_odds and float(decimal_odds) > 1.0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def remove_overround(probabilities: List[float]) -> List[float]:
        """Remove bookmaker overround to get fair probabilities"""
        total = sum(probabilities)
        return [p / total for p in probabilities] if total > 0 else probabilities

    @staticmethod
    def kelly_criterion(fair_prob: float, decimal_odds: float, max_fraction: float = 0.25) -> float:
        """Calculate Kelly criterion bet size"""
        try:
            d = float(decimal_odds)
        except Exception:
            return 0.0
        if d <= 1:
            return 0.0
        kelly_fraction = (fair_prob * d - 1) / (d - 1)
        return max(0.0, min(kelly_fraction, max_fraction))

    def extract_1x2_odds(self, odds_data: List[Dict]) -> Dict[str, Any]:
        """Extract 1X2 odds from odds data"""
        best_odds = {"Home": None, "Draw": None, "Away": None}
        best_bookmakers = {"Home": None, "Draw": None, "Away": None}
        for row in odds_data:
            market_id = row.get("market_id")
            if market_id != 1:
                continue
            label = str(row.get("label") or row.get("name") or "").lower().strip()
            value = row.get("value")
            bookmaker_id = row.get("bookmaker_id")
            try:
                decimal_odds = float(value) if value is not None else None
            except Exception:
                continue
            if not decimal_odds:
                continue
            outcome = None
            if label in ("1", "home", "home win"):
                outcome = "Home"
            elif label in ("x", "draw", "tie"):
                outcome = "Draw"
            elif label in ("2", "away", "away win"):
                outcome = "Away"
            if outcome and (best_odds[outcome] is None or decimal_odds > best_odds[outcome]):
                best_odds[outcome] = decimal_odds
                best_bookmakers[outcome] = bookmaker_id
        return {"odds": best_odds, "bookmakers": best_bookmakers}

    def calculate_betting_edges(self, odds_data: List[Dict]) -> Dict[str, Any]:
        """Calculate betting edges and recommendations"""
        extraction = self.extract_1x2_odds(odds_data)
        odds = extraction["odds"]
        bookmakers = extraction["bookmakers"]
        if not all(odds.get(x) for x in ("Home", "Draw", "Away")):
            return {"selections": [], "best": None}
        home_odds, draw_odds, away_odds = odds["Home"], odds["Draw"], odds["Away"]
        implied = [
            self.implied_probability(home_odds),
            self.implied_probability(draw_odds),
            self.implied_probability(away_odds),
        ]
        fair = self.remove_overround(implied)
        overround = sum(implied) - 1.0
        outcomes = ["Home", "Draw", "Away"]
        selections: List[Dict[str, Any]] = []
        for i, outcome in enumerate(outcomes):
            current_odds = [home_odds, draw_odds, away_odds][i]
            fair_prob = fair[i]
            implied_prob = self.implied_probability(current_odds)
            edge = fair_prob - implied_prob
            kelly = self.kelly_criterion(fair_prob, current_odds)
            selections.append({
                "outcome": outcome,
                "odds": current_odds,
                "implied_prob": round(implied_prob, 4),
                "fair_prob": round(fair_prob, 4),
                "edge": round(edge, 4),
                "kelly_fraction": round(kelly, 4),
                "bookmaker_id": bookmakers[outcome],
                "recommended": edge > 0.02 and kelly > 0.01,
            })
        best_bet = max(selections, key=lambda x: x["edge"]) if selections else None
        return {
            "selections": selections,
            "best": best_bet,
            "overround": round(overround, 4),
            "market_efficiency": round(1 - overround, 4),
        }

    # ==============================
    # MAIN ANALYSIS RUNNER
    # ==============================

    def run_complete_analysis(self) -> Dict[str, Any]:
        """Run all endpoints and build a summary report."""
        endpoints = self.get_comprehensive_endpoints()
        self.testing_progress.update({
            "current": 0,
            "total": len(endpoints),
            "status": "running",
            "phase": "testing",
            "current_test": "",
            "errors_encountered": 0,
            "success_count": 0,
            "detailed_log": [],
        })
        self.test_results = []

        for i, ep in enumerate(endpoints, start=1):
            self.testing_progress["current"] = i
            self.testing_progress["current_test"] = ep["name"]
            try:
                result = self.test_single_endpoint(ep)
                self.test_results.append(result)
            except Exception as e:
                logger.exception(f"Endpoint failed: {ep['name']}")
                self.test_results.append(EndpointResult(
                    name=ep["name"],
                    category=ep.get("category", "Unknown"),
                    url=ep["url"],
                    status_code=0,
                    success=False,
                    data_count=0,
                    response_time=0.0,
                    betting_value="none",
                    data_quality=0,
                    sample_data={},
                    analysis={"error": str(e)},
                    errors=[str(e)],
                    recommendations=["Check logs and parameters"],
                    subscription_tier_required=ep.get("tier", "unknown")
                ))
                self.testing_progress["errors_encountered"] += 1

            # tiny polite delay to avoid hammering the API
            time.sleep(0.05)

        # Build executive summary
        total = len(self.test_results)
        successful = sum(1 for r in self.test_results if r.success)
        failed = total - successful
        success_rate = round((successful / total) * 100, 1) if total else 0.0

        # Determine readiness heuristically
        has_odds = any("odds" in (",".join((r.analysis.get("critical_fields") or []))).lower() for r in self.test_results)
        has_live = any(r.category.lower() == "live" and r.success for r in self.test_results)
        readiness = "sufficient" if (has_live and successful > failed) else "insufficient"

        self.complete_analysis = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total": total,
                "successful": successful,
                "failed": failed,
                "success_rate": success_rate,
            },
            "capabilities": {
                "odds_access": has_odds,
                "live_data": has_live,
            },
            "detailed_results": [asdict(r) for r in self.test_results],
        }

        self.testing_progress.update({"status": "done", "phase": "complete", "current_test": ""})
        return self.complete_analysis

    # ------------------------------

    def to_json_report(self) -> str:
        if not self.complete_analysis:
            self.run_complete_analysis()
        return json.dumps(self.complete_analysis, indent=2)

# ==============================
# Flask API (optional)
# ==============================

def create_app() -> Flask:
    app = Flask(__name__)
    if _HAS_CORS and CORS:
        CORS(app)

    api_token = os.getenv("SPORTMONKS_API_TOKEN") or "REPLACE_ME"
    analyzer = CompleteBettingAnalyzer(api_token=api_token)

    @app.route("/run", methods=["POST", "GET"])
    def run_analysis():
        def _run():
            analyzer.run_complete_analysis()

        # Run in the same thread unless you really want async
        _run()
        return jsonify(analyzer.complete_analysis)

    @app.route("/progress", methods=["GET"])
    def progress():
        return jsonify(analyzer.testing_progress)

    @app.route("/results", methods=["GET"])
    def results():
        return jsonify(analyzer.complete_analysis or {"message": "No results yet. POST /run first."})

    return app

# ==============================
# CLI
# ==============================

if __name__ == "__main__":
    mode = os.getenv("MODE", "server")  # "server" or "cli"
    if mode == "cli":
        token = os.getenv("SPORTMONKS_API_TOKEN") or "REPLACE_ME"
        analyzer = CompleteBettingAnalyzer(api_token=token)
        report = analyzer.run_complete_analysis()
        print(json.dumps(report, indent=2))
    else:
        port = int(os.getenv("PORT", "8080"))
        app = create_app()
        app.run(host="0.0.0.0", port=port)