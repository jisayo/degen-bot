import unittest
from opportunity_scorer import score_opportunity, MIN_OPPORTUNITY_SCORE


class TestOpportunityScorer(unittest.TestCase):

    def test_strong_token_scores_well(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 37500,
            "volume_1h": 80000,
            "buys_1h": 160,
            "sells_1h": 80,
        }
        result = score_opportunity(token)

        self.assertGreater(result["opportunity_score"], 0)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_zero_liquidity_is_ineligible(self):
        token = {
            "liquidity_usd": 0,
            "market_cap_usd": 1,
            "volume_1h": 10000,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_liquidity_below_10k_is_ineligible(self):
        token = {
            "liquidity_usd": 9999.0,
            "market_cap_usd": 15000,
            "volume_1h": 10000,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("below minimum of $10,000.00" in r for r in result["reasons"]))

    def test_buy_ratio_below_60_40_is_ineligible(self):
        # 55% buys (55 buys, 45 sells) is below 60:40 requirement
        token = {
            "liquidity_usd": 15000,
            "market_cap_usd": 25000,
            "volume_1h": 30000,
            "buys_1h": 55,
            "sells_1h": 45,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("60:40" in r for r in result["reasons"]))

    def test_no_volume_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "market_cap_usd": 15000,
            "volume_1h": 0,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_activity_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "market_cap_usd": 15000,
            "volume_1h": 20000,
            "buys_1h": 5,
            "sells_1h": 5,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_score_never_exceeds_100(self):
        token = {
            "liquidity_usd": 100000,
            "market_cap_usd": 150000,
            "volume_1h": 500000,
            "buys_1h": 1000,
            "sells_1h": 500,
        }
        result = score_opportunity(token)
        self.assertLessEqual(result["opportunity_score"], 100)

    def test_invalid_strings_are_handled(self):
        token = {
            "liquidity_usd": "invalid",
            "volume_1h": "unknown",
            "buys_1h": "bad",
            "sells_1h": None,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_nan_values_are_handled(self):
        token = {
            "liquidity_usd": float("nan"),
            "volume_1h": 10000,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_infinite_values_are_handled(self):
        token = {
            "liquidity_usd": float("inf"),
            "volume_1h": 10000,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertEqual(result["opportunity_score"], 0)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_negative_values_are_rejected(self):
        token = {
            "liquidity_usd": -10000,
            "market_cap_usd": 1,
            "volume_1h": 10000,
            "buys_1h": -50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_score_is_ineligible_even_with_valid_ratio(self):
        token = {
            "liquidity_usd": 100,
            "market_cap_usd": 200,
            "volume_1h": 500,
            "buys_1h": 15,
            "sells_1h": 10,
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
            "volume_1h": 233162.93,
            "buys_1h": 3203,
            "sells_1h": 2442,
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
            "volume_1h": 500,
            "buys_1h": 15,
            "sells_1h": 10,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertIn("Missing or invalid market cap", result["reasons"])

    def test_score_at_minimum_can_qualify(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
        }
        result = score_opportunity(token)

        self.assertGreaterEqual(
            result["opportunity_score"], MIN_OPPORTUNITY_SCORE
        )
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_negative_1h_price_change_is_ineligible(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": -12.5,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("down-trending" in r for r in result["reasons"]))

    def test_positive_1h_price_change_can_qualify(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": 15.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])


if __name__ == "__main__":
    unittest.main()