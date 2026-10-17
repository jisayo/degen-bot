import time
import unittest
from unittest.mock import Mock, patch

import requests

from scanner import scan_tokens, get_token_age_minutes


class TestScanner(unittest.TestCase):

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_safe_candidate_is_eligible(
        self, mock_get, mock_score, mock_risk
    ):
        profiles_response = Mock()
        profiles_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "tokenAddress": "TEST_MINT",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "priceUsd": "0.01",
            "marketCap": 30000,
            "liquidity": {"usd": 20000},
            "volume": {"h24": 50000},
            "txns": {"h24": {"buys": 100, "sells": 80}},
            "url": "https://example.com/pair",
        }]

        mock_get.side_effect = [profiles_response, pairs_response]
        mock_risk.return_value = {
            "risk_level": "LOW",
            "risk_score": 1,
            "trade_allowed": True,
            "risks": [],
        }
        mock_score.return_value = {
            "opportunity_score": 80,
            "eligible_for_paper_trading": True,
            "reasons": [],
        }

        results = scan_tokens()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["paper_eligible"])

    @patch("scanner.check_rug_risk")
    @patch("scanner.score_opportunity")
    @patch("scanner.requests.get")
    def test_ratio_below_50_percent_is_rejected(
        self, mock_get, mock_score, mock_risk
    ):
        profiles = Mock()
        profiles.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000, "tokenAddress": "RATIO_49"
        }]
        pairs = Mock()
        pairs.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000, "priceUsd": "0.01",
            "marketCap": 10000, "liquidity": {"usd": 4900},
            "volume": {"h24": 50000},
            "txns": {"h24": {"buys": 100, "sells": 80}},
        }]
        mock_get.side_effect = [profiles, pairs]
        mock_risk.return_value = {
            "risk_level": "LOW", "risk_score": 1,
            "trade_allowed": True, "risks": [],
        }
        mock_score.return_value = {
            "opportunity_score": 80,
            "eligible_for_paper_trading": True, "reasons": [],
        }

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
        profiles = Mock()
        profiles.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000, "tokenAddress": "RATIO_50"
        }]
        pairs = Mock()
        pairs.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000, "priceUsd": "0.01",
            "marketCap": 10000, "liquidity": {"usd": 5000},
            "volume": {"h24": 50000},
            "txns": {"h24": {"buys": 100, "sells": 80}},
        }]
        mock_get.side_effect = [profiles, pairs]
        mock_risk.return_value = {
            "risk_level": "LOW", "risk_score": 1,
            "trade_allowed": True, "risks": [],
        }
        mock_score.return_value = {
            "opportunity_score": 80,
            "eligible_for_paper_trading": True, "reasons": [],
        }

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
        profiles_response = Mock()
        profiles_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "tokenAddress": "RISKY_MINT",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "priceUsd": "0.01",
            "liquidity": {"usd": 20000},
            "volume": {"h24": 50000},
            "txns": {"h24": {"buys": 100, "sells": 80}},
        }]

        mock_get.side_effect = [profiles_response, pairs_response]
        mock_risk.return_value = {
            "risk_level": "HIGH",
            "risk_score": 80,
            "trade_allowed": False,
            "risks": ["Suspicious token"],
        }
        mock_score.return_value = {
            "opportunity_score": 90,
            "eligible_for_paper_trading": True,
            "reasons": [],
        }

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
        profiles_response = Mock()
        profiles_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "tokenAddress": "NO_PRICE",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
            "pairCreatedAt": (time.time() - 600) * 1000,
            "priceUsd": "0",
            "liquidity": {"usd": 20000},
            "volume": {"h24": 50000},
            "txns": {"h24": {"buys": 100, "sells": 80}},
        }]

        mock_get.side_effect = [profiles_response, pairs_response]

        results = scan_tokens()

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

class TestTokenAge(unittest.TestCase):
    def test_five_minutes_is_valid(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 5 * 60_000}
        self.assertEqual(get_token_age_minutes(pair, now), 5)

    def test_sixty_minutes_is_valid(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now - 60 * 60_000}
        self.assertEqual(get_token_age_minutes(pair, now), 60)

    def test_missing_timestamp_is_invalid(self):
        self.assertIsNone(get_token_age_minutes({}))

    def test_invalid_timestamp_is_rejected(self):
        self.assertIsNone(get_token_age_minutes({"pairCreatedAt": "invalid"}))

    def test_future_timestamp_is_rejected(self):
        now = 1_000_000_000
        pair = {"pairCreatedAt": now + 60_000}
        self.assertIsNone(get_token_age_minutes(pair, now))
