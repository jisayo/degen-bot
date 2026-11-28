import unittest
from opportunity_scorer import score_opportunity, MIN_OPPORTUNITY_SCORE


class TestOpportunityScorer(unittest.TestCase):

    def test_strong_token_scores_well(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
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

    def test_liquidity_below_20k_is_ineligible(self):
        token = {
            "liquidity_usd": 19999.0,
            "market_cap_usd": 30000,
            "volume_1h": 10000,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("below minimum of $20,000.00" in r for r in result["reasons"]))

    def test_buy_ratio_below_55_pct_is_ineligible(self):
        # 50% buys (50 buys, 50 sells) is below 55% requirement
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 30000,
            "buys_1h": 50,
            "sells_1h": 50,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("below minimum requirement" in r for r in result["reasons"]))

    def test_no_volume_is_ineligible(self):
        token = {
            "liquidity_usd": 20000,
            "market_cap_usd": 30000,
            "volume_1h": 0,
            "buys_1h": 50,
            "sells_1h": 30,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])

    def test_low_activity_is_ineligible(self):
        token = {
            "liquidity_usd": 20000,
            "market_cap_usd": 30000,
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
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
        }
        result = score_opportunity(token)

        self.assertGreaterEqual(
            result["opportunity_score"], MIN_OPPORTUNITY_SCORE
        )
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_market_cap_below_75k_is_ineligible(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 74999.0,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("below minimum of $75,000.00" in r for r in result["reasons"]))

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
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": 15.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_extended_1h_pump_above_400_pct_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": 450.0,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("buying the top" in r for r in result["reasons"]))

    def test_red_5m_candle_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": 25.0,
            "price_change_m5": -5.2,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("5-minute candle is red" in r for r in result["reasons"]))

    def test_sell_dominated_5m_flow_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 80,
            "sells_1h": 40,
            "price_change_1h": 25.0,
            "price_change_m5": 3.0,
            "buys_5m": 5,
            "sells_5m": 8,
            "volume_5m": 4000,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("sell-dominated" in r for r in result["reasons"]))

    def test_inactive_5m_buys_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 30,
            "sells_1h": 10,
            "price_change_1h": 25.0,
            "price_change_m5": 1.0,
            "buys_5m": 2,
            "sells_5m": 0,
            "volume_5m": 1000,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("buys in the last 5 minutes" in r for r in result["reasons"]))

    def test_low_5m_volume_usd_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
            "price_change_1h": 25.0,
            "price_change_m5": 3.0,
            "buys_5m": 6,
            "sells_5m": 2,
            "volume_5m": 250.0,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("5-min USD volume" in r for r in result["reasons"]))

    def test_decelerating_5m_volume_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 50000,
            "volume_1h": 50000,
            "buys_1h": 200,
            "sells_1h": 40,
            "price_change_1h": 25.0,
            "price_change_m5": 2.0,
            "buys_5m": 4,
            "sells_5m": 1,
            "volume_5m": 1500.0,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("5-min volume fading" in r for r in result["reasons"]))

    def test_healthy_5m_chart_gates_qualify(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 160,
            "sells_1h": 80,
            "price_change_1h": 45.0,
            "price_change_m5": 8.5,
            "buys_5m": 15,
            "sells_5m": 5,
            "volume_5m": 5000.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_adaptive_midcap_allows_10_pct_liq_mc_ratio(self):
        # $25k liquidity / $250k MC = 10% (>= 8% adaptive floor for >= $200k MC)
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 250000,
            "volume_1h": 80000,
            "buys_1h": 140,
            "sells_1h": 70,
            "price_change_1h": 25.0,
            "price_change_m5": 4.0,
            "buys_5m": 12,
            "sells_5m": 4,
            "volume_5m": 4000.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_adaptive_buy_ratio_57_pct_qualifies_with_confirmed_5m_momentum(self):
        # 57% 1h buys qualifies when 5m candle is green and 5m flow is buy-dominated
        token = {
            "liquidity_usd": 26000,
            "market_cap_usd": 140000,
            "volume_1h": 80000,
            "buys_1h": 114,
            "sells_1h": 86,
            "price_change_1h": 20.0,
            "price_change_m5": 3.5,
            "buys_5m": 15,
            "sells_5m": 5,
            "volume_5m": 3000.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_deep_pool_allows_15x_volume_liquidity_ratio(self):
        # $25k liquidity * 15 = $375k 1h volume (allowed up to 20x for >= $20k pools)
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 150000,
            "volume_1h": 375000,
            "buys_1h": 300,
            "sells_1h": 150,
            "price_change_1h": 50.0,
            "price_change_m5": 5.0,
            "buys_5m": 30,
            "sells_5m": 10,
            "volume_5m": 20000.0,
        }
        result = score_opportunity(token)
        self.assertTrue(result["eligible_for_paper_trading"])

    def test_multi_source_bonus_adds_5_points(self):
        base = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 40,
            "sells_1h": 20,
        }
        s1 = score_opportunity({**base, "source_count": 1})
        s2 = score_opportunity({**base, "source_count": 2})
        self.assertEqual(s2["opportunity_score"], s1["opportunity_score"] + 5)

    def test_low_1h_volume_below_25k_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 15000,
            "buys_1h": 40,
            "sells_1h": 20,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("1h volume" in r for r in result["reasons"]))

    def test_trades_below_50_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 30,
            "sells_1h": 15,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("fewer than 50 trades" in r for r in result["reasons"]))

    def test_extreme_buy_imbalance_above_90_pct_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 95,
            "sells_1h": 5,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("Extreme buy imbalance" in r for r in result["reasons"]))

    def test_5m_fomo_spike_above_150_pct_is_rejected(self):
        token = {
            "liquidity_usd": 25000,
            "market_cap_usd": 100000,
            "volume_1h": 50000,
            "buys_1h": 120,
            "sells_1h": 60,
            "price_change_1h": 180.0,
            "price_change_m5": 165.0,
            "buys_5m": 25,
            "sells_5m": 5,
            "volume_5m": 5000.0,
        }
        result = score_opportunity(token)
        self.assertFalse(result["eligible_for_paper_trading"])
        self.assertTrue(any("anti-FOMO cap" in r for r in result["reasons"]))


if __name__ == "__main__":
    unittest.main()