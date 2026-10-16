import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paper_trader as pt


class TestPaperTrader(unittest.TestCase):

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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with (
                patch.object(pt, "DATA_DIR", root),
                patch.object(pt, "TRADE_LOG", root / "trades.csv"),
                patch.object(pt, "STATE_FILE", root / "state.json"),
            ):
                pt.initialise()
                trade = pt.execute_paper_trade("TEST", 1.00, 1.10)

                self.assertAlmostEqual(
                    pt.load_balance(), trade["balance"], places=4
                )

                with pt.TRADE_LOG.open() as file:
                    rows = file.readlines()

                self.assertEqual(len(rows), 2)  # Header + one trade


if __name__ == "__main__":
    unittest.main()
