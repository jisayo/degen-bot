import unittest

from staged_backtest import calculate_staged_exits


class TestStagedBacktest(unittest.TestCase):

    def setUp(self):
        # timestamp, open, high, low, close, volume
        self.entry = [0, 1.00, 1.00, 1.00, 1.00, 100]

    def test_first_target_sells_half(self):
        candles = [
            self.entry,
            [1, 1.00, 1.60, 0.95, 1.40, 100],
            [2, 1.40, 1.40, 1.30, 1.35, 100],
        ]

        exits = calculate_staged_exits(candles, 0, 1.00)

        self.assertEqual(exits[0][2], 0.50)
        self.assertEqual(exits[0][3], "TAKE_PROFIT_1")
        self.assertAlmostEqual(sum(e[2] for e in exits), 1.0)

    def test_both_targets_leave_final_quarter(self):
        candles = [
            self.entry,
            [1, 1.00, 1.60, 0.95, 1.50, 100],
            [2, 1.50, 2.10, 1.40, 2.00, 100],
            [3, 2.00, 2.05, 1.70, 1.80, 100],
        ]

        exits = calculate_staged_exits(candles, 0, 1.00)

        self.assertEqual(
            [e[3] for e in exits],
            ["TAKE_PROFIT_1", "TAKE_PROFIT_2", "STOP_OR_TRAILING"],
        )
        self.assertAlmostEqual(exits[0][2], 0.50)
        self.assertAlmostEqual(exits[1][2], 0.25)
        self.assertAlmostEqual(exits[2][2], 0.25)
        self.assertAlmostEqual(sum(e[2] for e in exits), 1.0)

    def test_stop_wins_when_stop_and_target_both_hit(self):
        candles = [
            self.entry,
            [1, 1.00, 1.60, 0.80, 1.20, 100],
        ]

        exits = calculate_staged_exits(candles, 0, 1.00)

        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0][3], "STOP_LOSS")
        self.assertAlmostEqual(exits[0][2], 1.0)
        self.assertAlmostEqual(exits[0][1], 0.85)

    def test_remaining_position_closes_at_end_of_data(self):
        candles = [
            self.entry,
            [1, 1.00, 1.20, 0.95, 1.10, 100],
        ]

        exits = calculate_staged_exits(candles, 0, 1.00)

        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0][3], "END_OF_DATA")
        self.assertAlmostEqual(exits[0][2], 1.0)


    def test_gap_below_stop_exits_at_candle_open(self):
        candles = [
            self.entry,
            [1, 0.80, 1.60, 0.75, 1.20, 100],
        ]

        exits = calculate_staged_exits(candles, 0, 1.00)

        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0][3], "GAP_STOP")
        self.assertAlmostEqual(exits[0][1], 0.80)
        self.assertAlmostEqual(exits[0][2], 1.0)


if __name__ == "__main__":
    unittest.main()
