import unittest
from unittest.mock import patch

import main


class TestMainPaperEntries(unittest.TestCase):

    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_eligible_token_opens_paper_position(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open
    ):
        mock_positions.side_effect = [[], []]
        mock_scan.return_value = [{
            "address": "TOKEN_A",
            "price_usd": 0.01,
            "paper_eligible": True,
        }]

        main.run_cycle()

        mock_open.assert_called_once_with("TOKEN_A", 0.01)

    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_ineligible_token_is_not_opened(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open
    ):
        mock_positions.side_effect = [[], []]
        mock_scan.return_value = [{
            "address": "TOKEN_BAD",
            "price_usd": 0.01,
            "paper_eligible": False,
        }]

        main.run_cycle()

        mock_open.assert_not_called()

    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_existing_token_is_not_opened_twice(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open
    ):
        existing = [{"token": "TOKEN_A"}]
        mock_positions.side_effect = [existing, existing]
        mock_scan.return_value = [{
            "address": "TOKEN_A",
            "price_usd": 0.01,
            "paper_eligible": True,
        }]

        main.run_cycle()

        mock_open.assert_not_called()

    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_never_exceeds_max_open_positions(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open
    ):
        mock_positions.side_effect = [[], []]
        mock_scan.return_value = [
            {
                "address": f"TOKEN_{i}",
                "price_usd": 0.01,
                "paper_eligible": True,
            }
            for i in range(5)
        ]

        main.run_cycle()

        self.assertEqual(mock_open.call_count, 3)

    @patch.object(main.trailing_strategy, "execute_exits")
    @patch.object(main.trailing_strategy, "evaluate_and_update_positions")
    @patch("main.load_positions")
    def test_monitor_positions_delegates_to_trailing_strategy(
        self, mock_load, mock_eval, mock_exec
    ):
        positions = [{"token": "SOL_TOKEN", "actual_entry_price": 1.0, "quantity": 100}]
        mock_load.return_value = positions
        mock_eval.return_value = [{"token": "SOL_TOKEN", "reason": "Trailing stop"}]
        mock_exec.return_value = [{"success": True}]

        res = main.monitor_positions({"SOL_TOKEN": 0.84})

        mock_eval.assert_called_once_with(positions, {"SOL_TOKEN": 0.84})
        mock_exec.assert_called_once_with([{"token": "SOL_TOKEN", "reason": "Trailing stop"}])
        self.assertEqual(len(res), 1)


if __name__ == "__main__":
    unittest.main()
