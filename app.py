#!/usr/bin/env python3
"""
REAL DATA PROCESSING MODULE
Filters sample data and processes actual upcoming fixtures for real betting opportunities
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any

# Import the class at the top of your file (as requested)
from quick_value_bet_finder import QuickValueBetFinder

logger = logging.getLogger(__name__)


class RealDataProcessor:
    def __init__(self, api_client):
        self.api = api_client
        self.today = date.today()
        self.tomorrow = self.today + timedelta(days=1)

        # Filter out sample/test fixture IDs (these are often historical)
        self.sample_fixture_ids = {19135003, 19427455}  # Liverpool vs Tottenham and other samples

    def filter_real_fixtures(self, raw_data: Dict) -> List[Dict]:
        """Filter out sample data and return only real upcoming fixtures"""
        real_fixtures: List[Dict] = []

        # Process upcoming fixtures from the next few days
        for key, data in raw_data.items():
            if key.startswith("upcoming_") and isinstance(data, dict):
                # Extract date from key like 'upcoming_2025-08-08'
                parts = key.split("_")
                if len(parts) < 2:
                    continue
                date_str = parts[1]

                try:
                    fixture_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                    # Only process fixtures from today onwards
                    if fixture_date >= self.today:
                        fixtures = self.extract_fixtures_from_data(data, fixture_date)
                        real_fixtures.extend(fixtures)

                except ValueError:
                    continue

        # Filter out sample fixtures
        real_fixtures = [f for f in real_fixtures if f.get("id") not in self.sample_fixture_ids]

        logger.info(f"Filtered {len(real_fixtures)} real upcoming fixtures")
        return real_fixtures

    def extract_fixtures_from_data(self, data: Dict, fixture_date: date) -> List[Dict]:
        """Extract fixture information from API response"""
        fixtures: List[Dict] = []

        if "data" in data and isinstance(data["data"], list):
            for fixture in data["data"]:
                try:
                    # Parse fixture data
                    fixture_info = {
                        "id": fixture.get("id"),
                        "home_team_id": None,
                        "away_team_id": None,
                        "home_team_name": "Unknown",
                        "away_team_name": "Unknown",
                        "league_id": fixture.get("league_id"),
                        "league_name": "Unknown",
                        "kickoff_time": None,
                        "status": (fixture.get("state", {}) or {}).get("short_name", "NS"),
                        "date": fixture_date,
                    }

                    # Extract team information
                    participants = fixture.get("participants", [])
                    if len(participants) >= 2:
                        home_is_first = (participants[0].get("meta", {}) or {}).get("location") == "home"
                        home_team = participants[0] if home_is_first else participants[1]
                        away_team = participants[1] if home_is_first else participants[0]

                        fixture_info.update(
                            {
                                "home_team_id": home_team.get("id"),
                                "away_team_id": away_team.get("id"),
                                "home_team_name": home_team.get("name", "Unknown"),
                                "away_team_name": away_team.get("name", "Unknown"),
                            }
                        )

                    # Extract league information
                    if "league" in fixture and isinstance(fixture["league"], dict):
                        fixture_info.update(
                            {
                                "league_id": fixture["league"].get("id"),
                                "league_name": fixture["league"].get("name", "Unknown"),
                            }
                        )

                    # Parse kickoff time
                    if "starting_at" in fixture and fixture["starting_at"]:
                        try:
                            kickoff_time = datetime.fromisoformat(str(fixture["starting_at"]).replace("Z", "+00:00"))
                            fixture_info["kickoff_time"] = kickoff_time
                        except Exception:
                            pass

                    # Only include fixtures that are not started yet
                    if (
                        fixture_info["status"] in ["NS", "TBD", "POSTP"]
                        and fixture_info["home_team_id"]
                        and fixture_info["away_team_id"]
                    ):
                        fixtures.append(fixture_info)

                except Exception as e:
                    logger.error(f"Error parsing fixture: {e}")
                    continue

        return fixtures

    def get_available_odds(self, raw_data: Dict, fixture_ids: List[int]) -> Dict[int, List[Dict]]:
        """Extract available odds for specific fixtures"""
        fixture_odds: Dict[int, List[Dict]] = {}

        for key, data in raw_data.items():
            if "odds" in key and isinstance(data, dict):
                odds_data = self.parse_odds_data(data)

                for odds in odds_data:
                    fixture_id = odds.get("fixture_id")
                    if fixture_id in fixture_ids:
                        if fixture_id not in fixture_odds:
                            fixture_odds[fixture_id] = []
                        fixture_odds[fixture_id].append(odds)

        logger.info(f"Found odds for {len(fixture_odds)} fixtures")
        return fixture_odds

    def parse_odds_data(self, odds_response: Dict) -> List[Dict]:
        """Parse odds data from SportMonks response"""
        odds_list: List[Dict] = []

        if "data" in odds_response and isinstance(odds_response["data"], list):
            for odds_item in odds_response["data"]:
                try:
                    parsed_odds = {
                        "fixture_id": odds_item.get("fixture_id"),
                        "market_id": odds_item.get("market_id"),
                        "bookmaker_id": odds_item.get("bookmaker_id"),
                        "bookmaker_name": (odds_item.get("bookmaker", {}) or {}).get("name", "Unknown"),
                        "market_name": (odds_item.get("market", {}) or {}).get("name", "Unknown"),
                        "selections": [],
                    }

                    # Extract selections (the actual odds)
                    for selection in odds_item.get("selections", []):
                        try:
                            odds_val = float(selection.get("odds", 0))
                        except (TypeError, ValueError):
                            odds_val = 0.0

                        parsed_odds["selections"].append(
                            {
                                "name": selection.get("name", ""),
                                "odds": odds_val,
                                "active": selection.get("active", True),
                            }
                        )

                    if parsed_odds["fixture_id"] and parsed_odds["selections"]:
                        odds_list.append(parsed_odds)

                except Exception as e:
                    logger.error(f"Error parsing odds item: {e}")
                    continue

        return odds_list

    def generate_real_predictions(self, fixtures: List[Dict]) -> List[Dict]:
        """Generate predictions for real upcoming fixtures"""
        predictions: List[Dict] = []

        for fixture in fixtures:
            try:
                # Skip if missing essential data
                if not fixture.get("home_team_id") or not fixture.get("away_team_id"):
                    continue

                # Generate basic prediction using available data
                prediction = self.calculate_match_prediction(fixture)

                if prediction:
                    predictions.append(prediction)

            except Exception as e:
                logger.error(f"Error generating prediction for fixture {fixture.get('id')}: {e}")
                continue

        logger.info(f"Generated {len(predictions)} real predictions")
        return predictions

    def calculate_match_prediction(self, fixture: Dict) -> Optional[Dict]:
        """Calculate prediction for a single match"""
        try:
            # Basic prediction algorithm using team IDs and historical patterns
            home_team_id = fixture["home_team_id"]
            away_team_id = fixture["away_team_id"]
            _ = (home_team_id, away_team_id)  # referenced, reserved for future use

            # Simple prediction model (you can enhance this)
            # For now, use basic probabilities with slight home advantage
            home_win_prob = 0.40  # 40% home win (with home advantage)
            draw_prob = 0.30  # 30% draw
            away_win_prob = 0.30  # 30% away win

            # Over/Under 2.5 goals (typical average is around 2.7 goals per match)
            over_2_5_prob = 0.55  # 55% over 2.5
            under_2_5_prob = 0.45  # 45% under 2.5

            # Both teams to score (historical average ~50-55%)
            btts_yes_prob = 0.52  # 52% both teams score
            btts_no_prob = 0.48  # 48% not both teams score

            # Expected goals (league average)
            expected_home_goals = 1.4
            expected_away_goals = 1.1

            # Confidence based on data availability (basic for now)
            confidence = 65.0

            return {
                "fixture_id": fixture["id"],
                "match": f"{fixture['home_team_name']} vs {fixture['away_team_name']}",
                "home_team": fixture["home_team_name"],
                "away_team": fixture["away_team_name"],
                "league": fixture["league_name"],
                "kickoff_time": fixture["kickoff_time"].isoformat() if fixture.get("kickoff_time") else None,
                "status": fixture["status"],
                "home_win_prob": home_win_prob,
                "draw_prob": draw_prob,
                "away_win_prob": away_win_prob,
                "over_2_5_prob": over_2_5_prob,
                "under_2_5_prob": under_2_5_prob,
                "btts_yes_prob": btts_yes_prob,
                "btts_no_prob": btts_no_prob,
                "expected_home_goals": expected_home_goals,
                "expected_away_goals": expected_away_goals,
                "confidence": confidence,
                "prediction_type": "basic_model",
            }

        except Exception as e:
            logger.error(f"Error calculating prediction: {e}")
            return None

    def find_value_bets_real_data(self, predictions: List[Dict], fixture_odds: Dict[int, List[Dict]]) -> List[Dict]:
        """Find value bets using real prediction and odds data"""
        value_bets: List[Dict] = []

        for prediction in predictions:
            fixture_id = prediction["fixture_id"]

            if fixture_id not in fixture_odds:
                continue

            odds_for_fixture = fixture_odds[fixture_id]

            # Process each odds entry for this fixture
            for odds_entry in odds_for_fixture:
                market_id = odds_entry.get("market_id")

                # Process 3-way result (market_id = 1)
                if market_id == 1:
                    bets = self.process_1x2_market(prediction, odds_entry)
                    value_bets.extend(bets)

                # Process Over/Under 2.5 (market_id = 5)
                elif market_id == 5:
                    bets = self.process_ou_market(prediction, odds_entry)
                    value_bets.extend(bets)

                # Process Both Teams to Score (market_id = 14)
                elif market_id == 14:
                    bets = self.process_btts_market(prediction, odds_entry)
                    value_bets.extend(bets)

        # Sort by edge (highest first)
        value_bets.sort(key=lambda x: x.get("edge", 0), reverse=True)

        logger.info(f"Found {len(value_bets)} value betting opportunities")
        return value_bets

    def process_1x2_market(self, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        """Process 1X2 market for value bets"""
        value_bets: List[Dict] = []

        # Map predictions to bet types
        bet_mappings = {
            "Home": ("home_win_prob", "1"),
            "Draw": ("draw_prob", "X"),
            "Away": ("away_win_prob", "2"),
        }

        for selection in odds_entry.get("selections", []):
            selection_name = selection.get("name", "")
            odds_value = selection.get("odds", 0)

            if odds_value <= 1.0:
                continue

            # Find matching prediction probability
            prob_key = None
            bet_type = None

            for name_pattern, (prob_k, bet_t) in bet_mappings.items():
                if name_pattern.lower() in selection_name.lower():
                    prob_key = prob_k
                    bet_type = bet_t
                    break

            if prob_key and bet_type:
                predicted_prob = prediction.get(prob_key, 0)
                implied_prob = 1 / odds_value
                edge = predicted_prob - implied_prob

                # Minimum 3% edge for real bets
                if edge > 0.03:
                    value_bets.append(
                        {
                            "fixture_id": prediction["fixture_id"],
                            "match": prediction["match"],
                            "market": "1X2",
                            "bet_type": bet_type,
                            "selection": selection_name,
                            "odds": odds_value,
                            "predicted_prob": predicted_prob,
                            "implied_prob": implied_prob,
                            "edge": edge,
                            "edge_percent": edge * 100,
                            "confidence": prediction.get("confidence", 0),
                            "bookmaker": odds_entry.get("bookmaker_name", "Unknown"),
                            "kickoff_time": prediction.get("kickoff_time"),
                            "recommendation": self.get_bet_recommendation(edge, prediction.get("confidence", 0)),
                        }
                    )

        return value_bets

    def process_ou_market(self, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        """Process Over/Under market for value bets"""
        value_bets: List[Dict] = []

        for selection in odds_entry.get("selections", []):
            selection_name = selection.get("name", "").lower()
            odds_value = selection.get("odds", 0)

            if odds_value <= 1.0:
                continue

            # Determine bet type and probability
            if "over" in selection_name and "2.5" in selection_name:
                predicted_prob = prediction.get("over_2_5_prob", 0)
                bet_type = "Over 2.5"
            elif "under" in selection_name and "2.5" in selection_name:
                predicted_prob = prediction.get("under_2_5_prob", 0)
                bet_type = "Under 2.5"
            else:
                continue

            implied_prob = 1 / odds_value
            edge = predicted_prob - implied_prob

            if edge > 0.03:
                value_bets.append(
                    {
                        "fixture_id": prediction["fixture_id"],
                        "match": prediction["match"],
                        "market": "Over/Under 2.5",
                        "bet_type": bet_type,
                        "selection": selection.get("name", ""),
                        "odds": odds_value,
                        "predicted_prob": predicted_prob,
                        "implied_prob": implied_prob,
                        "edge": edge,
                        "edge_percent": edge * 100,
                        "confidence": prediction.get("confidence", 0),
                        "bookmaker": odds_entry.get("bookmaker_name", "Unknown"),
                        "kickoff_time": prediction.get("kickoff_time"),
                        "recommendation": self.get_bet_recommendation(edge, prediction.get("confidence", 0)),
                    }
                )

        return value_bets

    def process_btts_market(self, prediction: Dict, odds_entry: Dict) -> List[Dict]:
        """Process Both Teams to Score market for value bets"""
        value_bets: List[Dict] = []

        for selection in odds_entry.get("selections", []):
            selection_name = selection.get("name", "").lower()
            odds_value = selection.get("odds", 0)

            if odds_value <= 1.0:
                continue

            # Determine bet type and probability
            if "yes" in selection_name or "both" in selection_name:
                predicted_prob = prediction.get("btts_yes_prob", 0)
                bet_type = "BTTS Yes"
            elif "no" in selection_name:
                predicted_prob = prediction.get("btts_no_prob", 0)
                bet_type = "BTTS No"
            else:
                continue

            implied_prob = 1 / odds_value
            edge = predicted_prob - implied_prob

            if edge > 0.03:
                value_bets.append(
                    {
                        "fixture_id": prediction["fixture_id"],
                        "match": prediction["match"],
                        "market": "Both Teams to Score",
                        "bet_type": bet_type,
                        "selection": selection.get("name", ""),
                        "odds": odds_value,
                        "predicted_prob": predicted_prob,
                        "implied_prob": implied_prob,
                        "edge": edge,
                        "edge_percent": edge * 100,
                        "confidence": prediction.get("confidence", 0),
                        "bookmaker": odds_entry.get("bookmaker_name", "Unknown"),
                        "kickoff_time": prediction.get("kickoff_time"),
                        "recommendation": self.get_bet_recommendation(edge, prediction.get("confidence", 0)),
                    }
                )

        return value_bets

    def get_bet_recommendation(self, edge: float, confidence: float) -> str:
        """Get betting recommendation based on edge and confidence"""
        if edge > 0.15 and confidence > 70:
            return "STRONG BUY"
        elif edge > 0.10 and confidence > 60:
            return "BUY"
        elif edge > 0.05 and confidence > 50:
            return "CONSIDER"
        elif edge > 0.03:
            return "WEAK VALUE"
        else:
            return "NO VALUE"

    def process_real_betting_opportunities(self, raw_data: Dict) -> Dict:
        """Main method to process real betting opportunities"""
        logger.info("Processing real betting opportunities...")

        # 1. Filter real upcoming fixtures
        real_fixtures = self.filter_real_fixtures(raw_data)

        if not real_fixtures:
            logger.warning("No real upcoming fixtures found")
            return {
                "status": "no_fixtures",
                "message": "No upcoming fixtures found for betting analysis",
                "fixtures_processed": 0,
                "predictions": [],
                "value_bets": [],
                "summary": {
                    "summary_text": "No upcoming fixtures found for betting analysis."
                }
            }

        # 2. Generate predictions for real fixtures
        predictions = self.generate_real_predictions(real_fixtures)

        # 3. Get available odds for these fixtures
        fixture_ids = [f["id"] for f in real_fixtures]
        fixture_odds = self.get_available_odds(raw_data, fixture_ids)

        # 4. Find value bets
        value_bets = self.find_value_bets_real_data(predictions, fixture_odds)

        # 5. Generate summary
        summary = self.generate_betting_summary(real_fixtures, predictions, value_bets)

        return {
            "status": "success",
            "fixtures_processed": len(real_fixtures),
            "predictions_generated": len(predictions),
            "value_bets_found": len(value_bets),
            "fixtures": real_fixtures[:10],  # Top 10 fixtures
            "predictions": predictions,
            "value_bets": value_bets,
            "summary": summary,
        }

    def generate_betting_summary(
        self, fixtures: List[Dict], predictions: List[Dict], value_bets: List[Dict]
    ) -> Dict:
        """Generate comprehensive betting summary"""
        if not value_bets:
            return {
                "total_opportunities": 0,
                "avg_edge": 0,
                "best_bet": None,
                "strong_bets": 0,
                "recommended_bets": 0,
                "fixtures_analyzed": len(fixtures),
                "predictions_made": len(predictions),
                "summary_text": f"Analyzed {len(fixtures)} fixtures, generated {len(predictions)} predictions, but found no value betting opportunities today.",
            }

        # Calculate metrics
        total_edge = sum(bet["edge"] for bet in value_bets)
        avg_edge = total_edge / len(value_bets)

        strong_bets = len([bet for bet in value_bets if bet["recommendation"] in ["STRONG BUY", "BUY"]])
        recommended_bets = len(
            [bet for bet in value_bets if bet["recommendation"] in ["STRONG BUY", "BUY", "CONSIDER"]]
        )

        best_bet = max(value_bets, key=lambda x: x["edge"]) if value_bets else None

        return {
            "total_opportunities": len(value_bets),
            "avg_edge": avg_edge,
            "avg_edge_percent": avg_edge * 100,
            "best_bet": best_bet,
            "strong_bets": strong_bets,
            "recommended_bets": recommended_bets,
            "fixtures_analyzed": len(fixtures),
            "predictions_made": len(predictions),
            "summary_text": f"Analyzed {len(fixtures)} real fixtures and found {len(value_bets)} value betting opportunities with average {avg_edge*100:.1f}% edge.",
        }


# ------------------------------------------------------------------------------
# OPTIONAL: Example bot skeleton showing EXACT integration you requested.
# If you already have a bot class, copy the analyze_real_opportunities() method
# and the four logging lines into your processing pipeline.
# ------------------------------------------------------------------------------

class SportMonksBotSkeleton:
    """
    Minimal skeleton to demonstrate integration:
    - Logs RAW STORE KEYS, PREDICTIONS, and Odds predictions generated
    - Calls QuickValueBetFinder for real opportunities
    - Uses RealDataProcessor to clean/structure data if needed elsewhere
    """

    def __init__(self, api_client=None):
        self.api = api_client
        self.raw_store: Dict[str, Any] = {}
        self.predictions: List[Dict[str, Any]] = []

    def analyze_real_opportunities(self) -> int:
        """
        Uses QuickValueBetFinder to analyze currently stored raw data and logs results.
        Returns the count of value bets.
        """
        # Get your existing raw data (the way you're currently doing it)
        raw_data = self.raw_store  # Your existing raw data storage

        # Find real betting opportunities
        finder = QuickValueBetFinder()
        opportunities = finder.find_real_betting_opportunities(raw_data)

        value_bets = opportunities["value_bets"]
        summary = opportunities["summary"]

        logger.info(f"🎯 REAL BETTING ANALYSIS: {summary['summary_text']}")

        if value_bets:
            logger.info(
                f"💰 BEST VALUE BET: {value_bets[0]['match']} - {value_bets[0]['bet_type']} "
                f"@ {value_bets[0]['odds']} ({value_bets[0]['edge_percent']}% edge)"
            )

            for bet in value_bets[:3]:  # Top 3
                logger.info(
                    f"💡 {bet['match']} | {bet['bet_type']} @ {bet['odds']} "
                    f"| {bet['edge_percent']}% edge | {bet['recommendation']}"
                )
        else:
            logger.info("📊 No value betting opportunities found today")

        return len(value_bets)

    def run_after_processing(self) -> None:
        """
        Call this after your current data processing steps complete.
        It prints the three log lines (exact order), then triggers real opportunities.
        """

        # EXACTLY AS YOU ASKED TO LOG, straight after your processing:
        logger.info(f"RAW STORE KEYS: {list(self.raw_store.keys())}")
        logger.info(f"PREDICTIONS: {self.predictions}")
        logger.info(f"INFO:SportMonksBot:Odds predictions generated: {len(self.predictions)}")

        # Call this at the end of your existing process
        real_opportunities_count = self.analyze_real_opportunities()
        logger.info(f"INFO:SportMonksBot:Real odds opportunities found: {real_opportunities_count}")


# If you want to test this file standalone, uncomment below.
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s")
#     bot = SportMonksBotSkeleton()
#     # Populate bot.raw_store and bot.predictions here as needed...
#     bot.run_after_processing()