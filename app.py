#!/usr/bin/env python3
"""
SportMonks v3 API Web Tester - Data Maximizer (safe, non-breaking)
- Keeps existing tester + routes intact
- Adds robust odds fallbacks, retries, pagination
- Adds in-play pulse (live odds + events snapshot)
- Adds predictions (1X2, OU) with fairising + Kelly (¼)
"""

import requests
import json
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import os
from dataclasses import dataclass, asdict, field
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import io
import random
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

# -------------------- Data models --------------------

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

# -------------------- Simple in-memory cache --------------------
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

# -------------------- Tester class --------------------

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

    # ---------- helpers: backoff, pagination, robust GET ----------
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

    # ---------- endpoints setup ----------
    def setup_test_endpoints(self) -> List[EndpointTest]:
        today = datetime.now().strftime('%Y-%m-%d')
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

    # ---------- discovery ----------
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

    # ---------- single endpoint test ----------
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

    # ---------- robust odds + details pull ----------
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
        target = str(self.prediction_settings["ou_target_line"]).replace(".", "")
        if ("over" in lab or lab.startswith("o")) and ("25" in lab or target in lab): return "Over 2.5"
        if ("under" in lab or lab.startswith("u")) and ("25" in lab or target in lab): return "Under 2.5"
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
            "participants", "scores", "state", "venue", "league", "weatherreport",
            "lineups.player", "statistics.type", "events", "odds"
        ])
        url = f"{self.base_url}/fixtures/{fixture_id}?include={includes}"
        status, body, _, _ = self._get(url)
        return {"status": status, "body": body, "source": "fixtures_include"}

    def _try_odds_fallbacks(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        # We try a few likely variants; accept first that returns data array-like under "data"
        variants = [
            f"{self.odds_base_url}/fixtures/{fixture_id}",
            f"{self.odds_base_url}/fixture/{fixture_id}",
            f"{self.base_url}/odds/fixture/{fixture_id}",
        ]
        for url in variants:
            status, body, _, _ = self._get(url)
            if status == 200 and isinstance(body, dict) and ("data" in body):
                data = body.get("data")
                if data:
                    return {"status": status, "body": body, "source": url}
        return None

    def fetch_fixture_detail(self, fixture_id: int) -> FixtureDetail:
        # 1) Try rich includes
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

        # 2) If no odds via includes, try dedicated odds fallbacks
        if odds_count == 0:
            fb = self._try_odds_fallbacks(fixture_id)
            if fb and isinstance(fb["body"], dict):
                od_data = fb["body"].get("data") or []
                odds_count = len(od_data) if isinstance(od_data, list) else (1 if od_data else 0)
                ext2 = self._extract_odds_from_nodes(od_data if isinstance(od_data, list) else [od_data])
                # merge/overwrite with fallback results
                for k in ("Home","Draw","Away"):
                    if ext2["best_1x2"].get(k):
                        extracted["best_1x2"][k] = ext2["best_1x2"][k]
                        extracted["best_1x2_bm"][k] = ext2["best_1x2_bm"][k]
                extracted["ou_candidates"].extend(ext2["ou_candidates"])
                bookmaker_count = max(extracted["bookmaker_count"], ext2["bookmaker_count"])
                includes_present["odds"] = True  # we have odds even if not via include

        # availability flags + overround
        markets_available["FT_1X2"] = all(extracted["best_1x2"].get(k) for k in ("Home","Draw","Away"))
        markets_available["OU"] = bool(extracted["ou_candidates"])
        bookmaker_count = max(bookmaker_count, extracted["bookmaker_count"])

        if markets_available["FT_1X2"]:
            inv = sum(1.0 / extracted["best_1x2"][k] for k in ("Home","Draw","Away"))
            overround_ft = round((inv - 1.0) * 100, 2)

        # completeness
        score = 0
        weight = {"participants":12,"scores":8,"state":8,"venue":6,"league":8,"weatherreport":6,"lineups":10,"stats":10,"events":12,"odds":20}
        for k, v in includes_present.items():
            if v: score += weight[k]
        if markets_available["FT_1X2"]:
            score += 10
        score = min(score, 100)

        fd = FixtureDetail(
            fixture_id=fixture_id, league_id=league_id, name=name, starting_at=starting_at,
            has_odds=has_odds_flag or includes_present["odds"],
            includes_present=includes_present, markets_available=markets_available,
            bookmaker_count=bookmaker_count, odds_count=odds_count, overround_ft_1x2=overround_ft,
            completeness_score=score
        )

        # stash aux for predictions
        self.cache.set(aux_key, extracted, ttl_seconds=120)
        return fd

    # ---------- predictions ----------
    @staticmethod
    def implied_prob(odds: float) -> float:
        return 1.0 / float(odds) if odds and odds > 1.0 else 0.0

    @staticmethod
    def de_overround(probs: List[float]) -> List[float]:
        s = sum(probs)
        if s <= 0: return probs
        return [p / s for p in probs]

    @staticmethod
    def kelly_fraction(p: float, b: float) -> float:
        if b <= 0: return 0.0
        f = (p*(b+1) - 1) / b
        return max(0.0, f)

    def predict_for_fixture(self, fixture_id: int, detail: FixtureDetail) -> FixturePrediction:
        pred = FixturePrediction(fixture_id=fixture_id, name=detail.name, starting_at=detail.starting_at, league_id=detail.league_id)
        aux = self.cache.get(f"fixture_odds_aux:{fixture_id}") or {}
        best_1x2 = aux.get("best_1x2") or {}
        best_1x2_bm = aux.get("best_1x2_bm") or {}
        ou_candidates = aux.get("ou_candidates") or []

        # 1X2
        if detail.markets_available.get("FT_1X2") and all(best_1x2.get(k) for k in ("Home","Draw","Away")):
            oH, oD, oA = best_1x2["Home"], best_1x2["Draw"], best_1x2["Away"]
            pH, pD, pA = self.implied_prob(oH), self.implied_prob(oD), self.implied_prob(oA)
            fH, fD, fA = self.de_overround([pH, pD, pA])
            book_pct = (1.0/oH + 1.0/oD + 1.0/oA) * 100.0

            for pick, odds, fair_p, bm in [
                ("Home", oH, fH, best_1x2_bm.get("Home")),
                ("Draw", oD, fD, best_1x2_bm.get("Draw")),
                ("Away", oA, fA, best_1x2_bm.get("Away")),
            ]:
                edge = fair_p - (1.0 / odds)
                k = self.kelly_fraction(fair_p, odds - 1.0) * self.prediction_settings["kelly_fraction"] if edge > 0 else 0.0
                note = f"Fairised | Fair≈{(1.0/fair_p):.2f} | Book%≈{book_pct:.1f}%"
                pred.selections.append(Selection(
                    market="1X2", pick=pick, odds=odds, implied_prob=self.implied_prob(odds),
                    fair_prob=fair_p, model_prob=fair_p, edge=edge, kelly_fraction=round(k, 4),
                    bookmaker_id=bm, notes=note
                ))

        # OU 2.5
        if ou_candidates:
            best_over, best_under = None, None
            for pick, dec, bm, _ in ou_candidates:
                if "over" in pick.lower():
                    if not best_over or dec > best_over[1]:
                        best_over = (pick, dec, bm)
                else:
                    if not best_under or dec > best_under[1]:
                        best_under = (pick, dec, bm)
            if best_over and best_under:
                oO, oU = best_over[1], best_under[1]
                pO, pU = self.implied_prob(oO), self.implied_prob(oU)
                fO, fU = self.de_overround([pO, pU])
                book_pct = (1.0/oO + 1.0/oU) * 100.0

                for pick, odds, fair_p, bm in [(best_over[0], oO, fO, best_over[2]), (best_under[0], oU, fU, best_under[2])]:
                    edge = fair_p - (1.0 / odds)
                    k = self.kelly_fraction(fair_p, odds - 1.0) * self.prediction_settings["kelly_fraction"] if edge > 0 else 0.0
                    note = f"Fairised | Fair≈{(1.0/fair_p):.2f} | Book%≈{book_pct:.1f}%"
                    pred.selections.append(Selection(
                        market=f"OU {self.prediction_settings['ou_target_line']}", pick=pick, odds=odds,
                        implied_prob=self.implied_prob(odds), fair_prob=fair_p, model_prob=fair_p,
                        edge=edge, kelly_fraction=round(k, 4), bookmaker_id=bm, notes=note
                    ))

        min_edge = self.prediction_settings["min_edge"]
        viable = [s for s in pred.selections if s.edge >= min_edge]
        pred.best = max(viable, key=lambda s: s.edge) if viable else (max(pred.selections, key=lambda s: s.edge, default=None))
        return pred

    # ---------- analysis ----------
    def derive_capabilities(self) -> Dict[str, bool]:
        by = {r.endpoint: r for r in self.test_results}
        return {
            "odds_access": by.get("All Pre-match Odds", TestResult("",0,False,0,0,{}, {}, [],[])).success,
            "bookmaker_data": by.get("All Bookmakers", TestResult("",0,False,0,0,{}, {}, [],[])).success,
            "market_data": by.get("All Markets", TestResult("",0,False,0,0,{}, {}, [],[])).success,
            "fixture_data": by.get("Today's Fixtures", TestResult("",0,False,0,0,{}, {}, [],[])).success,
            "live_data": by.get("Live Matches", TestResult("",0,False,0,0,{}, {}, [],[])).success,
            "predictions_access": False
        }

    def build_analysis_payload(self) -> Dict[str, Any]:
        summary = self.get_summary_stats()
        capabilities = self.derive_capabilities()

        critical, high_value, failed_critical = [], [], []
        for r in self.test_results:
            if r.endpoint in ("All Pre-match Odds", "Today's Fixtures", "All Markets", "All Bookmakers"):
                critical.append({"name": r.endpoint, "data_count": r.data_count, "quality": 100 if r.success else 0})
            elif r.endpoint in ("Live Matches", "Top Leagues"):
                high_value.append({"name": r.endpoint, "data_count": r.data_count, "quality": 80 if r.success else 0})
            elif ("Value Bets" in r.endpoint or "Probabilities" in r.endpoint) and not r.success:
                failed_critical.append({"name": r.endpoint, "error": (r.errors[0] if r.errors else f"HTTP {r.status_code}")})

        sr = summary.get("success_rate", 0)
        readiness_level = "insufficient"
        if sr >= 90: readiness_level = "excellent"
        elif sr >= 70: readiness_level = "good"
        elif sr >= 40: readiness_level = "moderate"

        roadmap = [
            {"phase": 1, "title": "Data Layer & Health", "weeks": "1 week",
             "tasks": ["Drill-down fetch per fixture with fallbacks", "Normalize odds & implied probs", "Caching + backoff"]},
            {"phase": 2, "title": "Baseline Models", "weeks": "1 week",
             "tasks": ["1X2 via fairised priors + simple form", "Totals via OU ladder", "Confidence + eligibility rules"]},
            {"phase": 3, "title": "Automation & Delivery", "weeks": "1 week",
             "tasks": ["In-play pulse + alerts", "Delivery (Telegram)", "ROI tracking"]}
        ]

        exec_summary = {
            "overall_readiness": readiness_level.upper(),
            "readiness_level": readiness_level,
            "feasibility_score": int(round(sr)),
            "total_endpoints": summary.get("total", 0),
            "successful_endpoints": summary.get("successful", 0),
            "critical_sources": len(critical),
            "high_value_sources": len(high_value),
            "total_data_items": summary.get("total_data_items", 0)
        }

        return {
            "executive_summary": exec_summary,
            "capabilities": capabilities,
            "data_sources": {
                "critical": critical,
                "high_value": high_value,
                "failed_critical": failed_critical
            },
            "fixture_details": [asdict(fd) for fd in self.fixture_details],
            "recommendations": [
                "Use in-play pulse to capture evolving edges.",
                "Filter by bookmakers you actually bet with for realistic pricing.",
            ],
            "implementation_roadmap": roadmap,
            "development_strategy": {
                "approach": "Odds-led predictions with fairising + ¼ Kelly; live pulse for in-play.",
                "timeline": "2–3 weeks to MVP",
                "tech_stack": ["Python","Flask","Requests","Redis (optional)","SQLite/Postgres"],
                "primary_markets": ["1X2","Over/Under 2.5"],
                "estimated_cost": "Within current SportMonks plan",
                "expected_roi": "Start paper; move to small stakes when stable."
            }
        }

    # ---------- orchestrator ----------
    def run_tests_async(self):
        self.is_testing = True
        self.test_results = []
        self.fixture_details = []
        endpoints = self.setup_test_endpoints()
        self.testing_progress = {'current': 0, 'total': len(endpoints) + 1, 'status': 'running', 'current_test': ''}

        try:
            # Smoke tests
            for i, endpoint in enumerate(endpoints):
                if not self.is_testing: break
                self.testing_progress.update(current=i+1, current_test=endpoint.name)
                self.test_results.append(self.test_single_endpoint(endpoint))
                time.sleep(0.2)

            # Fixture drilldown (up to 8)
            if self.is_testing:
                self.testing_progress.update(current=len(endpoints)+1, current_test="Fixture Drill-down")
                if not self.discovered_fixture_ids:
                    today = datetime.now().strftime('%Y-%m-%d')
                    url = f"{self.base_url}/fixtures/date/{today}"
                    status, body, _, _ = self._get(url)
                    if status == 200 and isinstance(body, dict):
                        self._collect_fixtures(body)

                for fid in self.discovered_fixture_ids[:8]:
                    self.fixture_details.append(self.fetch_fixture_detail(fid))
                    time.sleep(0.12)

            self.testing_progress['status'] = 'completed'
        except Exception as e:
            self.testing_progress['status'] = f'error: {str(e)[:120]}'
        finally:
            self.is_testing = False

    # ---------- summary ----------
    def get_summary_stats(self) -> Dict:
        if not self.test_results:
            return {'total': 0, 'successful': 0, 'failed': 0, 'success_rate': 0, 'avg_response_time': 0, 'total_data_items': 0}
        successful = sum(1 for r in self.test_results if r.success)
        total = len(self.test_results)
        avg_rt = round(sum(r.response_time for r in self.test_results if r.success) / max(successful, 1), 2)
        items = sum(r.data_count for r in self.test_results)
        return {'total': total, 'successful': successful, 'failed': total - successful,
                'success_rate': round(successful / total * 100, 1), 'avg_response_time': avg_rt, 'total_data_items': items}

# -------------------- Flask app --------------------

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
tester: Optional[SportMonksWebTester] = None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/start-test', methods=['POST'])
def start_test():
    global tester
    data = request.get_json(silent=True) or {}
    api_token = (data.get('api_token') or '').strip().replace('\n','').replace('\r','')
    if not api_token:
        return jsonify({'error': 'API token required'}), 400
    if tester and tester.is_testing:
        return jsonify({'error': 'Test already running'}), 400
    try:
        tester = SportMonksWebTester(api_token)
        thread = threading.Thread(target=tester.run_tests_async, daemon=True)
        thread.start()
        return jsonify({'success': True, 'message': 'Test started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-progress')
def get_progress():
    if not tester:
        return jsonify({'progress': {'current': 0, 'total': 0, 'status': 'idle', 'current_test': ''}})
    return jsonify({'progress': tester.testing_progress, 'discovered_ids': tester.discovered_ids,
                    'fixture_ids': tester.discovered_fixture_ids})

@app.route('/api/test-results')
def get_results():
    if not tester:
        return jsonify({'results': [], 'summary': {}, 'discovered_ids': {}, 'analysis': {}})
    results_dict = []
    for r in tester.test_results:
        rd = asdict(r)
        if len(str(rd.get('sample_data', ''))) > 500:
            rd['sample_data'] = {'truncated': 'Data too large for mobile display'}
        results_dict.append(rd)

    analysis = tester.build_analysis_payload()

    return jsonify({
        'results': results_dict,
        'summary': tester.get_summary_stats(),
        'discovered_ids': tester.discovered_ids,
        'fixture_ids': tester.discovered_fixture_ids,
        'analysis': analysis
    })

@app.route('/api/predictions')
def get_predictions():
    if not tester:
        return jsonify({"predictions": [], "message": "Run the analysis first."})
    preds: List[FixturePrediction] = []
    for fd in tester.fixture_details:
        try:
            p = tester.predict_for_fixture(fd.fixture_id, fd)
            if p.selections:
                preds.append(p)
        except Exception:
            continue

    def pack(p: FixturePrediction):
        return {
            "fixture_id": p.fixture_id,
            "name": p.name,
            "starting_at": p.starting_at,
            "league_id": p.league_id,
            "best": asdict(p.best) if p.best else None,
            "selections": [asdict(s) for s in p.selections]
        }

    preds_sorted = sorted(preds, key=lambda x: (x.best.edge if x.best else -1), reverse=True)
    return jsonify({"count": len(preds_sorted), "predictions": [pack(p) for p in preds_sorted]})

@app.route('/api/live-pulse')
def live_pulse():
    """Snapshot of in-play fixtures + quick odds via same fallbacks."""
    if not tester:
        return jsonify({"live": []})
    # get live fixtures
    status, body, _, _ = tester._get(f"{tester.base_url}/livescores/inplay")
    live = []
    if status == 200 and isinstance(body, dict):
        for item in body.get("data") or []:
            fid = item.get("id")
            if not fid:
                continue
            # try minimal enrich: odds fallback + last event minute
            fd_detail = tester.fetch_fixture_detail(int(fid))
            last_min = None
            # pull events if present in includes (we didn't include for pulse; try light fetch)
            inc = tester._try_fixture_includes(int(fid))
            if inc["status"] == 200 and isinstance(inc["body"], dict):
                rel = (inc["body"].get("data") or {}).get("relationships") or {}
                ev = rel.get("events", {}).get("data") or []
                if ev and isinstance(ev, list):
                    try:
                        mins = [e.get("minute") for e in ev if isinstance(e, dict) and e.get("minute") is not None]
                        last_min = max(mins) if mins else None
                    except:
                        last_min = None

            live.append({
                "fixture_id": fid,
                "name": item.get("name"),
                "time": (item.get("time") or {}).get("minute"),
                "scores": item.get("scores"),
                "state": item.get("state"),
                "last_event_min": last_min,
                "markets_available": fd_detail.markets_available,
                "overround_ft_1x2": fd_detail.overround_ft_1x2
            })
    return jsonify({"live": live})

@app.route('/api/download-report')
def download_report():
    if not tester or not tester.test_results:
        return jsonify({'error': 'No results available'}), 400

    # augment fixture_details with odds summaries
    augmented = []
    for fd in tester.fixture_details:
        row = asdict(fd)
        aux = tester.cache.get(f"fixture_odds_aux:{fd.fixture_id}") or {}
        b1 = aux.get("best_1x2") or {}
        if all(b1.get(k) for k in ("Home","Draw","Away")):
            inv = sum(1.0/float(b1[k]) for k in ("Home","Draw","Away"))
            row["book_percentage_1x2"] = round(inv * 100.0, 2)
            row["best_prices_1x2"] = b1
        ou = aux.get("ou_candidates") or []
        row["ou_candidates_count"] = len(ou)
        augmented.append(row)

    report_data = {
        'timestamp': datetime.now().isoformat(),
        'summary': tester.get_summary_stats(),
        'discovered_ids': tester.discovered_ids,
        'fixture_ids': tester.discovered_fixture_ids,
        'results': [asdict(r) for r in tester.test_results],
        'fixture_details': augmented,
        'analysis': tester.build_analysis_payload()
    }

    report_json = json.dumps(report_data, indent=2, default=str)
    buffer = io.BytesIO(report_json.encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, mimetype='application/json', as_attachment=True,
                     download_name=f'sportmonks_test_results_{datetime.now().date().isoformat()}.json')

@app.route('/health')
def health_check():
    status = tester.testing_progress['status'] if tester else 'idle'
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat(), 'testing_status': status})

# Aliases kept for older HTML
@app.route('/api/start-analysis', methods=['POST'])
def start_analysis_alias():
    return start_test()

@app.route('/api/progress')
def progress_alias():
    return get_progress()

@app.route('/api/results')
def results_alias():
    return get_results()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)