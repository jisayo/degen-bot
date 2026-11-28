import time
import unittest
from unittest.mock import Mock, patch

import requests

from scanner import scan_tokens, get_token_age_minutes


def make_pair(
    address="TEST_MINT",
    liquidity=20000,
    market_cap=100000,
    price="0.01",
    age_minutes=45,
    buys=100,
    sells=80,
    volume=50000,
):
    """Create a pair fixture with one-hour activity data."""
    return {
        "chainId": "solana",
        "pairCreatedAt": (time.time() - age_minutes * 60) * 1000,
        "baseToken": {"address": address},
        "priceUsd": price,
        "marketCap": market_cap,
        "liquidity": {"usd": liquidity},
        "volume": {
            "h1": volume,
            "h24": volume * 10,
        },
        "txns": {
            "h1": {
                "buys": buys,
                "sells": sells,
            },
            "h24": {
                "buys": buys * 10,
                "sells": sells * 10,
            },
        },
        "url": "https://example.com/pair",
    }


def make_profile(address="TEST_MINT"):
    return {
        "chainId": "solana",
        "tokenAddress": address,
    }


def make_risk(level="LOW", allowed=True):
    return {
        "risk_level": level,
        "risk_score": 1 if level == "LOW" else 80,
        "trade_allowed": allowed,
        "risks": [],
    }


def make_opportunity(score=80, eligible=True):
    return {
        "opportunity_score": score,
        "eligible_for_paper_trading": eligible,
        "reasons": [],
    }


class TestScanner(unittest.TestCase):

    def setUp(self):
        self._extra_patch = patch("scanner.fetch_extra_discovery_tokens", return_value=[])
        self._extra_patch.start()

    def tearDown(self):
        self._extra_patch.stop()

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_safe_candidate_is_eligible(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile()])),
            Mock(json=Mock(return_value=[make_pair()])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["paper_eligible"])
        self.assertEqual(results[0]["volume_1h"], 50000)
        self.assertEqual(results[0]["buys_1h"], 100)
        self.assertEqual(results[0]["sells_1h"], 80)

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_ratio_below_15_percent_is_rejected(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("RATIO_14")])),
            Mock(json=Mock(return_value=[
                make_pair(
                    address="RATIO_14",
                    liquidity=14000,
                    market_cap=100000,
                )
            ])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["liquidity_mc_ratio"], 0.14)
        self.assertFalse(results[0]["paper_eligible"])

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_ratio_exactly_15_percent_is_accepted(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("RATIO_15")])),
            Mock(json=Mock(return_value=[
                make_pair(
                    address="RATIO_15",
                    liquidity=30000,
                    market_cap=200000,
                )
            ])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["liquidity_mc_ratio"], 0.15)
        self.assertTrue(results[0]["paper_eligible"])

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_high_risk_candidate_is_blocked(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("RISKY_MINT")])),
            Mock(json=Mock(return_value=[
                make_pair(address="RISKY_MINT")
            ])),
        ]
        mock_risk.return_value = make_risk("HIGH", False)
        mock_score.return_value = make_opportunity(90, True)

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["paper_eligible"])

    @patch("scanner.requests.get")
    def test_api_failure_returns_empty_results(self, mock_get):
        mock_get.side_effect = requests.Timeout("Timed out")

        results = scan_tokens()

        self.assertEqual(results, [])

    @patch("scanner.requests.get")
    def test_invalid_price_is_skipped(self, mock_get):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("NO_PRICE")])),
            Mock(json=Mock(return_value=[
                make_pair(address="NO_PRICE", price="0")
            ])),
        ]

        results = scan_tokens()

        self.assertEqual(results, [])

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_missing_one_hour_activity_is_skipped(
        self, mock_get, mock_score, mock_risk
    ):
        pair = make_pair()
        pair["volume"].pop("h1")
        pair["txns"].pop("h1")

        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile()])),
            Mock(json=Mock(return_value=[pair])),
        ]

        results = scan_tokens()

        self.assertEqual(results, [])
        mock_risk.assert_not_called()
        mock_score.assert_not_called()

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_scanner_uses_one_hour_not_24_hour_activity(
        self, mock_get, mock_score, mock_risk
    ):
        pair = make_pair(
            buys=12,
            sells=8,
            volume=3000,
        )

        # Deliberately different 24-hour values.
        pair["volume"]["h24"] = 900000
        pair["txns"]["h24"] = {"buys": 9000, "sells": 8000}

        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile()])),
            Mock(json=Mock(return_value=[pair])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        scan_tokens()

        market_data = mock_risk.call_args.args[0]

        self.assertEqual(market_data["volume_1h"], 3000)
        self.assertEqual(market_data["buys_1h"], 12)
        self.assertEqual(market_data["sells_1h"], 8)

    @patch("scanner.requests.get")
    def test_invalid_profiles_response_returns_empty(self, mock_get):
        mock_get.return_value = Mock(
            json=Mock(return_value={"unexpected": "data"})
        )

        results = scan_tokens()

        self.assertEqual(results, [])

    @patch("scanner.requests.get")
    def test_empty_pair_list_is_skipped(self, mock_get):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile()])),
            Mock(json=Mock(return_value=[])),
        ]

        results = scan_tokens()

        self.assertEqual(results, [])


class TestTokenAge(unittest.TestCase):

    def test_one_minute_is_valid(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 1 * 60_000}

        self.assertEqual(get_token_age_minutes(pair, now), 1)

    def test_five_minutes_is_valid(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 5 * 60_000}

        self.assertEqual(get_token_age_minutes(pair, now), 5)

    def test_age_below_one_minute_is_invalid(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 30_000}
        self.assertEqual(get_token_age_minutes(pair, now), 0.5)

    def test_age_above_five_minutes_is_reported(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 6 * 60_000}
        self.assertEqual(get_token_age_minutes(pair, now), 6)

    def test_missing_timestamp_is_invalid(self):
        self.assertIsNone(get_token_age_minutes({}))

    def test_invalid_timestamp_is_rejected(self):
        self.assertIsNone(
            get_token_age_minutes({"pairCreatedAt": "invalid"})
        )

    def test_future_timestamp_is_rejected(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now + 60_000}

        self.assertIsNone(get_token_age_minutes(pair, now))

    @patch("scanner.fetch_extra_discovery_tokens", return_value=[])
    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_scanner_preserves_negative_price_change_and_extracts_volume_5m(
        self, mock_get, mock_score, mock_risk, _mock_extra
    ):
        pair = make_pair(address="NEG_M5", liquidity=30000, market_cap=100000)
        pair["volume"]["m5"] = 2500.0
        pair["priceChange"] = {"h1": -10.5, "m5": -4.2}

        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("NEG_M5")])),
            Mock(json=Mock(return_value=[pair])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["price_change_1h"], -10.5)
        self.assertEqual(results[0]["price_change_m5"], -4.2)
        self.assertEqual(results[0]["volume_5m"], 2500.0)


class TestMultiDexDiscovery(unittest.TestCase):

    def test_max_tokens_is_at_least_50(self):
        from scanner import MAX_TOKENS
        self.assertGreaterEqual(MAX_TOKENS, 50)

    def test_select_balanced_candidates_fair_round_robin_and_dedup(self):
        from scanner import select_balanced_candidates
        ds_profiles = [{"chainId": "solana", "tokenAddress": f"PROF_{i}"} for i in range(20)]
        extra_tokens = (
            [{"chainId": "solana", "tokenAddress": f"NEW_{i}", "source": "gecko_new_pools"} for i in range(20)]
            + [{"chainId": "solana", "tokenAddress": f"BOOST_{i}", "source": "ds_boosts"} for i in range(20)]
            + [{"chainId": "solana", "tokenAddress": f"TREND_{i}", "source": "gecko_trending"} for i in range(20)]
        )
        # Overlap token appearing in both ds_profiles and gecko_new_pools
        extra_tokens.append({"chainId": "solana", "tokenAddress": "PROF_0", "source": "gecko_new_pools"})

        selected, stats = select_balanced_candidates(ds_profiles, extra_tokens, max_tokens=16)

        self.assertEqual(len(selected), 16)
        self.assertEqual(stats["unique_candidates"], 80)
        self.assertEqual(stats["feed_overlap"], 1)
        # Overlap token should be prioritized first with both sources preserved
        self.assertEqual(selected[0]["tokenAddress"], "PROF_0")
        self.assertEqual(selected[0]["source_count"], 2)
        self.assertIn("ds_profiles", selected[0]["sources"])
        self.assertIn("gecko_new_pools", selected[0]["sources"])
        # Every single feed must be represented fairly (no feed starved out)
        selected_sources = {s for tok in selected for s in tok["sources"]}
        self.assertEqual(
            selected_sources,
            {"ds_profiles", "gecko_new_pools", "ds_boosts", "gecko_trending"},
        )

    @patch("scanner.fetch_extra_discovery_tokens", return_value=[])
    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_scan_metrics_tracks_funnel_and_rejections(
        self, mock_get, mock_score, mock_risk, _mock_extra
    ):
        from scanner import get_last_scan_metrics
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("TOK_1"), make_profile("TOK_2")])),
            Mock(json=Mock(return_value=[make_pair(address="TOK_1", age_minutes=5000)])),  # age skip
            Mock(json=Mock(return_value=[make_pair(address="TOK_2", liquidity=5000, market_cap=100000)])),
        ]
        mock_risk.return_value = make_risk("HIGH", False)
        mock_score.return_value = make_opportunity(20, False)

        scan_tokens()
        metrics = get_last_scan_metrics()
        self.assertEqual(metrics["unique_candidates"], 2)
        self.assertEqual(metrics["selected_for_scan"], 2)
        self.assertEqual(metrics["tokens_evaluated"], 1)
        self.assertEqual(metrics["eligible_opportunities"], 0)
        self.assertEqual(metrics["rejection_counts"].get("age_window"), 1)
        self.assertEqual(metrics["rejection_counts"].get("rug_risk"), 1)
        self.assertIn("scan_duration_sec", metrics)

    @patch("scanner.fetch_extra_discovery_tokens", return_value=[])
    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_age_window_30_to_360_minutes_enforced(
        self, mock_get, mock_score, mock_risk, _mock_extra
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[
                make_profile("TOO_YOUNG"),
                make_profile("IN_WINDOW"),
                make_profile("TOO_OLD"),
            ])),
            Mock(json=Mock(return_value=[make_pair(address="TOO_YOUNG", age_minutes=15)])),
            Mock(json=Mock(return_value=[make_pair(address="IN_WINDOW", age_minutes=60)])),
            Mock(json=Mock(return_value=[make_pair(address="TOO_OLD", age_minutes=400)])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()
        self.assertEqual([r["address"] for r in results], ["IN_WINDOW"])

    @patch("scanner.requests.get")
    def test_fetch_extra_discovery_tokens_parses_gecko_and_boosts(self, mock_get):
        from scanner import fetch_extra_discovery_tokens
        gecko_trending_payload = {
            "data": [
                {
                    "relationships": {
                        "base_token": {"data": {"id": "solana_GECKO_TREND_1"}}
                    }
                },
                {
                    "relationships": {
                        "base_token": {"data": {"id": "solana_So11111111111111111111111111111111111111112"}}
                    }
                },
            ]
        }
        gecko_new_payload = {
            "data": [
                {
                    "relationships": {
                        "base_token": {"data": {"id": "solana_GECKO_NEW_1"}}
                    }
                },
            ]
        }
        boosts_payload = [
            {"chainId": "solana", "tokenAddress": "BOOST_MINT_1"},
            {"chainId": "ethereum", "tokenAddress": "ETH_IGNORED"},
        ]
        mock_get.side_effect = [
            Mock(json=Mock(return_value=gecko_trending_payload)),
            Mock(json=Mock(return_value=gecko_new_payload)),
            Mock(json=Mock(return_value=boosts_payload)),
        ]

        tokens = fetch_extra_discovery_tokens()
        addresses = [t["tokenAddress"] for t in tokens]
        self.assertEqual(addresses, ["GECKO_TREND_1", "GECKO_NEW_1", "BOOST_MINT_1"])


if __name__ == "__main__":
    unittest.main()