import unittest
from opportunity_scorer import score_opportunity, MIN_OPPORTUNITY_SCORE


class TestOpportunityScorer(unittest.TestCase):

    def test_strong_token_scores_well(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 37500,
            "volume_24h": 80000,
            "buys_24h": 160,
            "sells_24h": 80,
        }
        result = score_opportunity(token)

        self.assertGreater(result["opportunity_score"], 0)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_zero_liquidity_is_ineligible(self):
        token = {
            "liquidity_usd": 0,
            "market_cap_usd": 1,
            "volume_24h": 10000,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_no_volume_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "market_cap_usd": 15000,
            "volume_24h": 0,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_activity_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "market_cap_usd": 15000,
            "volume_24h": 20000,
            "buys_24h": 5,
            "sells_24h": 5,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_score_never_exceeds_100(self):
        token = {
            "liquidity_usd": 100000,
            "market_cap_usd": 150000,
            "volume_24h": 500000,
            "buys_24h": 1000,
            "sells_24h": 500,
        }
        result = score_opportunity(token)
        self.assertLessEqual(result["opportunity_score"], 100)

    def test_invalid_strings_are_handled(self):
        token = {
            "liquidity_usd": "invalid",
            "volume_24h": "unknown",
            "buys_24h": "bad",
            "sells_24h": None,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_nan_values_are_handled(self):
        token = {
            "liquidity_usd": float("nan"),
            "volume_24h": 10000,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_infinite_values_are_handled(self):
        token = {
            "liquidity_usd": float("inf"),
            "volume_24h": 10000,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_negative_values_are_rejected(self):
        token = {
            "liquidity_usd": -10000,
            "market_cap_usd": 1,
            "volume_24h": 10000,
            "buys_24h": -50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_score_is_ineligible_even_with_valid_ratio(self):
        token = {
            "liquidity_usd": 100,
            "market_cap_usd": 200,
            "volume_24h": 500,
            "buys_24h": 15,
            "sells_24h": 10,
        }
        result = score_opportunity(token)

        self.assertLess(result["opportunity_score"], MIN_OPPORTUNITY_SCORE)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any(
            "Opportunity score below minimum" in reason
            for reason in result["reasons"]
        ))

    def test_extreme_volume_liquidity_ratio_is_blocked(self):
        token = {
            "liquidity_usd": 9647.02,
            "market_cap_usd": 15805,
            "volume_24h": 233162.93,
            "buys_24h": 3203,
            "sells_24h": 2442,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any(
            "exceeds 10x" in reason for reason in result["reasons"]
        ))

    def test_zero_market_cap_is_ineligible(self):
        token = {
            "liquidity_usd": 100,
            "market_cap_usd": 0,
            "volume_24h": 500,
            "buys_24h": 15,
            "sells_24h": 10,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertIn("Missing or invalid market cap", result["reasons"])

    def test_score_at_minimum_can_qualify(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_24h": 50000,
            "buys_24h": 40,
            "sells_24h": 20,
        }
        result = score_opportunity(token)

        self.assertGreaterEqual(
            result["opportunity_score"], MIN_OPPORTUNITY_SCORE
        )
        self.assertTrue(result["eligible_for_paper_trading"])


if __name__ == "__main__":
    unittest.main()