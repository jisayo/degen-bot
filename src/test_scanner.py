import time
import unittest
from unittest.mock import Mock, patch

import requests

from scanner import scan_tokens, get_token_age_minutes


def make_pair(
    address="TEST_MINT",
    liquidity=20000,
    market_cap=30000,
    price="0.01",
    age_minutes=3,
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
    def test_ratio_below_50_percent_is_rejected(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("RATIO_49")])),
            Mock(json=Mock(return_value=[
                make_pair(
                    address="RATIO_49",
                    liquidity=4900,
                    market_cap=10000,
                )
            ])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["liquidity_mc_ratio"], 0.49)
        self.assertFalse(results[0]["paper_eligible"])

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_ratio_exactly_50_percent_is_accepted(
        self, mock_get, mock_score, mock_risk
    ):
        mock_get.side_effect = [
            Mock(json=Mock(return_value=[make_profile("RATIO_50")])),
            Mock(json=Mock(return_value=[
                make_pair(
                    address="RATIO_50",
                    liquidity=5000,
                    market_cap=10000,
                )
            ])),
        ]
        mock_risk.return_value = make_risk()
        mock_score.return_value = make_opportunity()

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["liquidity_mc_ratio"], 0.50)
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


if __name__ == "__main__":
    unittest.main()