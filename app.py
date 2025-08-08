#!/usr/bin/env python3
"""
SportMonks v3 API Web Tester - Data Maximizer (safe, non-breaking)

- Keeps original tester routes & logic intact
- FIX: correct per-fixture odds fetch via /v3/odds/pre-match?filter[fixture_id]=...
- Adds robust odds fallbacks, retries, pagination, small cache
- Adds richer endpoints:
    /api/fixtures/today
    /api/fixtures/next48h
    /api/inplay
    /api/fixture/<id>/context
    /api/predictions
- Download report includes book% summaries
- CORS optional (won’t crash if flask-cors not installed)
"""

import requests
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import os
from dataclasses import dataclass, asdict, field
from flask import Flask, render_template, jsonify, request, send_file
try:
    from flask_cors import CORS
    _HAS_CORS = True
except Exception:
    CORS = None
    _HAS_CORS = False
import io
import random
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

# -------------------- Models --------------------
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

@dataclass
class FixtureDetail:
    fixture_id: int
    league_id: Optional[int]
    name: Optional[str]
    starting_at: Optional[str]
    has_odds: bool
    includes_present: Dict[str, bool]
    markets_available: Dict[str, bool]
    bookmaker_count: int
    odds_count: int
    overround_ft_1x2: Optional[float] = None
    completeness_score: int = 0

@dataclass
class Selection:
    market: str
    pick: str
    odds: float
    implied_prob: float
    fair_prob: float
    model_prob: float
    edge: float
    kelly_fraction: float
    bookmaker_id: Optional[int] = None
    notes: Optional[str] = None

@dataclass
class FixturePrediction:
    fixture_id: int
    name: Optional[str]
    starting_at: Optional[str]
    league_id: Optional[int]
    selections: List[Selection] = field(default_factory=list)
    best: Optional[Selection] = None

# -------------------- Small cache --------------------
class SimpleCache:
    def __init__(self):
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str):
        rec = self._store.get(key)
        if not rec:
            return None
        expires_at, value = rec
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int = 120):
        self._store[key] = (time.time() + ttl_seconds, value)

# -------------------- Core Tester --------------------
class SportMonksWebTester:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.sportmonks.com/v3/football"
        self.odds_base_url = "https://api.sportmonks.com/v3/odds"
        self.session = requests.Session()
        self.session.params = {"api_token": api_token}
        self.session.headers.update({"Accept": "application/json"})

        self.discovered_ids = {
            'fixture_id': None, 'league_id': None, 'season_id': None, 'team_id': None,
            'player_id': None, 'bookmaker_id': None, 'market_id': None, 'round_id': None, 'stage_id': None
        }
        self.discovered_fixture_ids: List[int] = []

        self.test_results: List[TestResult] = []
        self.fixture_details: List[FixtureDetail] = []
        self.testing_progress = {'current': 0, 'total': 0, 'status': 'idle', 'current_test': ''}
        self.is_testing = False

        self.cache = SimpleCache()
        self.prediction_settings = {
            "bookmaker_allowlist": None,  # e.g., [2, 8, 11]
            "min_edge": 0.03,
            "kelly_fraction": 0.25,
            "ou_target_line": 2.5
        }

    # ---------- HTTP helpers ----------
    def _sleep_backoff(self, attempt: int):
        time.sleep(min(1.6, (0.2 * (2 ** attempt)) + random.uniform(0, 0.1)))

    def _join_params(self, url: str, extra: Dict[str, str]) -> str:
        u = urlparse(url)
        q = parse_qs(u.query)
        for k, v in extra.items():
            q[k] = [str(v)]
        new_q = urlencode({k: v[0] for k, v in q.items()})
        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))

    def _get_once(self, url: str, timeout=20) -> Tuple[int, Any, float, Optional[str]]:
        cached = self.cache.get(url)
        if cached:
            return cached
        start = time.time()
        try:
            r = self.session.get(url, timeout=timeout)
            elapsed = time.time() - start
            try:
                j = r.json()
            except Exception:
                j = None
            result = (r.status_code, j, elapsed, None)
        except Exception as e:
            result = (0, None, time.time() - start, str(e)[:200])
        self.cache.set(url, result, ttl_seconds=30)
        return result

    def _fetch_all_pages(self, url: str, max_pages: int = 5) -> Tuple[int, Any, float, Optional[str]]:
        merged = []
        status_code, body, elapsed, err = self._get_once(url)
        if err or status_code != 200 or not isinstance(body, dict):
            return status_code, body, elapsed, err
        data = body.get("data")
        meta = body.get("meta") or {}
        merged.extend(data if isinstance(data, list) else ([data] if data else []))
        total_time = elapsed

        current_page = int(meta.get("current_page") or 1)
        last_page = int(meta.get("last_page") or 1)
        if last_page <= current_page:
            return status_code, {"data": merged, "meta": meta}, total_time, None

        for page in range(current_page + 1, min(last_page, max_pages) + 1):
            next_url = self._join_params(url, {"page": page})
            sc, b, el, e = self._get_once(next_url)
            total_time += el
            if e or sc != 200 or not isinstance(b, dict):
                break
            d = b.get("data")
            merged.extend(d if isinstance(d, list) else ([d] if d else []))
        return 200, {"data": merged, "meta": meta}, total_time, None

    def _get(self, url: str, timeout=20, paginated=False) -> Tuple[int, Any, float, Optional[str]]:
        cache_key = ("PAGINATED:" if paginated else "SINGLE:") + url
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        attempts = 0
        last = (0, None, 0.0, "No attempt")
        while attempts < 4:
            res = self._fetch_all_pages(url) if paginated else self._get_once(url, timeout=timeout)
            status, body, elapsed, err = res
            last = res
            transient = status in (429, 502, 503, 504) or (status == 200 and body is None)
            if not transient:
                break
            attempts += 1
            self._sleep_backoff(attempts)
        self.cache.set(cache_key, last, ttl_seconds=30)
        return last

    # ---------- Endpoint definitions ----------
    def setup_test_endpoints(self) -> List[EndpointTest]:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        endpoints = [
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
            EndpointTest("Bookmakers", "All Bookmakers",
                f"{self.odds_base_url}/bookmakers",
                "Available bookmakers and their IDs",
                ["id", "name", "legacy_id"]),
            EndpointTest("Markets", "All Markets",
                f"{self.odds_base_url}/markets",
                "Available betting markets",
                ["id", "name", "has_winning_calculations"]),
            EndpointTest("Fixtures", "Today's Fixtures",
                f"{self.base_url}/fixtures/date/{today}",
                "Today's football matches",
                ["id", "name", "starting_at", "localteam_id", "visitorteam_id"]),
            EndpointTest("Live Scores", "Live Matches",
                f"{self.base_url}/livescores/inplay",
                "Currently live matches with scores",
                ["id", "name", "time", "scores"]),
            EndpointTest("Leagues", "Top Leagues",
                f"{self.base_url}/leagues",
                "Available football leagues",
                ["id", "name", "country_id", "is_cup"]),
        ]
        return endpoints

    # ---------- Discovery ----------
    def _collect_fixtures(self, response_data: Dict):
        if not response_data or 'data' not in response_data:
            return
        data = response_data['data']
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and 'id' in item:
                fid = int(item['id'])
                if fid not in self.discovered_fixture_ids:
                    self.discovered_fixture_ids.append(fid)
                if self.discovered_ids['fixture_id'] is None:
                    self.discovered_ids['fixture_id'] = str(fid)
            if isinstance(item, dict) and 'league_id' in item and self.discovered_ids['league_id'] is None:
                self.discovered_ids['league_id'] = str(item.get('league_id'))

    # ---------- Test runner ----------
    def test_single_endpoint(self, endpoint: EndpointTest) -> TestResult:
        paginated = endpoint.name in ("All Bookmakers", "All Markets")
        status_code, body, response_time, err = self._get(endpoint.url, paginated=paginated)

        if err or status_code != 200:
            return TestResult(endpoint=endpoint.name, status_code=status_code, success=False,
                              data_count=0, response_time=response_time, data_structure={},
                              sample_data={}, errors=[err or f"HTTP {status_code}"], warnings=[])

        if endpoint.name == "Today's Fixtures":
            self._collect_fixtures(body)
        if endpoint.name == "All Bookmakers":
            data = body.get("data") or []
            if data and isinstance(data, list):
                self.discovered_ids['bookmaker_id'] = str(data[0].get('id', ''))

        data_count = 0
        sample_data = {}
        if isinstance(body, dict) and 'data' in body:
            data = body['data']
            if isinstance(data, list):
                data_count = len(data)
                sample_data = data[0] if data else {}
            else:
                data_count = 1
                sample_data = data

        return TestResult(endpoint=endpoint.name, status_code=status_code, success=True,
                          data_count=data_count, response_time=response_time,
                          data_structure=self._analyze_structure(body), sample_data=sample_data,
                          errors=[], warnings=[])

    def _analyze_structure(self, data: Any) -> Dict:
        if isinstance(data, dict):
            return {"type": "dict", "key_count": len(data), "sample_keys": list(data.keys())[:5]}
        elif isinstance(data, list):
            return {"type": "list", "length": len(data), "item_type": type(data[0]).__name__ if data else "unknown"}
        else:
            return {"type": type(data).__name__, "sample": str(data)[:50]}

    # ---------- Fixture details + odds (fixed per-fixture odds) ----------
    def _normalize_1x2_label(self, label: str) -> Optional[str]:
        lab = (label or "").strip().lower()
        if lab in ("1","home","home win","local","localteam","home team"): return "Home"
        if lab in ("x","draw","tie"): return "Draw"
        if lab in ("2","away","away win","visitor","visitorteam","away team"): return "Away"
        if "home" in lab or "local" in lab: return "Home"
        if "away" in lab or "visitor" in lab: return "Away"
        if "draw" in lab: return "Draw"
        return None

    def _looks_like_ou_25(self, label: str) -> Optional[str]:
        if not label: return None
        lab = label.lower().replace(" ", "")
        if ("over" in lab or lab.startswith("o")) and ("25" in lab or "2.5" in lab): return "Over 2.5"
        if ("under" in lab or lab.startswith("u")) and ("25" in lab or "2.5" in lab): return "Under 2.5"
        return None

    def _extract_odds_from_nodes(self, odds_nodes: List[Dict]) -> Dict[str, Any]:
        best_1x2 = {"Home": None, "Draw": None, "Away": None}
        best_1x2_bm = {"Home": None, "Draw": None, "Away": None}
        ou_candidates = []
        seen_bookmakers = set()
        allow = self.prediction_settings["bookmaker_allowlist"]

        for o in odds_nodes or []:
            bm_id = o.get("bookmaker_id")
            if allow and bm_id not in allow:
                continue
            if bm_id: seen_bookmakers.add(bm_id)

            market_id = o.get("market_id")
            price = o.get("value")
            label = (o.get("label") or o.get("name") or "").strip()

            if market_id == 1 and price and label:
                key = self._normalize_1x2_label(label)
                if key:
                    try:
                        dec = float(price)
                        prev = best_1x2.get(key)
                        if prev is None or dec > prev:
                            best_1x2[key] = dec
                            best_1x2_bm[key] = bm_id
                    except:
                        pass

            if market_id == 80 and price and label:
                pick = self._looks_like_ou_25(label)
                if pick:
                    try:
                        dec = float(price)
                        ou_candidates.append((pick, dec, bm_id, label))
                    except:
                        pass

        return {
            "best_1x2": best_1x2,
            "best_1x2_bm": best_1x2_bm,
            "ou_candidates": ou_candidates,
            "bookmaker_count": len(seen_bookmakers)
        }

    def _try_fixture_includes(self, fixture_id: int) -> Dict[str, Any]:
        includes = ",".join([
            "participants", "scores", "state", "venue", "league",
            "weatherreport", "lineups.player", "statistics.type", "events", "odds"
        ])
        url = f"{self.base_url}/fixtures/{fixture_id}?include={includes}"
        status, body, _, _ = self._get(url)
        return {"status": status, "body": body, "source": "fixtures_include"}

    # NEW: canonical per-fixture pre-match odds fetch
    def _fetch_odds_for_fixture(self, fixture_id: int) -> Dict[str, Any]:
        base = f"{self.odds_base_url}/pre-match"
        params = {
            "filter[fixture_id]": str(fixture_id),
            "markets": "1,80",      # 1X2 and OU
            "per_page": 200,
        }
        q = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base}?{q}"
        status, body, _, _ = self._get(url, paginated=True)
        return {"status": status, "body": body, "source": url}

    # Reworked fallbacks: try canonical filtered route first, then lenient variants
    def _try_odds_fallbacks(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        primary = self._fetch_odds_for_fixture(fixture_id)
        if (primary["status"] == 200 and isinstance(primary["body"], dict)
            and primary["body"].get("data")):
            return primary

        variants = [
            f"{self.odds_base_url}/pre-match?filter[fixture_id]={fixture_id}&per_page=200",
            f"{self.base_url}/odds/pre-match?filter[fixture_id]={fixture_id}&per_page=200",
        ]
        for url in variants:
            status, body, _, _ = self._get(url, paginated=True)
            if status == 200 and isinstance(body, dict) and body.get("data"):
                return {"status": status, "body": body, "source": url}
        return None

    def fetch_fixture_detail(self, fixture_id: int) -> FixtureDetail:
        inc = self._try_fixture_includes(fixture_id)

        includes_present = {k: False for k in
            ["participants","scores","state","venue","league","weatherreport","lineups","stats","events","odds"]}
        markets_available = {"FT_1X2": False, "OU": False}
        bookmaker_count = 0
        odds_count = 0
        name = league_id = starting_at = None
        has_odds_flag = False
        overround_ft = None

        nodes_from_include = []
        rel = {}

        if inc["status"] == 200 and isinstance(inc["body"], dict):
            d = (inc["body"] or {}).get("data") or {}
            name = d.get("name")
            league_id = d.get("league_id")
            starting_at = d.get("starting_at")
            has_odds_flag = bool(d.get("has_odds"))
            rel = d.get("relationships") or {}

            def present(rn):
                node = rel.get(rn) or {}
                return bool(node.get("data") or node.get("data", []) or node.get("data", {}))

            includes_present["participants"] = present("participants")
            includes_present["scores"] = present("scores")
            includes_present["state"] = present("state")
            includes_present["venue"] = present("venue")
            includes_present["league"] = present("league")
            includes_present["weatherreport"] = present("weatherreport")
            includes_present["lineups"] = present("lineups")
            includes_present["stats"] = present("statistics")
            includes_present["events"] = present("events")
            includes_present["odds"] = present("odds")

            nodes_from_include = rel.get("odds", {}).get("data") or []
            odds_count = len(nodes_from_include)

        aux_key = f"fixture_odds_aux:{fixture_id}"
        extracted = self._extract_odds_from_nodes(nodes_from_include) if nodes_from_include else {
            "best_1x2": {"Home": None, "Draw": None, "Away": None},
            "best_1x2_bm": {"Home": None, "Draw": None, "Away": None},
            "ou_candidates": [],
            "bookmaker_count": 0
        }

        # Use canonical per-fixture odds if includes had none
        if odds_count == 0:
            fb = self._try_odds_fallbacks(fixture_id)
            if fb and isinstance(fb["body"], dict):
                od_data = fb["body"].get("data") or []
                odds_count = len(od_data) if isinstance(od_data, list) else (1 if od_data else 0)
                ext2 = self._extract_odds_from_nodes(od_data if isinstance(od_data, list) else [od_data])
                for k in ("Home","Draw","Away"):
                    if ext2["best_1x2"].get(k):
                        extracted["best_1x2