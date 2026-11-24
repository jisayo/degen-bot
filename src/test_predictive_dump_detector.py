"""
Unit tests for the Predictive Dump Detection System.
"""

import unittest
from predictive_dump_detector import PredictiveDumpDetector, classify_risk_tier


class TestPredictiveDumpDetector(unittest.TestCase):

    def setUp(self):
        self.detector = PredictiveDumpDetector()

    def test_classify_risk_tier(self):
        self.assertEqual(classify_risk_tier(10), "LOW")
        self.assertEqual(classify_risk_tier(24), "LOW")
        self.assertEqual(classify_risk_tier(25), "MODERATE")
        self.assertEqual(classify_risk_tier(44), "MODERATE")
        self.assertEqual(classify_risk_tier(45), "HIGH")
        self.assertEqual(classify_risk_tier(64), "HIGH")
        self.assertEqual(classify_risk_tier(65), "VERY_HIGH")
        self.assertEqual(classify_risk_tier(79), "VERY_HIGH")
        self.assertEqual(classify_risk_tier(80), "CRITICAL")
        self.assertEqual(classify_risk_tier(100), "CRITICAL")

    def test_safe_clean_token_scores_low_risk(self):
        token_data = {
            "address": "CLEAN_MINT",
            "liquidity_usd": 25000.0,
            "market_cap_usd": 50000.0,  # 50% ratio
            "volume_1h": 40000.0,
            "buys_1h": 150,
            "sells_1h": 80,
            "buys_5m": 25,
            "sells_5m": 12,
        }
        rugcheck_data = {
            "lpLockedPct": 98.0,
            "creatorBalancePct": 0.5,
            "insiderHoldingPct": 4.0,
            "topHolders": [
                {"address": "H1", "pct": 4.0, "isPool": False},
                {"address": "H2", "pct": 3.0, "isPool": False},
            ],
            "mint_authority": None,
            "freeze_authority": None,
            "rugged": False,
            "risks": [],
        }
        # Candles: healthy green candles without long upper wicks
        candles = [
            [1000, 0.010, 0.012, 0.009, 0.011, 10000],
            [1060, 0.011, 0.014, 0.010, 0.013, 12000],
            [1120, 0.013, 0.016, 0.012, 0.015, 15000],
        ]

        result = self.detector.evaluate(token_data, rugcheck_data, candles)

        self.assertLess(result["risk_score"], 25.0)
        self.assertEqual(result["risk_tier"], "LOW")
        self.assertEqual(result["confidence"], "HIGH")
        rejected, reason = self.detector.should_reject(result, rejection_threshold=45.0)
        self.assertFalse(rejected)
        self.assertIsNone(reason)

    def test_zero_liquidity_triggers_maximum_liquidity_risk(self):
        token_data = {
            "address": "RUG_ZERO_LIQ",
            "liquidity_usd": 0.0,
            "market_cap_usd": 10000.0,
        }
        score, reasons, det = self.detector.evaluate_liquidity_risk(token_data)

        self.assertEqual(score, 20.0)
        self.assertTrue(any("Zero or unverified" in r for r in reasons))

    def test_thin_liquidity_to_mc_ratio_scores_risk(self):
        token_data = {
            "address": "THIN_LIQ",
            "liquidity_usd": 3000.0,
            "market_cap_usd": 60000.0,  # 5% ratio (< 8%)
        }
        score, reasons, det = self.detector.evaluate_liquidity_risk(token_data)

        self.assertGreaterEqual(score, 8.0)
        self.assertTrue(any("< 8% of MC" in r for r in reasons))

    def test_whale_concentration_and_sell_pressure(self):
        token_data = {
            "address": "WHALE_DUMP",
            "volume_1h": 100000.0,
            "buys_1h": 200,   # retail buys: 200 small buys
            "sells_1h": 10,   # whale sells: 10 massive sells
        }
        rugcheck_data = {
            "topHolders": [
                {"address": "WHALE_1", "pct": 22.0, "isPool": False},  # > 15%
                {"address": "WHALE_2", "pct": 18.0, "isPool": False},
                {"address": "WHALE_3", "pct": 10.0, "isPool": False},
            ]
        }
        score, reasons, det = self.detector.evaluate_whale_distribution_risk(
            token_data, rugcheck_data
        )

        self.assertGreaterEqual(score, 15.0)
        self.assertTrue(any("Whale distribution pattern" in r for r in reasons))
        self.assertTrue(any("single wallet controls" in r for r in reasons))

    def test_developer_sales_and_high_insider_holding(self):
        token_data = {"address": "DEV_SCAM"}
        rugcheck_data = {
            "creator": "DEV_WALLET_123",
            "creatorBalancePct": 6.5,  # > 5%
            "insiderHoldingPct": 25.0, # > 20%
            "risks": [{"name": "Creator sold tokens", "level": "danger"}],
        }
        score, reasons, det = self.detector.evaluate_developer_risk(
            token_data, rugcheck_data
        )

        self.assertGreaterEqual(score, 18.0)
        self.assertTrue(any("Creator has actively sold" in r for r in reasons))
        self.assertTrue(any("Deployer holds dangerous" in r for r in reasons))
        self.assertTrue(any("Insiders control" in r for r in reasons))

    def test_buy_sell_pressure_decay(self):
        token_data = {
            "address": "MOMENTUM_BLEED",
            "buys_1h": 30,
            "sells_1h": 70,  # 30% buys (< 45%)
            "buys_5m": 2,
            "sells_5m": 20,  # 5m buy ratio = 9% (rapid decay)
        }
        # 3 red candles in a row
        candles = [
            [100, 0.05, 0.051, 0.045, 0.046, 5000],
            [160, 0.046, 0.047, 0.040, 0.041, 6000],
            [220, 0.041, 0.042, 0.035, 0.036, 7000],
        ]
        score, reasons, det = self.detector.evaluate_buy_sell_pressure_risk(
            token_data, candles
        )

        self.assertGreaterEqual(score, 12.0)
        self.assertTrue(any("Sellers dominate" in r for r in reasons))
        self.assertTrue(any("Rapid buy decay" in r for r in reasons))
        self.assertTrue(any("3 consecutive bearish" in r for r in reasons))

    def test_price_momentum_upper_wick_rejection_and_divergence(self):
        token_data = {"address": "EXHAUSTION_MINT"}
        # Candle 1: normal
        # Candle 2: high wick rejection (High: 0.10, Open: 0.05, Close: 0.055, Low: 0.05 -> wick is 0.045 / 0.05 = 90%)
        # and volume collapsed from 50,000 to 10,000
        candles = [
            [100, 0.04, 0.052, 0.038, 0.050, 50000],
            [160, 0.05, 0.100, 0.049, 0.052, 10000],
        ]
        score, reasons, det = self.detector.evaluate_price_momentum_risk(
            token_data, candles
        )

        self.assertGreaterEqual(score, 5.0)
        self.assertTrue(any("Heavy overhead rejection" in r for r in reasons))
        self.assertTrue(any("Bearish volume divergence" in r for r in reasons))

    def test_trading_anomalies_volume_liquidity_ratio(self):
        token_data = {
            "address": "WASH_TRADED",
            "liquidity_usd": 5000.0,
            "volume_1h": 120000.0,  # 24x liquidity (wash trading)
            "buys_1h": 2000,
            "sells_1h": 2000,       # 4000 total txns, avg trade $30
        }
        score, reasons, det = self.detector.evaluate_trading_anomalies_risk(
            token_data
        )

        self.assertGreaterEqual(score, 6.0)
        self.assertTrue(any("Extreme volume/liquidity ratio" in r for r in reasons))

    def test_token_safety_unrevoked_mint_and_freeze(self):
        rugcheck_data = {
            "mint_authority": "DEV_PUBKEY_MINT",
            "freeze_authority": "DEV_PUBKEY_FREEZE",
            "rugged": True,
        }
        score, reasons, det = self.detector.evaluate_token_safety_risk(
            rugcheck_data
        )

        self.assertEqual(score, 5.0)  # Capped at max 5
        self.assertTrue(any("confirmed rugged" in r for r in reasons))
        self.assertTrue(any("Active mint authority" in r for r in reasons))
        self.assertTrue(any("Active freeze authority" in r for r in reasons))

    def test_missing_data_does_not_assume_safe(self):
        # Empty inputs
        result = self.detector.evaluate({"address": "MYSTERY_TOKEN"})

        self.assertEqual(result["confidence"], "LOW")
        # Missing dev and safety audits add conservative baseline risk points
        self.assertGreater(result["risk_score"], 0)
        self.assertTrue(any("unavailable" in r for r in result["warning_signals"]))

    def test_should_reject_critical_and_high_risk_tokens(self):
        high_risk_eval = {
            "risk_score": 68.5,
            "risk_tier": "VERY_HIGH",
            "warning_signals": ["Zero or unverified pool liquidity", "Deployer holds dangerous 8%"],
        }
        rejected, reason = self.detector.should_reject(high_risk_eval, rejection_threshold=45.0)

        self.assertTrue(rejected)
        self.assertIn("VERY_HIGH risk: 68.5/100", reason)
        self.assertIn("Zero or unverified pool liquidity", reason)

    def test_dexscreener_negative_price_change_scores_momentum_risk(self):
        token_data = {
            "address": "BLEEDING_TOKEN",
            "price_change_1h": -18.5,
            "price_change_m5": -6.2,
        }
        score, reasons, det = self.detector.evaluate_price_momentum_risk(token_data)
        self.assertGreaterEqual(score, 6.0)
        self.assertTrue(any("Severe 1-hour price decline" in r for r in reasons))
        self.assertTrue(any("Sharp 5-minute price decline" in r for r in reasons))

    def test_order_asymmetry_at_memecoin_clip_sizes(self):
        token_data = {
            "address": "MEMECOIN_DISTRIBUTION",
            "volume_1h": 15000.0,
            "buys_1h": 100,  # 100 buys
            "sells_1h": 50,  # 50 sells -> avg sell is 2x avg buy
        }
        score, reasons, det = self.detector.evaluate_whale_distribution_risk(token_data)
        self.assertGreaterEqual(score, 4.0)
        self.assertTrue(any("Bearish order asymmetry" in r or "Whale distribution pattern" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
