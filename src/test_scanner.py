import unittest
from unittest.mock import Mock, patch

import requests

from scanner import scan_tokens


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
            "tokenAddress": "TEST_MINT",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
            "priceUsd": "0.01",
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
    def test_high_risk_candidate_is_blocked(
        self, mock_get, mock_score, mock_risk
    ):
        profiles_response = Mock()
        profiles_response.json.return_value = [{
            "chainId": "solana",
            "tokenAddress": "RISKY_MINT",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
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
            "tokenAddress": "NO_PRICE",
        }]

        pairs_response = Mock()
        pairs_response.json.return_value = [{
            "chainId": "solana",
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
