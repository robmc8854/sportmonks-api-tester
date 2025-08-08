#!/usr/bin/env python3
"""
COMPLETE PROFESSIONAL SPORTMONKS BETTING BOT ANALYZER
- Tests a broad map of v3 endpoints (some may 403/404 on your plan—handled safely)
- Discovers today's fixtures & in-play matches
- Fetches per-fixture odds (markets 1=1X2, 80=Over/Under) from the correct odds service
- Computes fair probabilities, edges & Kelly (book-only baseline)
- Provides JSON report + helper endpoints for your front-end
"""

import io
import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, render_template, request, send_file

# Optional CORS: app runs fine even if this isn't installed.
try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    CORS = None
    _HAS_CORS = False


# ==============================
# Data Models
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


# ==============================
# Analyzer
# ==============================

class CompleteBettingAnalyzer:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_base_url = "https://api.sportmonks.com/v3/odds"

        self.session = requests.Session()
        # v3 supports api_token as a query param on all endpoints
        self.session.params = {"api_token": api_token}
        # Optional header auth: must be Bearer <token>
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        self.test_results: List[EndpointResult] = []
        self.discovered_data: Dict[str, List[Any]] = {
            "fixture_ids": [],
            "team_ids": [],
            "league_ids": [],
            "bookmaker_ids": [],
            "market_ids": [],
        }
        self.testing_progress = {
            "current": 0,
            "total": 0,
            "status": "idle",
            "current_test": "",
            "phase": "idle",
        }
        self.is_testing = False
        self.complete_analysis: Dict[str, Any] = {}

    # -----------------------
    # Endpoints to test (FULL MAP-ish; some are speculative and may 404)
    # -----------------------
    def get_all_endpoints(self) -> List[Dict]:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        fb = self.base_url
        ob = self.odds_base_url

        endpoints: List[Dict] = []

        # Live
        endpoints += [
            {"name": "Live Scores", "url": f"{fb}/livescores", "category": "Live"},
            {"name": "Live Scores In-play", "url": f"{fb}/livescores/inplay", "category": "Live"},
            {"name": "Live Latest Updates", "url": f"{fb}/livescores/latest", "category": "Live"},
        ]

        # Fixtures
        endpoints += [
            {"name": "All Fixtures", "url": f"{fb}/fixtures?per_page=50", "category": "Fixtures"},
            {"name": "Today's Fixtures", "url": f"{fb}/fixtures/date/{today}?include=participants,league,venue,state", "category": "Fixtures"},
            {"name": "Tomorrow's Fixtures", "url": f"{fb}/fixtures/date/{tomorrow}", "category": "Fixtures"},
            {"name": "Yesterday's Results", "url": f"{fb}/fixtures/date/{yesterday}", "category": "Fixtures"},
            {"name": "Fixtures Between Dates", "url": f"{fb}/fixtures/between/{today}/{tomorrow}", "category": "Fixtures"},
            {"name": "Latest Fixture Updates", "url": f"{fb}/fixtures/latest", "category": "Fixtures"},
            # Heavy includes (may be slow or plan-limited)
            {"name": "Fixtures With Rich Includes", "url": f"{fb}/fixtures/date/{today}?include=participants,league,venue,state,statistics,events,lineups,odds", "category": "Fixtures"},
        ]

        # Odds (correct service)
        endpoints += [
            {"name": "Pre-match Odds (All)", "url": f"{ob}/pre-match?per_page=100", "category": "Odds"},
            {"name": "In-play Odds (All)", "url": f"{ob}/inplay?per_page=100", "category": "Odds"},
            {"name": "Latest Pre-match Odds Updates", "url": f"{ob}/pre-match/latest?per_page=50", "category": "Odds"},
            {"name": "Markets", "url": f"{ob}/markets", "category": "Markets"},
            {"name": "Bookmakers", "url": f"{ob}/bookmakers", "category": "Bookmakers"},
        ]

        # Leagues / Seasons
        endpoints += [
            {"name": "Leagues", "url": f"{fb}/leagues?per_page=50", "category": "Leagues"},
            {"name": "Seasons", "url": f"{fb}/seasons?per_page=50", "category": "Seasons"},
        ]

        # Head-to-head sample (correct path)
        endpoints += [
            {"name": "Head2Head Example", "url": f"{fb}/head2head/1/2?per_page=5", "category": "Fixtures"},
        ]

        # Predictions (likely premium; expect 403)
        endpoints += [
            {"name": "Predictions: Probabilities", "url": f"{fb}/predictions/probabilities", "category": "Predictions"},
            {"name": "Predictions: Value Bets", "url": f"{fb}/predictions/valuebets", "category": "Predictions"},
        ]

        # Broad coverage (lower betting value but kept for completeness)
        endpoints += [
            {"name": "All Teams", "url": f"{fb}/teams?per_page=50", "category": "Teams"},
            {"name": "All Players", "url": f"{fb}/players?per_page=50", "category": "Players"},
            {"name": "All Venues", "url": f"{fb}/venues?per_page=50", "category": "Venues"},
            {"name": "All Referees", "url": f"{fb}/referees?per_page=50", "category": "Referees"},
            {"name": "All Coaches", "url": f"{fb}/coaches?per_page=50", "category": "Coaches"},
            {"name": "All Transfers", "url": f"{fb}/transfers?per_page=50", "category": "Transfers"},
            {"name": "All States", "url": f"{fb}/states?per_page=50", "category": "States"},
            {"name": "All Types", "url": f"{fb}/types?per_page=50", "category": "Types"},
            {"name": "Countries", "url": f"{fb}/countries?per_page=50", "category": "Geography"},
            {"name": "Continents", "url": f"{fb}/continents?per_page=50", "category": "Geography"},
            {"name": "Cities", "url": f"{fb}/cities?per_page=50", "category": "Geography"},
            {"name": "Regions", "url": f"{fb}/regions?per_page=50", "category": "Geography"},
            {"name": "Live Standings", "url": f"{fb}/standings/live", "category": "Standings"},
        ]

        # Speculative v3 paths (kept per your “full map” request; may 404)
        speculative = [
            {"name": "Topscorers by Season (spec)", "url": f"{fb}/topscorers/seasons/1", "category": "Topscorers"},
            {"name": "Schedules by Season (spec)", "url": f"{fb}/schedules/seasons/1", "category": "Schedules"},
            {"name": "TV Stations (spec)", "url": f"{fb}/tv-stations", "category": "TV"},
            {"name": "Expected Goals by Fixture (spec)", "url": f"{fb}/expected-goals/fixtures/1", "category": "xG"},
            {"name": "Rivals by Team (spec)", "url": f"{fb}/rivals/teams/1", "category": "Rivals"},
            {"name": "Player Statistics by Season (spec)", "url": f"{fb}/statistics/players/seasons/1", "category": "Statistics"},
            {"name": "Team Statistics by Season (spec)", "url": f"{fb}/statistics/teams/seasons/1", "category": "Statistics"},
        ]
        endpoints += speculative

        # Subscription info (if supported)
        endpoints += [
            {"name": "My Leagues", "url": f"{fb}/my/leagues", "category": "Subscription"},
            {"name": "My Resources", "url": f"{fb}/my/resources", "category": "Subscription"},
            {"name": "My Enrichments", "url": f"{fb}/my/enrichments", "category": "Subscription"},
        ]

        return endpoints

    # -----------------------
    # Helpers: odds math
    # -----------------------
    @staticmethod
    def _imp(odds: float) -> float:
        return 1.0 / float(odds) if odds and odds > 1.0 else 0.0

    @staticmethod
    def _de_overround(probs: List[float]) -> List[float]:
        s = sum(probs)
        return [p / s for p in probs] if s > 0 else probs

    @staticmethod
    def _kelly(p: float, b: float) -> float:
        if b <= 0:
            return 0.0
        f = (p * (b + 1) - 1) / b
        return max(0.0, f)

    def _extract_best_1x2_ou(self, odds_rows: List[Dict]) -> Dict[str, Any]:
        best_1x2 = {"Home": None, "Draw": None, "Away": None}
        best_1x2_bm = {"Home": None, "Draw": None, "Away": None}
        ou_over = None
        ou_under = None

        for o in odds_rows or []:
            market_id = o.get("market_id")
            label = (o.get("label") or o.get("name") or "").strip().lower()
            val = o.get("value")
            bm = o.get("bookmaker_id")
            try:
                dec = float(val) if val is not None else None
            except Exception:
                dec = None

            # Market 1 -> 1X2
            if market_id == 1 and dec:
                key = None
                if label in ("1", "home", "home win", "local", "localteam", "home team"):
                    key = "Home"
                elif label in ("x", "draw", "tie"):
                    key = "Draw"
                elif label in ("2", "away", "away win", "visitor", "visitorteam", "away team"):
                    key = "Away"
                elif "home" in label or "local" in label:
                    key = "Home"
                elif "away" in label or "visitor" in label:
                    key = "Away"
                elif "draw" in label:
                    key = "Draw"
                if key and (not best_1x2[key] or dec > best_1x2[key]):
                    best_1x2[key] = dec
                    best_1x2_bm[key] = bm

            # Market 80 -> Over/Under (try to pick 2.5 line if present)
            if market_id == 80 and dec:
                l2 = label.replace(" ", "")
                if ("over" in l2 or l2.startswith("o")) and ("25" in l2 or "2.5" in l2):
                    if not ou_over or dec > ou_over[0]:
                        ou_over = (dec, bm, "Over 2.5")
                if ("under" in l2 or l2.startswith("u")) and ("25" in l2 or "2.5" in l2):
                    if not ou_under or dec > ou_under[0]:
                        ou_under = (dec, bm, "Under 2.5")

        return {"best_1x2": best_1x2, "best_1x2_bm": best_1x2_bm, "ou_over": ou_over, "ou_under": ou_under}

    def compute_book_edges(self, odds_rows: List[Dict]) -> Dict[str, Any]:
        picks: List[Dict[str, Any]] = []
        ext = self._extract_best_1x2_ou(odds_rows)

        # 1X2
        b = ext["best_1x2"]
        bm = ext["best_1x2_bm"]
        if all(b.get(k) for k in ("Home", "Draw", "Away")):
            oH, oD, oA = b["Home"], b["Draw"], b["Away"]
            pH, pD, pA = self._imp(oH), self._imp(oD), self._imp(oA)
            fH, fD, fA = self._de_overround([pH, pD, pA])
            book_pct = (1.0 / oH + 1.0 / oD + 1.0 / oA) * 100.0

            for label, odds, fair_p, bid in [
                ("Home", oH, fH, bm.get("Home")),
                ("Draw", oD, fD, bm.get("Draw")),
                ("Away", oA, fA, bm.get("Away")),
            ]:
                edge = fair_p - self._imp(odds)
                k = self._kelly(fair_p, odds - 1.0) * 0.25 if edge > 0 else 0.0
                picks.append({
                    "market": "1X2",
                    "pick": label,
                    "odds": odds,
                    "implied_prob": round(self._imp(odds), 4),
                    "fair_prob": round(fair_p, 4),
                    "edge": round(edge, 4),
                    "kelly_fraction": round(k, 4),
                    "bookmaker_id": bid,
                    "book_percentage": round(book_pct, 2),
                })

        # O/U 2.5
        if ext["ou_over"] and ext["ou_under"]:
            oO, bmo, _ = ext["ou_over"]
            oU, bmu, _ = ext["ou_under"]
            pO, pU = self._imp(oO), self._imp(oU)
            fO, fU = self._de_overround([pO, pU])
            book_pct = (1.0 / oO + 1.0 / oU) * 100.0
            for label, odds, fair_p, bid in [("Over 2.5", oO, fO, bmo), ("Under 2.5", oU, fU, bmu)]:
                edge = fair_p - self._imp(odds)
                k = self._kelly(fair_p, odds - 1.0) * 0.25 if edge > 0 else 0.0
                picks.append({
                    "market": "O/U 2.5",
                    "pick": label,
                    "odds": odds,
                    "implied_prob": round(self._imp(odds), 4),
                    "fair_prob": round(fair_p, 4),
                    "edge": round(edge, 4),
                    "kelly_fraction": round(k, 4),
                    "bookmaker_id": bid,
                    "book_percentage": round(book_pct, 2),
                })

        best = max(picks, key=lambda x: x["edge"], default=None)
        return {"selections": picks, "best": best}

    # -----------------------
    # HTTP helpers + test runner
    # -----------------------
    def _get_json(self, url: str, timeout: int = 25) -> Tuple[int, Dict, float, Optional[str]]:
        start = time.time()
        try:
            r = self.session.get(url, timeout=timeout)
            elapsed = time.time() - start
            ctype = r.headers.get("content-type", "")
            if ctype.startswith("application/json"):
                return r.status_code, r.json(), elapsed, None
            return r.status_code, {}, elapsed, None
        except Exception as e:
            return 0, {}, time.time() - start, str(e)[:200]

    def analyze_endpoint_data(self, response_data: Dict, endpoint: Dict) -> Tuple[str, int, Dict, List[str]]:
        betting_value = "none"
        quality_score = 0
        analysis: Dict[str, Any] = {}
        recommendations: List[str] = []

        if not isinstance(response_data, dict) or "data" not in response_data:
            return betting_value, quality_score, analysis, ["❌ Invalid response structure"]

        data = response_data["data"]
        if not data:
            return betting_value, quality_score, analysis, ["⚠️ Empty dataset"]

        sample = data[0] if isinstance(data, list) and data else data
        if not isinstance(sample, dict):
            return betting_value, quality_score, analysis, ["❌ Unexpected data format"]

        # Discovery
        self._update_discovered(data, endpoint)

        # Heuristic scoring for betting usefulness
        critical_fields = ["odds", "predictions", "probabilities", "value", "bookmaker_id", "market_id"]
        high_value_fields = ["fixture_id", "starting_at", "scores", "statistics", "participants"]
        medium_value_fields = ["league_id", "team_id", "events", "lineup", "form"]

        found_critical = [f for f in critical_fields if f in sample]
        found_high = [f for f in high_value_fields if f in sample]
        found_medium = [f for f in medium_value_fields if f in sample]

        quality_score = (len(found_critical) * 25) + (len(found_high) * 15) + (len(found_medium) * 8)
        if isinstance(data, list):
            quality_score += min(20, len(data))
        quality_score = min(100, quality_score)

        if len(found_critical) >= 2:
            betting_value = "critical"
        elif len(found_critical) >= 1:
            betting_value = "high"
        elif len(found_high) >= 2:
            betting_value = "medium"
        elif len(found_high) >= 1:
            betting_value = "low"

        analysis = {
            "total_fields": len(sample),
            "critical_betting_fields": found_critical,
            "high_value_fields": found_high,
            "medium_value_fields": found_medium,
            "data_completeness": len(sample) / max(len(critical_fields + high_value_fields), 1) * 100,
            "nested_complexity": sum(1 for v in sample.values() if isinstance(v, (dict, list))),
        }

        if found_critical:
            if "odds" in found_critical or "value" in found_critical:
                recommendations.append("🎯 Odds present — core betting possible.")
            if "predictions" in found_critical or "probabilities" in found_critical:
                recommendations.append("🤖 Predictions present — AI logic possible.")

        if endpoint["category"] == "Odds" and not found_critical and "value" not in sample:
            recommendations.append("❌ PROBLEM: Odds-like endpoint missing price fields.")

        if quality_score > 70:
            recommendations.append("🚀 High-quality data — implement advanced features.")
        elif quality_score > 40:
            recommendations.append("✅ Good data — suitable for bot foundation.")
        else:
            recommendations.append("⚠️ Limited data — simple strategies only.")

        return betting_value, quality_score, analysis, recommendations

    def _update_discovered(self, data: Any, endpoint: Dict):
        items = data if isinstance(data, list) else [data]
        for item in items[:50]:
            if not isinstance(item, dict):
                continue
            if "id" in item:
                if endpoint["category"] in ["Fixtures", "Live"] and item["id"] not in self.discovered_data["fixture_ids"]:
                    self.discovered_data["fixture_ids"].append(item["id"])
                elif endpoint["category"] == "Leagues" and item["id"] not in self.discovered_data["league_ids"]:
                    self.discovered_data["league_ids"].append(item["id"])
            if "bookmaker_id" in item and item["bookmaker_id"] not in self.discovered_data["bookmaker_ids"]:
                self.discovered_data["bookmaker_ids"].append(item["bookmaker_id"])
            if "market_id" in item and item["market_id"] not in self.discovered_data["market_ids"]:
                self.discovered_data["market_ids"].append(item["market_id"])

    def test_single_endpoint(self, endpoint: Dict) -> EndpointResult:
        status_code, response_data, response_time, err = self._get_json(endpoint["url"])

        if err or status_code != 200:
            error_msg = err or f"HTTP {status_code}"
            if status_code == 403:
                error_msg += " (access denied/premium)"
            elif status_code == 404:
                error_msg += " (not found)"
            elif status_code == 429:
                error_msg += " (rate limit)"
            return EndpointResult(
                name=endpoint["name"],
                category=endpoint["category"],
                url=endpoint["url"],
                status_code=status_code,
                success=False,
                data_count=0,
                response_time=response_time,
                betting_value="none",
                data_quality=0,
                sample_data={},
                analysis={},
                errors=[error_msg],
                recommendations=[],
            )

        betting_value, quality_score, analysis, recs = self.analyze_endpoint_data(response_data, endpoint)

        data_count = 0
        sample_data = {}
        if "data" in response_data:
            data = response_data["data"]
            if isinstance(data, list):
                data_count = len(data)
                sample_data = data[0] if data else {}
            else:
                data_count = 1
                sample_data = data

        return EndpointResult(
            name=endpoint["name"],
            category=endpoint["category"],
            url=endpoint["url"],
            status_code=status_code,
            success=True,
            data_count=data_count,
            response_time=response_time,
            betting_value=betting_value,
            data_quality=quality_score,
            sample_data=sample_data,
            analysis=analysis,
            recommendations=recs,
        )

    # -----------------------
    # Fetchers used by routes
    # -----------------------
    def fetch_odds_for_fixture(self, fixture_id: int, markets: str = "1,80") -> Dict[str, Any]:
        url = f"{self.odds_base_url}/pre-match?filter[fixture_id]={fixture_id}&markets={markets}&per_page=200"
        status, body, _, _ = self._get_json(url)
        return {"status": status, "body": body if isinstance(body, dict) else {}, "url": url}

    def fetch_inplay_context(self) -> Dict[str, Any]:
        s_live, live, _, _ = self._get_json(f"{self.base_url}/livescores/inplay")
        stitched = []
        if s_live == 200 and isinstance(live, dict):
            for fx in (live.get("data") or []):
                fid = fx.get("id")
                if not fid:
                    continue
                s_od, od, _, _ = self._get_json(f"{self.odds_base_url}/inplay?filter[fixture_id]={fid}&per_page=200")
                stitched.append({
                    "fixture": fx,
                    "odds": (od.get("data") or []) if s_od == 200 and isinstance(od, dict) else [],
                })
        return {"data": stitched}

    # -----------------------
    # Orchestration
    # -----------------------
    def run_complete_analysis(self):
        self.is_testing = True
        self.test_results = []
        endpoints = self.get_all_endpoints()
        self.testing_progress = {
            "current": 0,
            "total": len(endpoints),
            "status": "running",
            "current_test": "Starting comprehensive analysis...",
            "phase": "testing",
        }

        try:
            for i, endpoint in enumerate(endpoints):
                if not self.is_testing:
                    break
                self.testing_progress.update({
                    "current": i + 1,
                    "current_test": f"Testing {endpoint['name']}",
                    "phase": "testing",
                })
                res = self.test_single_endpoint(endpoint)
                self.test_results.append(res)
                time.sleep(0.1)

            # Build final analysis
            self.testing_progress.update({
                "phase": "analyzing",
                "current_test": "Generating betting bot analysis...",
            })
            self.generate_complete_analysis()
            self.testing_progress["status"] = "completed"

        except Exception as e:
            self.testing_progress["status"] = f"error: {str(e)[:180]}"
        finally:
            self.is_testing = False

    def generate_complete_analysis(self):
        successful = [r for r in self.test_results if r.success]
        failed = [r for r in self.test_results if not r.success]

        critical_sources = [r for r in successful if r.betting_value == "critical"]
        high_value_sources = [r for r in successful if r.betting_value == "high"]

        total_quality = sum(r.data_quality for r in successful)
        max_possible = len(self.test_results) * 100
        overall_score = (total_quality / max_possible * 100) if max_possible > 0 else 0.0

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
            "odds_access": any(("odds" in r.name.lower()) and r.success for r in self.test_results),
            "predictions_access": any(("prediction" in r.name.lower()) and r.success for r in self.test_results),
            "live_data": any(("live" in r.name.lower()) and r.success for r in self.test_results),
            "fixture_data": any(("fixture" in r.name.lower()) and r.success for r in self.test_results),
            "bookmaker_data": any(("bookmaker" in r.name.lower()) and r.success for r in self.test_results),
            "market_data": any(("market" in r.name.lower()) and r.success for r in self.test_results),
        }

        self.complete_analysis = {
            "executive_summary": {
                "overall_readiness": readiness,
                "readiness_level": readiness_level,
                "feasibility_score": round(overall_score, 1),
                "total_endpoints": len(self.test_results),
                "successful_endpoints": len(successful),
                "critical_sources": len(critical_sources),
                "high_value_sources": len(high_value_sources),
                "total_data_items": sum(r.data_count for r in successful),
            },
            "capabilities": capabilities,
            "data_sources": {
                "critical": [{"name": r.name, "category": r.category, "data_count": r.data_count, "quality": r.data_quality} for r in critical_sources],
                "high_value": [{"name": r.name, "category": r.category, "data_count": r.data_count} for r in high_value_sources],
                "failed_critical": [{"name": r.name, "error": r.errors[0] if r.errors else "Unknown"} for r in failed if r.category in ["Odds", "Predictions"]],
            },
            "discovered_data": {
                "fixtures": len(self.discovered_data["fixture_ids"]),
                "teams": len(self.discovered_data["team_ids"]),
                "bookmakers": len(self.discovered_data["bookmaker_ids"]),
                "markets": len(self.discovered_data["market_ids"]),
                "sample_fixture_ids": self.discovered_data["fixture_ids"][:20],
            },
            "detailed_results": [asdict(r) for r in self.test_results],
        }

    def get_summary_stats(self) -> Dict:
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


# ==============================
# Flask App
# ==============================

app = Flask(__name__)
if _HAS_CORS:
    CORS(app, resources={r"/api/*": {"origins": "*"}})

analyzer: Optional[CompleteBettingAnalyzer] = None


@app.route("/")
def home():
    # Your existing templates/index.html UI
    return render_template("index.html")


@app.route("/api/start-analysis", methods=["POST"])
def start_analysis():
    global analyzer
    data = request.get_json(silent=True) or {}
    api_token = (data.get("api_token") or "").strip()
    if not api_token:
        return jsonify({"error": "API token required"}), 400
    if analyzer and analyzer.is_testing:
        return jsonify({"error": "Analysis already running"}), 400
    try:
        analyzer = CompleteBettingAnalyzer(api_token)
        thread = threading.Thread(target=analyzer.run_complete_analysis, daemon=True)
        thread.start()
        return jsonify({"success": True, "message": "Complete analysis started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/progress")
def get_progress():
    if not analyzer:
        return jsonify({"progress": {"current": 0, "total": 0, "status": "idle", "current_test": "", "phase": "idle"}})
    return jsonify({"progress": analyzer.testing_progress})


@app.route("/api/results")
def get_results():
    if not analyzer:
        return jsonify({"error": "No analyzer available"}), 400
    if not analyzer.complete_analysis:
        return jsonify({"error": "Analysis not complete"}), 400
    return jsonify({
        "summary": analyzer.get_summary_stats(),
        "analysis": analyzer.complete_analysis
    })


@app.route("/api/download-report")
def download_report():
    if not analyzer or not analyzer.complete_analysis:
        return jsonify({"error": "No analysis available"}), 400

    report_data = {
        "timestamp": datetime.now().isoformat(),
        "summary": analyzer.get_summary_stats(),
        "complete_analysis": analyzer.complete_analysis,
        "raw_results": [asdict(r) for r in analyzer.test_results]
    }

    report_json = json.dumps(report_data, indent=2, default=str)
    buffer = io.BytesIO(report_json.encode("utf-8"))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name=f'betting_bot_complete_analysis_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    )


# ---------- Helper routes for your UI ----------

@app.route("/api/fixtures/today")
def fixtures_today():
    if not analyzer:
        return jsonify({"error": "No analyzer"}), 400
    day = datetime.utcnow().strftime("%Y-%m-%d")
    status, body, _, _ = analyzer._get_json(f"{analyzer.base_url}/fixtures/date/{day}?include=participants,league,venue,state")
    return jsonify(body if isinstance(body, dict) else {"data": []}), (status or 200)


@app.route("/api/inplay/context")
def inplay_context():
    if not analyzer:
        return jsonify({"error": "No analyzer"}), 400
    return jsonify(analyzer.fetch_inplay_context())


@app.route("/api/fixture/<int:fixture_id>/odds")
def fixture_odds(fixture_id: int):
    if not analyzer:
        return jsonify({"error": "No analyzer"}), 400
    res = analyzer.fetch_odds_for_fixture(fixture_id)
    rows = res["body"].get("data") or []
    edges = analyzer.compute_book_edges(rows) if rows else {"selections": [], "best": None}
    payload = {
        "fixture_id": fixture_id,
        "source": res["url"],
        "row_count": len(rows),
        "edges": edges
    }
    return jsonify(payload), (res["status"] or 200)


@app.route("/health")
def health_check():
    status = analyzer.testing_progress["status"] if analyzer else "idle"
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat(), "testing_status": status})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)