import unittest

from backtest_engine import calculate_exit


def candle(t, open_, high, low, close, volume=1000):
    return [t, open_, high, low, close, volume]


class TestBacktestEngineExits(unittest.TestCase):

    def test_fixed_stop_loss(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.00, 1.02, 0.84, 0.90),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 0.85)
        self.assertEqual(reason, "STOP_LOSS")

    def test_trailing_stop_after_price_rises(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.00, 1.40, 0.98, 1.35),
            candle(3, 1.30, 1.32, 1.18, 1.22),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertAlmostEqual(price, 1.19)
        self.assertEqual(reason, "TRAILING_STOP")

    def test_gap_through_fixed_stop(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 0.80, 0.90, 0.75, 0.85),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 0.80)
        self.assertEqual(reason, "GAP_STOP_LOSS")

    def test_gap_through_trailing_stop(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.00, 1.40, 0.98, 1.35),
            candle(3, 1.10, 1.15, 1.05, 1.08),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 1.10)
        self.assertEqual(reason, "GAP_TRAILING_STOP")

    def test_take_profit(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.00, 1.55, 0.95, 1.50),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 1.50)
        self.assertEqual(reason, "TAKE_PROFIT")

    def test_gap_above_take_profit(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.60, 1.70, 1.55, 1.65),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 1.50)
        self.assertEqual(reason, "TAKE_PROFIT")

    def test_stop_wins_when_stop_and_target_both_hit(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.00, 1.60, 0.80, 1.20),
        ]
        _, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(price, 0.85)
        self.assertEqual(reason, "STOP_LOSS")

    def test_end_of_data(self):
        candles = [
            candle(1, 1.00, 1.05, 0.95, 1.00),
            candle(2, 1.02, 1.10, 0.98, 1.06),
            candle(3, 1.06, 1.12, 1.01, 1.08),
        ]
        timestamp, price, reason = calculate_exit(candles, 0, 1.00)
        self.assertEqual(timestamp, 3)
        self.assertEqual(price, 1.08)
        self.assertEqual(reason, "END_OF_DATA")


if __name__ == "__main__":
    unittest.main()
