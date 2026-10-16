import unittest

from opportunity_scorer import score_opportunity


class TestOpportunityScorer(unittest.TestCase):

    def test_strong_token_scores_well(self):
        token = {
            "liquidity_usd": 25000,
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
            "volume_24h": 10000,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)

        self.assertFalse(result["eligible_for_paper_trading"])

    def test_no_volume_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "volume_24h": 0,
            "buys_24h": 50,
            "sells_24h": 30,
        }
        result = score_opportunity(token)

        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_activity_is_ineligible(self):
        token = {
            "liquidity_usd": 10000,
            "volume_24h": 20000,
            "buys_24h": 5,
            "sells_24h": 5,
        }
        result = score_opportunity(token)

        self.assertFalse(result["eligible_for_paper_trading"])

    def test_score_never_exceeds_100(self):
        token = {
            "liquidity_usd": 100000,
            "volume_24h": 500000,
            "buys_24h": 1000,
            "sells_24h": 500,
        }
        result = score_opportunity(token)

        self.assertLessEqual(result["opportunity_score"], 100)


if __name__ == "__main__":
    unittest.main()
