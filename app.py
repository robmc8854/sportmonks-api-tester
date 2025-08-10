Here you go — full corrected script with the JSON-safe serializers and a cleaned param formatter (so you won’t hit the str.format() duplicate-key error). Logic and flow are unchanged.

#!/usr/bin/env python3
"""
COMPLETE SPORTMONKS SUBSCRIPTION ANALYZER - ALL COMPONENTS MAPPED

Based on your extensive dashboard components, this analyzer will test and map:
✅ Core Data (Fixtures, Livescores, Leagues, Teams, Players)
✅ Odds & Predictions (Pre-match, Live, Bookmakers, Markets, AI Predictions)
✅ Advanced Analytics (xG, Pressure Index, Trends, Player Efficiency)
✅ Statistics (Match Centre, Team Stats, Player Profiles, Head2Head)
✅ Real-time Data (Live Standings, Events Timeline, Commentaries)
✅ Supplementary Data (Injuries, Referees, TV Stations, News)

This will generate a comprehensive data inventory for building an advanced AI betting bot.
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
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ComponentCapability:
    component_name: str
    endpoint_url: str
    category: str
    accessible: bool
    data_count: int
    sample_data: Dict
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


# -------- Endpoint registry spec --------
@dataclass
class EndpointSpec:
    name: str
    url_template: str                  # e.g. "/fixtures/{fixture_id}?include=participants"
    category: str                      # "core" | "betting" | "analytics" | ...
    params: Optional[Dict] = None      # default query params
    ai_potential: str = "medium"


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
        self.analysis_progress = {
            "phase": "idle",
            "current_test": "",
            "progress": 0,
            "total_phases": 12,
            "detailed_log": [],
            "errors": []
        }
        self.is_analyzing = False

        # Discovered IDs + endpoint registry
        self.discovered_ids: Dict[str, Any] = {}
        self.endpoint_registry: List[EndpointSpec] = self._build_endpoint_registry()

    # ---------- Robust request w/ gentle retry ----------
    def _api_request(self, url: str, params: Dict = None) -> Tuple[int, Dict, str]:
        """Enhanced API request with comprehensive logging"""
        try:
            request_params = {"api_token": self.api_token}
            if params:
                request_params.update(params)

            resp = None
            for attempt in range(3):
                resp = self.session.get(url, params=request_params, timeout=30)
                if resp.status_code != 429:
                    break
                time.sleep(1.5 * (attempt + 1))

            status_code = resp.status_code if resp is not None else 0
            text_preview = (resp.text[:200] if (resp is not None and resp.text) else "")
            log_entry = f"[{status_code}] {url}"
            if status_code != 200:
                log_entry += f" - {text_preview}"

            self.analysis_progress["detailed_log"].append(log_entry)

            try:
                data = resp.json() if (resp is not None and resp.text) else {}
            except Exception:
                data = {}

            return status_code, data, ""

        except Exception as e:
            error_msg = f"Request failed: {str(e)[:200]}"
            self.analysis_progress["errors"].append(error_msg)
            return 0, {}, error_msg

    # ---------- Component tester ----------
    def test_component(
        self,
        component_name: str,
        endpoint_url: str,
        category: str,
        params: Dict = None,
        ai_potential: str = "medium"
    ) -> ComponentCapability:
        """Test individual component capability"""
        status, data, error = self._api_request(endpoint_url, params or {"per_page": "25"})

        data_count = 0
        sample_data = {}
        api_features: List[str] = []

        if status == 200:
            if isinstance(data, dict) and "data" in data:
                data_items = data["data"]
                if isinstance(data_items, list):
                    data_count = len(data_items)
                    sample_data = data_items[0] if data_items else {}
                else:
                    data_count = 1
                    sample_data = data_items if isinstance(data_items, dict) else {}

                # Analyze API features from sample data
                if sample_data:
                    api_features = list(sample_data.keys())[:10]  # Top 10 fields

        return ComponentCapability(
            component_name=component_name,
            endpoint_url=endpoint_url,
            category=category,
            accessible=(status == 200),
            data_count=data_count,
            sample_data=sample_data,
            api_features=api_features,
            betting_value="high" if "odds" in component_name.lower() or "prediction" in component_name.lower() else "medium",
            ai_potential=ai_potential
        )

    # ---------- Endpoint registry builder ----------
    def _build_endpoint_registry(self) -> List[EndpointSpec]:
        b, o = self.base_url, self.odds_url
        return [
            # Core discovery
            EndpointSpec("Leagues", f"{b}/leagues", "core", {"per_page": "200", "include": "country,seasons.current"}, "high"),
            EndpointSpec("Seasons", f"{b}/seasons", "core", {"per_page": "200"}),
            EndpointSpec("Teams", f"{b}/teams", "core", {"per_page": "200"}, "high"),
            EndpointSpec("Players", f"{b}/players", "core", {"per_page": "200"}),
            EndpointSpec("Standings", f"{b}/standings", "statistics"),
            EndpointSpec("Livescores", f"{b}/livescores", "core", None, "high"),
            EndpointSpec("Livescores Inplay", f"{b}/livescores/inplay", "core", None, "high"),
            EndpointSpec("Fixtures Today", f"{b}/fixtures/date/{{today}}", "core"),
            EndpointSpec("Fixtures Tomorrow", f"{b}/fixtures/date/{{tomorrow}}", "core"),
            EndpointSpec("Fixtures Between", f"{b}/fixtures/between/{{from_date}}/{{to_date}}", "core"),

            # By ID
            EndpointSpec("League by ID", f"{b}/leagues/{{league_id}}", "core", {"include": "country,seasons.current"}),
            EndpointSpec("Season by ID", f"{b}/seasons/{{season_id}}", "core", {"include": "rounds,stages"}),
            EndpointSpec("Round by ID (basic)", f"{b}/rounds/{{round_id}}", "core", {"include": "fixtures.participants;fixtures.league;league.country"}),
            EndpointSpec("Round by ID (odds filtered)", f"{b}/rounds/{{round_id}}", "betting",
                         {"include": "fixtures.odds.market;fixtures.odds.bookmaker;fixtures.participants;league.country",
                          "filters": "markets:1;bookmakers:2"}, "high"),
            EndpointSpec("Team by ID", f"{b}/teams/{{team_id}}", "statistics", {"include": "statistics,squad,venue"}, "high"),
            EndpointSpec("Player by ID", f"{b}/players/{{player_id}}", "statistics", {"include": "statistics,team"}),
            EndpointSpec("Fixture by ID (rich)", f"{b}/fixtures/{{fixture_id}}", "core",
                         {"include": "participants,league,venue,state,scores,events.type,events.player,statistics,lineups,odds.market,odds.bookmaker"}, "high"),

            # Odds
            EndpointSpec("Bookmakers", f"{o}/bookmakers", "betting", None, "high"),
            EndpointSpec("Markets", f"{o}/markets", "betting", None, "high"),
            EndpointSpec("Pre-match Odds (global)", f"{o}/pre-match", "betting", {"per_page": "100"}, "high"),
            EndpointSpec("Live Odds (inplay)", f"{o}/inplay", "betting", {"per_page": "100"}, "high"),
            EndpointSpec("Pre-match Odds by Fixture", f"{o}/pre-match", "betting",
                         {"per_page": "50", "filter[fixture_id]": "{fixture_id}", "include": "fixture,bookmaker,market"}, "high"),

            # Advanced / Optional
            EndpointSpec("Head-to-Head", f"{b}/head2head/{{team_id_a}}/{{team_id_b}}", "statistics", {"per_page": "25"}, "high"),
            EndpointSpec("Live Standings", f"{b}/standings/live", "realtime"),
            EndpointSpec("Expected Goals (fixture)", f"{b}/expected-goals/fixtures/{{fixture_id}}", "analytics", None, "high"),
            EndpointSpec("Predictions (probabilities)", f"{b}/predictions/probabilities", "ai", None, "high"),

            # Supplementary
            EndpointSpec("Referees", f"{b}/referees", "supplementary", {"per_page": "200"}),
            EndpointSpec("Injuries", f"{b}/injuries", "supplementary", {"per_page": "200"}),
            EndpointSpec("TV Stations", f"{b}/tv-stations", "supplementary", {"per_page": "200"}),
        ]

    # ---------- Seed ID discovery ----------
    def _discover_seed_ids(self) -> None:
        """Populate self.discovered_ids with a small, real set of IDs for later endpoint tests."""
        self.discovered_ids = {}
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        self.discovered_ids.update({
            "today": today, "tomorrow": tomorrow,
            "from_date": from_date, "to_date": to_date
        })

        # Leagues -> Seasons
        _, leagues_json, _ = self._api_request(f"{self.base_url}/leagues", {"per_page": "50", "include": "seasons"})
        leagues = leagues_json.get("data", []) if isinstance(leagues_json, dict) else []
        if leagues:
            lg = leagues[0]
            self.discovered_ids["league_id"] = lg.get("id")
            seasons = lg.get("seasons") or []
            if seasons:
                self.discovered_ids["season_id"] = seasons[0].get("id")

        # Rounds from season
        if self.discovered_ids.get("season_id"):
            _, s_json, _ = self._api_request(f"{self.base_url}/seasons/{self.discovered_ids['season_id']}", {"include": "rounds"})
            rounds = (s_json.get("data", {}) or {}).get("rounds") or []
            if rounds:
                self.discovered_ids["round_id"] = rounds[0].get("id")

        # Fixtures today or between
        _, fixtures_today_json, _ = self._api_request(f"{self.base_url}/fixtures/date/{today}")
        fixtures = fixtures_today_json.get("data", []) if isinstance(fixtures_today_json, dict) else []
        if not fixtures:
            _, fx_json, _ = self._api_request(f"{self.base_url}/fixtures/between/{from_date}/{to_date}")
            fixtures = fx_json.get("data", []) if isinstance(fx_json, dict) else []

        if fixtures:
            fx = fixtures[0]
            self.discovered_ids["fixture_id"] = fx.get("id")
            parts = fx.get("participants") or []
            if len(parts) >= 2:
                self.discovered_ids["team_id"] = parts[0].get("id")
                self.discovered_ids["team_id_a"] = parts[0].get("id")
                self.discovered_ids["team_id_b"] = parts[1].get("id")

        # Teams fallback
        if "team_id" not in self.discovered_ids:
            _, teams_json, _ = self._api_request(f"{self.base_url}/teams", {"per_page": "50"})
            teams = teams_json.get("data", []) if isinstance(teams_json, dict) else []
            if teams:
                self.discovered_ids["team_id"] = teams[0].get("id")
                if len(teams) >= 2:
                    self.discovered_ids["team_id_a"] = teams[0].get("id")
                    self.discovered_ids["team_id_b"] = teams[1].get("id")

        # Players
        _, players_json, _ = self._api_request(f"{self.base_url}/players", {"per_page": "50"})
        players = players_json.get("data", []) if isinstance(players_json, dict) else []
        if players:
            self.discovered_ids["player_id"] = players[0].get("id")

    # ---------- Template formatter ----------
    def _format(self, template: str) -> str:
        """Fill {placeholders} in url_template using discovered_ids + dates."""
        vals = dict(self.discovered_ids)  # copy discovered values
        # Ensure date keys exist if missing
        vals.setdefault("today", datetime.utcnow().strftime("%Y-%m-%d"))
        vals.setdefault("tomorrow", (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"))
        vals.setdefault("from_date", datetime.utcnow().strftime("%Y-%m-%d"))
        vals.setdefault("to_date", datetime.utcnow().strftime("%Y-%m-%d"))
        try:
            return template.format(**vals)
        except KeyError:
            return template

    # ---------- Param expander (fixed to avoid duplicate keys) ----------
    def _expand_params(self, params: Optional[Dict]) -> Optional[Dict]:
        if not params:
            return None
        out: Dict[str, Any] = {}

        # Build a single dict of format values (no duplicates)
        vals = dict(self.discovered_ids)
        vals.setdefault("today", datetime.utcnow().strftime("%Y-%m-%d"))
        vals.setdefault("tomorrow", (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"))
        vals.setdefault("from_date", datetime.utcnow().strftime("%Y-%m-%d"))
        vals.setdefault("to_date", datetime.utcnow().strftime("%Y-%m-%d"))

        for k, v in params.items():
            if isinstance(v, str):
                try:
                    out[k] = v.format(**vals)
                except KeyError:
                    out[k] = v
            else:
                out[k] = v
        return out

    # ---------- Registry runner ----------
    def run_endpoint_registry(self):
        """Iterate endpoint registry, call each endpoint, and record what works."""
        self._discover_seed_ids()

        for spec in self.endpoint_registry:
            url = self._format(spec.url_template)
            params = self._expand_params(spec.params)

            status, data, _ = self._api_request(url, params or {"per_page": "25"})
            data_count = 0
            sample = {}
            if status == 200 and isinstance(data, dict):
                d = data.get("data")
                if isinstance(d, list):
                    data_count = len(d)
                    sample = d[0] if d else {}
                elif isinstance(d, dict):
                    data_count = 1
                    sample = d
                else:
                    sample = data

            cap = ComponentCapability(
                component_name=spec.name,
                endpoint_url=url,
                category=spec.category,
                accessible=(status == 200),
                data_count=data_count,
                sample_data=sample if isinstance(sample, dict) else {},
                api_features=(list(sample.keys())[:10] if isinstance(sample, dict) else []),
                betting_value="high" if spec.category in ("betting", "ai") else "medium",
                ai_potential=spec.ai_potential
            )

            if cap.accessible:
                self.inventory.working_components.append(cap)
                # lightweight counters for key areas
                if spec.name == "Bookmakers":
                    self.inventory.bookmakers_count = data_count
                if spec.name == "Markets":
                    self.inventory.betting_markets_count = data_count
                if spec.name.startswith("Pre-match Odds"):
                    self.inventory.pre_match_odds_count = max(self.inventory.pre_match_odds_count, data_count)
                if spec.name.startswith("Live Odds"):
                    self.inventory.live_odds_count = max(self.inventory.live_odds_count, data_count)
                if spec.name in ("Livescores", "Livescores Inplay"):
                    self.inventory.live_matches = max(self.inventory.live_matches, data_count)
                if spec.name == "Fixture by ID (rich)":
                    self.inventory.events_timeline_available = True
                    self.inventory.lineup_data_available = True
            else:
                self.inventory.failed_components.append(cap)

    # ---------- Original phases ----------
    def phase_1_authentication_test(self):
        """Phase 1: Test API authentication"""
        self.analysis_progress.update({
            "phase": "authentication",
            "current_test": "Testing API authentication...",
            "progress": 1
        })

        status, data, error = self._api_request(f"{self.core_url}/my/subscription")

        if status == 200:
            self.inventory.api_authenticated = True
            subscription_data = data.get("data", {})
            self.inventory.subscription_tier = subscription_data.get("tier", "Standard+")
        else:
            # Fallback test
            status, data, error = self._api_request(f"{self.base_url}/livescores")
            self.inventory.api_authenticated = (status == 200)

    def phase_2_core_football_data(self):
        """Phase 2: Test core football data components"""
        self.analysis_progress.update({
            "phase": "core_data",
            "current_test": "Testing core football data...",
            "progress": 2
        })

        # Leagues
        comp = self.test_component("Leagues", f"{self.base_url}/leagues", "core",
                                   {"per_page": "200"}, "high")
        if comp.accessible:
            self.inventory.leagues_available = comp.data_count
            self.inventory.working_components.append(comp)
        else:
            self.inventory.failed_components.append(comp)

        # Teams
        comp = self.test_component("Teams", f"{self.base_url}/teams", "core",
                                   {"per_page": "200"}, "high")
        if comp.accessible:
            self.inventory.teams_available = comp.data_count
            self.inventory.working_components.append(comp)
        else:
            self.inventory.failed_components.append(comp)

        # Players
        comp = self.test_component("Players", f"{self.base_url}/players", "core",
                                   {"per_page": "200"}, "medium")
        if comp.accessible:
            self.inventory.players_available = comp.data_count
            self.inventory.working_components.append(comp)
        else:
            self.inventory.failed_components.append(comp)

        # Fixtures
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        comp = self.test_component("Today's Fixtures", f"{self.base_url}/fixtures/date/{today}", "core", ai_potential="high")
        if comp.accessible:
            self.inventory.fixtures_today = comp.data_count
            self.inventory.working_components.append(comp)

        comp = self.test_component("Tomorrow's Fixtures", f"{self.base_url}/fixtures/date/{tomorrow}", "core", ai_potential="high")
        if comp.accessible:
            self.inventory.fixtures_tomorrow = comp.data_count
            self.inventory.working_components.append(comp)

        # Live Scores
        comp = self.test_component("Live Scores", f"{self.base_url}/livescores", "core", ai_potential="high")
        if comp.accessible:
            self.inventory.live_matches = comp.data_count
            self.inventory.working_components.append(comp)

    def phase_3_odds_and_predictions(self):
        """Phase 3: Test odds and prediction components"""
        self.analysis_progress.update({
            "phase": "odds_predictions",
            "current_test": "Testing odds and prediction components...",
            "progress": 3
        })

        # Bookmakers
        comp = self.test_component("Bookmakers", f"{self.odds_url}/bookmakers", "betting", ai_potential="high")
        if comp.accessible:
            self.inventory.bookmakers_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Bookmakers Data")

        # Markets
        comp = self.test_component("Betting Markets", f"{self.odds_url}/markets", "betting", ai_potential="high")
        if comp.accessible:
            self.inventory.betting_markets_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Betting Markets")

        # Pre-match Odds
        comp = self.test_component("Pre-match Odds", f"{self.odds_url}/pre-match", "betting",
                                   {"per_page": "100"}, "high")
        if comp.accessible:
            self.inventory.pre_match_odds_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Pre-match Odds")

        # Live Odds
        comp = self.test_component("Live Odds", f"{self.odds_url}/inplay", "betting",
                                   {"per_page": "100"}, "high")
        if comp.accessible:
            self.inventory.live_odds_count = comp.data_count
            self.inventory.working_components.append(comp)
            self.inventory.high_value_components.append("Live Odds")

        # Predictions
        comp = self.test_component("AI Predictions", f"{self.base_url}/predictions", "ai", ai_potential="high")
        if comp.accessible:
            self.inventory.predictions_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("AI Match Predictions")

    def phase_4_advanced_analytics(self):
        """Phase 4: Test advanced analytics components"""
        self.analysis_progress.update({
            "phase": "advanced_analytics",
            "current_test": "Testing advanced analytics (xG, Pressure Index)...",
            "progress": 4
        })

        # Expected Goals (xG) - Match level
        comp = self.test_component("Expected Goals (xG)", f"{self.base_url}/fixtures", "analytics",
                                   {"include": "xg", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.xg_match_data_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Expected Goals (xG) Analysis")

        # Player xG Efficiency (if available through player stats)
        comp = self.test_component("Player xG Efficiency", f"{self.base_url}/players", "analytics",
                                   {"include": "statistics", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.xg_player_efficiency_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Player xG Efficiency")

        # Pressure Index (usually in fixture statistics)
        comp = self.test_component("Pressure Index", f"{self.base_url}/fixtures", "analytics",
                                   {"include": "pressureIndex", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.pressure_index_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Pressure Index Analytics")

        # Trends
        comp = self.test_component("Team Trends", f"{self.base_url}/teams", "analytics",
                                   {"include": "trends", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.trends_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Team Performance Trends")

    def phase_5_statistics_components(self):
        """Phase 5: Test statistics and analysis components"""
        self.analysis_progress.update({
            "phase": "statistics",
            "current_test": "Testing statistics and analysis components...",
            "progress": 5
        })

        # Head2Head
        comp = self.test_component("Head to Head", f"{self.base_url}/head2head", "statistics", ai_potential="high")
        if comp.accessible:
            self.inventory.head2head_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Head-to-Head Analysis")

        # Team Statistics
        comp = self.test_component("Team Statistics", f"{self.base_url}/teams", "statistics",
                                   {"include": "statistics", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.team_statistics_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Detailed Team Statistics")

        # Player Profiles
        comp = self.test_component("Player Profiles", f"{self.base_url}/players", "statistics",
                                   {"include": "detailedStatistics", "per_page": "25"}, "medium")
        if comp.accessible:
            self.inventory.player_profiles_available = True
            self.inventory.working_components.append(comp)

        # Topscorers
        comp = self.test_component("Topscorers", f"{self.base_url}/topscorers", "statistics", ai_potential="medium")
        if comp.accessible:
            self.inventory.topscorers_available = True
            self.inventory.working_components.append(comp)

        # Standings
        comp = self.test_component("Standings", f"{self.base_url}/standings", "statistics", ai_potential="high")
        if comp.accessible:
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("League Standings Analysis")

    def phase_6_realtime_features(self):
        """Phase 6: Test real-time features"""
        self.analysis_progress.update({
            "phase": "realtime",
            "current_test": "Testing real-time features...",
            "progress": 6
        })

        # Live Standings
        comp = self.test_component("Live Standings", f"{self.base_url}/standings/live", "realtime", ai_potential="medium")
        if comp.accessible:
            self.inventory.live_standings_available = True
            self.inventory.working_components.append(comp)

        # Events Timeline
        comp = self.test_component("Events Timeline", f"{self.base_url}/fixtures", "realtime",
                                   {"include": "events", "per_page": "25"}, "high")
        if comp.accessible:
            self.inventory.events_timeline_available = True
            self.inventory.working_components.append(comp)
            self.inventory.ai_ready_features.append("Match Events Timeline")

        # Lineups
        comp = self.test_component("Lineups", f"{self.base_url}/fixtures", "realtime",
                                   {"include": "lineups", "per_page": "25"}, "medium")
        if comp.accessible:
            self.inventory.lineup_data_available = True
            self.inventory.working_components.append(comp)

        # Commentary
        comp = self.test_component("Live Commentary", f"{self.base_url}/commentaries", "realtime", ai_potential="low")
        if comp.accessible:
            self.inventory.live_commentary_available = True
            self.inventory.working_components.append(comp)

    def phase_7_supplementary_data(self):
        """Phase 7: Test supplementary data components"""
        self.analysis_progress.update({
            "phase": "supplementary",
            "current_test": "Testing supplementary data...",
            "progress": 7
        })

        # Injuries & Suspensions
        comp = self.test_component("Injuries & Suspensions", f"{self.base_url}/injuries", "supplementary", ai_potential="medium")
        if comp.accessible:
            self.inventory.injuries_suspensions_available = True
            self.inventory.working_components.append(comp)

        # Referee Statistics
        comp = self.test_component("Referee Statistics", f"{self.base_url}/referees", "supplementary",
                                   {"include": "statistics"}, "medium")
        if comp.accessible:
            self.inventory.referee_stats_available = True
            self.inventory.working_components.append(comp)

        # TV Stations
        comp = self.test_component("TV Stations", f"{self.base_url}/tv-stations", "supplementary", ai_potential="low")
        if comp.accessible:
            self.inventory.tv_stations_available = True
            self.inventory.working_components.append(comp)

        # News (if available)
        comp = self.test_component("News", f"{self.base_url}/news", "supplementary", ai_potential="low")
        if comp.accessible:
            self.inventory.news_available = True
            self.inventory.working_components.append(comp)

    def phase_8_calculate_readiness_score(self):
        """Phase 8: Calculate AI betting bot readiness score"""
        self.analysis_progress.update({
            "phase": "scoring",
            "current_test": "Calculating AI bot readiness...",
            "progress": 8
        })

        score = 0.0

        # Core data (30% of score)
        if self.inventory.leagues_available > 0:
            score += 5
        if self.inventory.teams_available > 0:
            score += 5
        if self.inventory.fixtures_today > 0:
            score += 10
        if self.inventory.live_matches >= 0:
            score += 10  # Even 0 is good, means endpoint works

        # Odds data (25% of score)
        if self.inventory.bookmakers_count > 0:
            score += 8
        if self.inventory.betting_markets_count > 0:
            score += 7
        if self.inventory.pre_match_odds_count > 0:
            score += 10

        # Advanced analytics (25% of score)
        if self.inventory.xg_match_data_available:
            score += 8
        if self.inventory.pressure_index_available:
            score += 7
        if self.inventory.trends_available:
            score += 5
        if self.inventory.predictions_available:
            score += 5

        # Statistics (20% of score)
        if self.inventory.head2head_available:
            score += 5
        if self.inventory.team_statistics_available:
            score += 5
        if self.inventory.events_timeline_available:
            score += 5
        if self.inventory.player_profiles_available:
            score += 5

        self.inventory.bot_readiness_score = min(score, 100.0)

    def phase_9_generate_strategies(self):
        """Phase 9: Generate recommended betting strategies"""
        self.analysis_progress.update({
            "phase": "strategies",
            "current_test": "Generating betting strategies...",
            "progress": 9
        })

        # Value betting strategies
        if self.inventory.pre_match_odds_count > 0:
            self.inventory.recommended_strategies.append("Pre-match Value Betting Analysis")

        if self.inventory.live_odds_count > 0:
            self.inventory.recommended_strategies.append("Live Betting Opportunity Detection")

        # xG-based strategies
        if self.inventory.xg_match_data_available:
            self.inventory.recommended_strategies.append("Expected Goals (xG) Based Predictions")
            self.inventory.recommended_strategies.append("Over/Under Goals Market Analysis")

        # Form and trends
        if self.inventory.trends_available and self.inventory.head2head_available:
            self.inventory.recommended_strategies.append("Team Form & H2H Trend Analysis")

        # Live betting
        if self.inventory.pressure_index_available and self.inventory.events_timeline_available:
            self.inventory.recommended_strategies.append("In-Play Momentum & Pressure Analysis")

        # Comprehensive analysis
        if len(self.inventory.ai_ready_features) >= 5:
            self.inventory.recommended_strategies.append("Multi-Factor AI Prediction Model")

    def phase_10_advanced_features_assessment(self):
        """Phase 10: Assess advanced features for AI bot"""
        self.analysis_progress.update({
            "phase": "advanced_assessment",
            "current_test": "Assessing advanced AI capabilities...",
            "progress": 10
        })

        advanced_features: List[str] = []

        if self.inventory.xg_match_data_available:
            advanced_features.append("Expected Goals (xG) - Goal probability modeling")

        if self.inventory.pressure_index_available:
            advanced_features.append("Pressure Index - Match momentum tracking")

        if self.inventory.predictions_available:
            advanced_features.append("AI Predictions - Machine learning outcomes")

        if self.inventory.trends_available:
            advanced_features.append("Performance Trends - Historical pattern analysis")

        if self.inventory.events_timeline_available:
            advanced_features.append("Live Events - Real-time match analysis")

        if self.inventory.head2head_available:
            advanced_features.append("Head-to-Head - Historical matchup analysis")

        if self.inventory.team_statistics_available:
            advanced_features.append("Team Statistics - Performance metrics")

        if self.inventory.injuries_suspensions_available:
            advanced_features.append("Team News - Player availability impact")

        self.inventory.advanced_features_available = advanced_features

    def phase_11_final_component_summary(self):
        """Phase 11: Generate final component summary"""
        self.analysis_progress.update({
            "phase": "summary",
            "current_test": "Generating component summary...",
            "progress": 11
        })

        self.inventory.total_components_enabled = len(self.inventory.working_components)

        # Categorize high-value components for betting
        high_value_betting: List[str] = []
        for comp in self.inventory.working_components:
            if comp.betting_value == "high" or comp.ai_potential == "high":
                high_value_betting.append(comp.component_name)

        self.inventory.high_value_components = high_value_betting

    def phase_12_complete_analysis(self):
        """Phase 12: Complete analysis"""
        self.analysis_progress.update({
            "phase": "completed",
            "current_test": "Analysis complete!",
            "progress": 12
        })

    def run_complete_analysis(self):
        """Run comprehensive analysis of all components"""
        self.is_analyzing = True

        try:
            self.phase_1_authentication_test()
            time.sleep(0.5)
            self.phase_2_core_football_data()
            time.sleep(0.5)
            self.phase_3_odds_and_predictions()
            time.sleep(0.5)

            # Endpoint sweep inserted here
            self.analysis_progress.update({
                "phase": "endpoint_sweep",
                "current_test": "Scanning endpoint registry...",
                "progress": 3.5
            })
            self.run_endpoint_registry()
            time.sleep(0.5)

            self.phase_4_advanced_analytics()
            time.sleep(0.5)
            self.phase_5_statistics_components()
            time.sleep(0.5)
            self.phase_6_realtime_features()
            time.sleep(0.5)
            self.phase_7_supplementary_data()
            time.sleep(0.5)
            self.phase_8_calculate_readiness_score()
            time.sleep(0.5)
            self.phase_9_generate_strategies()
            time.sleep(0.5)
            self.phase_10_advanced_features_assessment()
            time.sleep(0.5)
            self.phase_11_final_component_summary()
            time.sleep(0.5)
            self.phase_12_complete_analysis()

        except Exception as e:
            self.analysis_progress.update({
                "phase": "error",
                "current_test": f"Error: {str(e)[:200]}",
                "progress": 0
            })
        finally:
            self.is_analyzing = False

    def get_comprehensive_report(self) -> str:
        """Generate comprehensive copyable report"""
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

⚡ REAL-TIME FEATURES
📊 Live Standings: {"✅ Available" if self.inventory.live_standings_available else "❌ Not Available"}
📝 Live Commentary: {"✅ Available" if self.inventory.live_commentary_available else "❌ Not Available"}
⚽ Events Timeline: {"✅ Available" if self.inventory.events_timeline_available else "❌ Not Available"}
👥 Lineup Data: {"✅ Available" if self.inventory.lineup_data_available else "❌ Not Available"}

🔧 SUPPLEMENTARY DATA
🏥 Injuries & Suspensions: {"✅ Available" if self.inventory.injuries_suspensions_available else "❌ Not Available"}
👨‍⚖️ Referee Statistics: {"✅ Available" if self.inventory.referee_stats_available else "❌ Not Available"}
📺 TV Stations: {"✅ Available" if self.inventory.tv_stations_available else "❌ Not Available"}
📰 News: {"✅ Available" if self.inventory.news_available else "❌ Not Available"}

🚀 HIGH-VALUE COMPONENTS FOR AI BETTING BOT:
{chr(10).join([f"   ✅ {comp}" for comp in self.inventory.high_value_components])}

🤖 AI-READY FEATURES:
{chr(10).join([f"   🎯 {feature}" for feature in self.inventory.ai_ready_features])}

💡 RECOMMENDED BETTING STRATEGIES:
{chr(10).join([f"   🎲 {strategy}" for strategy in self.inventory.recommended_strategies])}
"""
        return report.strip()


# -----------------------------
# JSON serializers (added)
# -----------------------------
def _component_to_dict(c: ComponentCapability) -> Dict[str, Any]:
    return {
        "component_name": c.component_name,
        "endpoint_url": c.endpoint_url,
        "category": c.category,
        "accessible": c.accessible,
        "data_count": c.data_count,
        "sample_data": c.sample_data,
        "api_features": c.api_features,
        "betting_value": c.betting_value,
        "ai_potential": c.ai_potential,
    }

def _inventory_to_dict(inv: ComprehensiveInventory) -> Dict[str, Any]:
    out = {
        "subscription_tier": inv.subscription_tier,
        "api_authenticated": inv.api_authenticated,
        "total_components_enabled": inv.total_components_enabled,

        "leagues_available": inv.leagues_available,
        "teams_available": inv.teams_available,
        "players_available": inv.players_available,
        "fixtures_today": inv.fixtures_today,
        "fixtures_tomorrow": inv.fixtures_tomorrow,
        "live_matches": inv.live_matches,

        "bookmakers_count": inv.bookmakers_count,
        "betting_markets_count": inv.betting_markets_count,
        "pre_match_odds_count": inv.pre_match_odds_count,
        "live_odds_count": inv.live_odds_count,
        "predictions_available": inv.predictions_available,

        "xg_match_data_available": inv.xg_match_data_available,
        "xg_player_efficiency_available": inv.xg_player_efficiency_available,
        "pressure_index_available": inv.pressure_index_available,
        "trends_available": inv.trends_available,

        "match_centre_available": inv.match_centre_available,
        "player_profiles_available": inv.player_profiles_available,
        "team_statistics_available": inv.team_statistics_available,
        "head2head_available": inv.head2head_available,
        "topscorers_available": inv.topscorers_available,

        "live_standings_available": inv.live_standings_available,
        "live_commentary_available": inv.live_commentary_available,
        "events_timeline_available": inv.events_timeline_available,
        "lineup_data_available": inv.lineup_data_available,

        "injuries_suspensions_available": inv.injuries_suspensions_available,
        "referee_stats_available": inv.referee_stats_available,
        "tv_stations_available": inv.tv_stations_available,
        "news_available": inv.news_available,

        "high_value_components": inv.high_value_components,
        "ai_ready_features": inv.ai_ready_features,

        "bot_readiness_score": float(inv.bot_readiness_score),
        "recommended_strategies": inv.recommended_strategies,
        "advanced_features_available": inv.advanced_features_available,
    }
    out["working_components"] = [_component_to_dict(c) for c in inv.working_components]
    out["failed_components"] = [_component_to_dict(c) for c in inv.failed_components]
    return out


# -----------------------------
# Flask Application + HTML UI
# -----------------------------

app = Flask(__name__)
application = app  # for Gunicorn


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
    if (!token) { alert('Please enter your SportMonks API token'); return; }

    const btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_token: token })
        });
        if (response.ok) startPolling();
        else { throw new Error('Failed to start analysis'); }
    } catch (err) {
        alert('Error: ' + err.message);
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
            const percent = (data.progress / 12) * 100;
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('phase').textContent = data.phase.toUpperCase();
            document.getElementById('currentTest').textContent = data.current_test;

            if (data.phase === 'completed') {
                clearInterval(pollTimer);
                loadResults();
            } else if (data.phase === 'error') {
                clearInterval(pollTimer);
                alert('Analysis failed: ' + data.current_test);
                resetUI();
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 1000);
}

async function loadResults() {
    try {
        const response = await fetch('/api/results');
        const data = await response.json();
        displayResults(data);
        resetUI();
    } catch (err) {
        alert('Error loading results');
        resetUI();
    }
}

function displayResults(data) {
    const inv = data.inventory;
    const metrics = `
        <div class="metric"><div class="metric-value">${inv.leagues_available}</div><div class="metric-label">Leagues</div></div>
        <div class="metric"><div class="metric-value">${inv.fixtures_today}</div><div class="metric-label">Today's Matches</div></div>
        <div class="metric"><div class="metric-value">${inv.live_matches}</div><div class="metric-label">Live Matches</div></div>
        <div class="metric"><div class="metric-value">${inv.pre_match_odds_count}</div><div class="metric-label">Pre-match Odds</div></div>
        <div class="metric"><div class="metric-value">${inv.live_odds_count}</div><div class="metric-label">Live Odds</div></div>
        <div class="metric"><div class="metric-value">${Number(inv.bot_readiness_score).toFixed(1)}</div><div class="metric-label">Readiness Score</div></div>
    `;
    document.getElementById('quickMetrics').innerHTML = metrics;

    let readinessClass = 'readiness-not';
    if (inv.bot_readiness_score >= 70) readinessClass = 'readiness-ready';
    else if (inv.bot_readiness_score >= 40) readinessClass = 'readiness-partial';

    document.getElementById('readinessStatus').innerHTML = `<p class="${readinessClass}">Readiness: ${Number(inv.bot_readiness_score).toFixed(1)}/100</p>`;
    document.getElementById('resultsCard').style.display = 'block';

    fullReportData = data.report || '';
    document.getElementById('fullReport').textContent = fullReportData;
    document.getElementById('reportCard').style.display = 'block';
}

function copyReport() {
    if (!fullReportData) return;
    navigator.clipboard.writeText(fullReportData);
    alert('Report copied to clipboard!');
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


# -----------------------------
# Routes
# -----------------------------

analyzer: Optional[ComprehensiveSubscriptionAnalyzer] = None


@app.route("/", methods=["GET"])
def home():
    return HTML_TEMPLATE


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    global analyzer
    data = request.get_json(silent=True) or {}
    api_token = (data.get("api_token") or "").strip()
    if not api_token:
        return jsonify({"error": "API token required"}), 400

    if analyzer and analyzer.is_analyzing:
        return jsonify({"error": "Analysis already running"}), 400

    analyzer = ComprehensiveSubscriptionAnalyzer(api_token)

    t = threading.Thread(target=analyzer.run_complete_analysis, daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/api/progress", methods=["GET"])
def api_progress():
    if not analyzer:
        return jsonify({"phase": "idle", "current_test": "Waiting to start", "progress": 0})
    return jsonify(analyzer.analysis_progress)


@app.route("/api/results", methods=["GET"])
def api_results():
    if not analyzer:
        return jsonify({"error": "No analyzer"}), 400
    if analyzer.analysis_progress.get("phase") != "completed":
        return jsonify({"error": "Analysis not complete"}), 400

    return jsonify({
        "inventory": _inventory_to_dict(analyzer.inventory),
        "report": analyzer.get_comprehensive_report()
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    })


# -----------------------------
# Gunicorn / Dev entrypoints
# -----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    logger.info(f"Starting analyzer on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)