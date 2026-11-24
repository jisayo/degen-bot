import unittest
from unittest.mock import patch

from rug_detector import check_rug_risk


TOKEN = {
    "address": "So11111111111111111111111111111111111111112",
    "liquidity_usd": 20000,
    "volume_1h": 50000,
    "buys_1h": 100,
    "sells_1h": 80,
}


class TestRugDetector(unittest.TestCase):

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_low_risk_can_pass(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertTrue(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 58, "risks": []
    })
    def test_score_58_blocks_trade(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertEqual(result["risk_score"], 58)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": True})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_rugged_token_blocked(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertEqual(result["risk_score"], 100)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", side_effect=ConnectionError())
    def test_api_failure_blocks(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": None, "risks": []
    })
    def test_missing_score_blocks(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_low_liquidity_alone_does_not_block(self, *_):
        token = {**TOKEN, "liquidity_usd": 100}
        result = check_rug_risk(token)
        self.assertTrue(result["trade_allowed"])
        self.assertLess(result["risk_score"], 30)

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_negative_liquidity_blocks(self, *_):
        token = {**TOKEN, "liquidity_usd": -1}
        result = check_rug_risk(token)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_zero_liquidity_blocks(self, *_):
        token = {**TOKEN, "liquidity_usd": 0}
        result = check_rug_risk(token)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={"rugged": False})
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_missing_market_data_blocks(self, *_):
        token = {**TOKEN}
        del token["volume_1h"]
        result = check_rug_risk(token)
        self.assertFalse(result["trade_allowed"])

    @patch("rug_detector.get_rugcheck_report", return_value={
        "rugged": False,
        "topHolders": [
            {"address": "WHALE_WALLET", "pct": 85.0, "isPool": False},
        ],
    })
    @patch("rug_detector.summarise_risk", return_value={
        "risk_score": 1, "risks": []
    })
    def test_concentrated_top_holder_supply_blocks_trade(self, *_):
        result = check_rug_risk(TOKEN)
        self.assertFalse(result["trade_allowed"])
        self.assertGreaterEqual(result["risk_score"], 60)
        self.assertTrue(any("Single holder owns" in r for r in result["risks"]))


if __name__ == "__main__":
    unittest.main()
