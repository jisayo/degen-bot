import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paper_trader as pt


class TestPaperTrader(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.patches = [
            patch.object(pt, "DATA_DIR", self.root),
            patch.object(pt, "TRADE_LOG", self.root / "trades.csv"),
            patch.object(pt, "STATE_FILE", self.root / "state.json"),
            patch.object(pt, "POSITIONS_FILE", self.root / "positions.json"),
        ]

        for item in self.patches:
            item.start()

        pt.initialise()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    # Existing tests

    def test_profitable_trade(self):
        trade = pt.simulate_trade("TEST", 1.00, 1.10, 50)
        self.assertGreater(trade["pnl"], 0)

    def test_losing_trade(self):
        trade = pt.simulate_trade("TEST", 1.00, 0.90, 50)
        self.assertLess(trade["pnl"], 0)

    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            pt.simulate_trade("TEST", 0, 1.10, 50)

    def test_insufficient_balance(self):
        with self.assertRaises(ValueError):
            pt.simulate_trade("TEST", 1.00, 1.10, 1)

    def test_execution_updates_balance_and_log(self):
        trade = pt.execute_paper_trade("TEST", 1.00, 1.10)

        self.assertAlmostEqual(
            pt.load_balance(), trade["balance"], places=4
        )

        with pt.TRADE_LOG.open() as file:
            rows = file.readlines()

        self.assertEqual(len(rows), 2)

    # New lifecycle tests

    def test_open_position_is_persisted(self):
        position = pt.open_position("TOKEN_A", 1.00)

        positions = pt.load_positions()

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["token"], "TOKEN_A")
        self.assertEqual(position["entry_price"], 1.00)

    def test_duplicate_open_position_is_rejected(self):
        pt.open_position("TOKEN_A", 1.00)

        with self.assertRaises(ValueError):
            pt.open_position("TOKEN_A", 1.10)

    def test_invalid_entry_price_is_rejected(self):
        with self.assertRaises(ValueError):
            pt.open_position("TOKEN_A", 0)

        self.assertEqual(pt.load_positions(), [])

    def test_close_position_updates_balance_and_log(self):
        pt.open_position("TOKEN_A", 1.00)
        trade = pt.close_position("TOKEN_A", 1.20)

        self.assertGreater(trade["pnl"], 0)
        self.assertAlmostEqual(
            pt.load_balance(), trade["balance"], places=4
        )
        self.assertEqual(pt.load_positions(), [])

        with pt.TRADE_LOG.open(newline="") as file:
            rows = list(csv.DictReader(file))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["token"], "TOKEN_A")

    def test_closing_unknown_position_is_rejected(self):
        with self.assertRaises(ValueError):
            pt.close_position("UNKNOWN", 1.00)

    def test_invalid_exit_price_is_rejected(self):
        pt.open_position("TOKEN_A", 1.00)

        with self.assertRaises(ValueError):
            pt.close_position("TOKEN_A", float("nan"))

        self.assertEqual(len(pt.load_positions()), 1)


    def test_first_take_profit_sells_half_and_keeps_position_open(self):
        pt.open_position("TP_TOKEN", 1.00)

        closed = pt.monitor_positions({"TP_TOKEN": 1.52})

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "Take profit 1 (+50%)")
        positions = pt.load_positions()
        self.assertEqual(len(positions), 1)
        self.assertTrue(positions[0]["first_take_profit_done"])
        self.assertAlmostEqual(
            positions[0]["quantity"],
            positions[0]["original_quantity"] * 0.5,
        )

    def test_second_target_sells_quarter_and_activates_trailing_stop(self):
        pt.open_position("TP2_TOKEN", 1.00)

        closed = pt.monitor_positions({"TP2_TOKEN": 2.10})

        self.assertEqual(len(closed), 2)
        self.assertEqual(
            [trade["reason"] for trade in closed],
            ["Take profit 1 (+50%)", "Take profit 2 (+100%)"],
        )
        positions = pt.load_positions()
        self.assertEqual(len(positions), 1)
        self.assertTrue(positions[0]["second_take_profit_done"])
        self.assertTrue(positions[0]["trailing_stop_active"])
        self.assertAlmostEqual(
            positions[0]["quantity"],
            positions[0]["original_quantity"] * 0.25,
        )

    def test_trailing_stop_closes_final_quarter_after_second_target(self):
        pt.open_position("TRAIL_TOKEN", 1.00)
        pt.monitor_positions({"TRAIL_TOKEN": 1.52})
        pt.monitor_positions({"TRAIL_TOKEN": 2.10})

        positions = pt.load_positions()
        self.assertTrue(positions[0]["trailing_stop_active"])

        closed = pt.monitor_positions({"TRAIL_TOKEN": 1.70})

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "Trailing stop")
        self.assertEqual(pt.load_positions(), [])

    def test_stop_loss_closes_position(self):
        pt.open_position("SL_TOKEN", 1.00)

        closed = pt.monitor_positions({"SL_TOKEN": 0.85})

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "Stop loss")
        self.assertEqual(pt.load_positions(), [])

    def test_trailing_stop_is_not_active_before_second_target(self):
        pt.open_position("TRAIL_TOKEN", 1.00)

        pt.monitor_positions({"TRAIL_TOKEN": 1.20})
        positions = pt.load_positions()
        self.assertAlmostEqual(positions[0]["highest_price"], 1.20)

        closed = pt.monitor_positions({"TRAIL_TOKEN": 1.00})

        self.assertEqual(closed, [])
        self.assertEqual(len(pt.load_positions()), 1)

    def test_peak_price_persists_between_checks(self):
        pt.open_position("PEAK_TOKEN", 1.00)

        pt.monitor_positions({"PEAK_TOKEN": 1.10})
        pt.monitor_positions({"PEAK_TOKEN": 1.19})

        positions = pt.load_positions()
        self.assertAlmostEqual(positions[0]["highest_price"], 1.19)



    def test_partial_exit_accounts_for_fees_and_balance(self):
        position = pt.open_position("ACCOUNTING_TOKEN", 1.00)
        starting_balance = pt.load_balance()

        closed = pt.monitor_positions({"ACCOUNTING_TOKEN": 1.52})

        self.assertEqual(len(closed), 1)
        trade = closed[0]
        quantity_sold = position["original_quantity"] * 0.5
        proceeds = quantity_sold * 1.52 * (1 - pt.SLIPPAGE_RATE)
        expected_fees = (
            position["entry_fee"] * 0.5
            + proceeds * pt.FEE_RATE
        )
        expected_pnl = (
            proceeds - position["trade_size"] * 0.5 - expected_fees
        )

        self.assertAlmostEqual(trade["pnl"], round(expected_pnl, 4), places=4)
        self.assertAlmostEqual(
            pt.load_balance(),
            round(starting_balance + expected_pnl, 4),
            places=4,
        )
        self.assertEqual(len(pt.load_positions()), 1)


if __name__ == "__main__":
    unittest.main()