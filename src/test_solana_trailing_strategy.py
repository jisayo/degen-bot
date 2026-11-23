import unittest
from unittest.mock import patch, MagicMock

from solana_trailing_strategy import SolanaTrailingStopStrategy, calculate_solana_trailing_exit
from jito_executor import JitoBundleExecutor, DEFAULT_SLIPPAGE_TOLERANCE


class TestSolanaTrailingStopStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = SolanaTrailingStopStrategy(
            max_positions=3,
            trailing_stop_pct=0.15,
            slippage_tolerance=0.15,
        )

    def test_max_three_simultaneous_positions_limit(self):
        self.assertEqual(self.strategy.max_positions, 3)

    def test_ignore_historical_ath_starts_from_activation_entry(self):
        # Token had historical ATH of $10.00 before our entry at $1.00
        position = {
            "token": "TEST_TOKEN",
            "entry_price": 1.00,
            "actual_entry_price": 1.01,
            "highest_price": 1.01,  # Post-activation peak initialized to entry
            "quantity": 100.0,
        }
        live_prices = {"TEST_TOKEN": 1.05}

        exits = self.strategy.evaluate_and_update_positions([position], live_prices)

        # Peak is updated to $1.05 (NOT historical $10.00)
        self.assertEqual(position["highest_price"], 1.05)
        # Stop trigger is locked at 15% below $1.05 = $0.8925
        self.assertAlmostEqual(position["stop_trigger_price"], 1.05 * 0.85, places=4)
        # No exit triggered
        self.assertEqual(len(exits), 0)

    def test_stop_trigger_moves_upward_with_new_highs(self):
        position = {
            "token": "TEST_TOKEN",
            "entry_price": 1.00,
            "actual_entry_price": 1.00,
            "highest_price": 1.00,
            "quantity": 100.0,
        }

        # Price rises to $1.20
        self.strategy.evaluate_and_update_positions([position], {"TEST_TOKEN": 1.20})
        self.assertAlmostEqual(position["highest_price"], 1.20)
        self.assertAlmostEqual(position["stop_trigger_price"], 1.20 * 0.85, places=4)  # $1.02

        # Price hits new high of $2.00
        self.strategy.evaluate_and_update_positions([position], {"TEST_TOKEN": 2.00})
        self.assertAlmostEqual(position["highest_price"], 2.00)
        self.assertAlmostEqual(position["stop_trigger_price"], 2.00 * 0.85, places=4)  # $1.70

    def test_ignores_pullbacks_smaller_than_15_percent(self):
        position = {
            "token": "TEST_TOKEN",
            "entry_price": 1.00,
            "actual_entry_price": 1.00,
            "highest_price": 2.00,  # Peak is $2.00, stop trigger is $1.70
            "quantity": 100.0,
        }

        # Pullback to $1.80 (10% drop, smaller than 15%)
        exits = self.strategy.evaluate_and_update_positions([position], {"TEST_TOKEN": 1.80})
        self.assertEqual(len(exits), 0)
        self.assertEqual(position["highest_price"], 2.00)  # Peak remains $2.00

        # Pullback to $1.72 (14% drop, still smaller than 15%)
        exits = self.strategy.evaluate_and_update_positions([position], {"TEST_TOKEN": 1.72})
        self.assertEqual(len(exits), 0)

    def test_triggers_exit_when_price_drops_15_percent_from_peak(self):
        position = {
            "token": "TEST_TOKEN",
            "entry_price": 1.00,
            "actual_entry_price": 1.00,
            "highest_price": 2.00,  # Peak is $2.00, stop trigger is $1.70
            "quantity": 100.0,
        }

        # Price drops to $1.69 (15.5% drop from peak of $2.00)
        exits = self.strategy.evaluate_and_update_positions([position], {"TEST_TOKEN": 1.69})

        self.assertEqual(len(exits), 1)
        exit_event = exits[0]
        self.assertEqual(exit_event["token"], "TEST_TOKEN")
        self.assertEqual(exit_event["current_price"], 1.69)
        self.assertEqual(exit_event["post_activation_peak"], 2.00)
        self.assertIn("Trailing stop triggered", exit_event["reason"])

    def test_jito_protected_bundle_execution_with_15_percent_slippage(self):
        executor = JitoBundleExecutor(slippage_tolerance=0.15)
        self.assertEqual(executor.slippage_tolerance, 0.15)

        res = executor.execute_trailing_stop_sell(
            token_mint="MINT_XYZ",
            token_amount=1000.0,
            current_price_usd=1.70,
            post_activation_peak_usd=2.00,
        )

        self.assertTrue(res["success"])
        details = res["details"]
        self.assertEqual(details["slippage_tolerance_pct"], 15.0)
        self.assertEqual(details["mev_protection"], "JITO_PRIVATE_BUNDLE (Mempool Bypassed)")
        self.assertAlmostEqual(details["expected_proceeds_usd"], 1700.0)
        # Min proceeds accounts for 15% slippage = $1,700 * 0.85 = $1,445.00
        self.assertAlmostEqual(details["min_guaranteed_proceeds_usd"], 1445.0)

    @patch("requests.get")
    def test_fetch_live_dexscreener_prices(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{
            "chainId": "solana",
            "priceUsd": "0.045",
            "liquidity": {"usd": "15000"},
        }]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        prices = self.strategy.fetch_live_dexscreener_prices(["TOKEN_XYZ"])
        self.assertEqual(prices.get("TOKEN_XYZ"), 0.045)

    def test_calculate_solana_trailing_exit_stop_loss(self):
        candles = [
            [100, 1.00, 1.05, 0.95, 1.00, 5000],
            [101, 1.00, 1.02, 0.84, 0.90, 5000],
        ]
        t, price, reason, peak = calculate_solana_trailing_exit(candles, 1.00, 0.15)
        self.assertEqual(t, 101)
        self.assertAlmostEqual(price, 0.85)
        self.assertEqual(reason, "STOP_LOSS")
        self.assertEqual(peak, 1.00)

    def test_calculate_solana_trailing_exit_trailing_stop(self):
        candles = [
            [100, 1.00, 1.05, 0.95, 1.00, 5000],
            [101, 1.00, 2.00, 0.98, 1.90, 5000],  # Peak moves to 2.00, stop moves to 1.70
            [102, 1.90, 1.95, 1.68, 1.70, 5000],  # Low hits 1.68 <= 1.70 -> triggers trailing stop
        ]
        t, price, reason, peak = calculate_solana_trailing_exit(candles, 1.00, 0.15)
        self.assertEqual(t, 102)
        self.assertAlmostEqual(price, 1.70)
        self.assertEqual(reason, "TRAILING_TAKE_PROFIT")
        self.assertEqual(peak, 2.00)

    def test_calculate_solana_trailing_exit_gap_down(self):
        candles = [
            [100, 1.00, 1.05, 0.95, 1.00, 5000],
            [101, 0.80, 0.85, 0.75, 0.82, 5000],  # Open is 0.80 <= 0.85
        ]
        t, price, reason, peak = calculate_solana_trailing_exit(candles, 1.00, 0.15)
        self.assertEqual(t, 101)
        self.assertEqual(price, 0.80)
        self.assertEqual(reason, "GAP_STOP_LOSS")


if __name__ == "__main__":
    unittest.main()
