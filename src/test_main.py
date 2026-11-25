import unittest
from unittest.mock import patch, MagicMock
import threading
import time

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

    @patch("main.get_cooldown_tokens")
    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_cooldown_token_is_not_reopened(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open, mock_cooldown
    ):
        mock_positions.side_effect = [[], []]
        mock_cooldown.return_value = {"TOKEN_COOLDOWN"}
        mock_scan.return_value = [{
            "address": "TOKEN_COOLDOWN",
            "price_usd": 0.01,
            "paper_eligible": True,
        }]

        main.run_cycle()

        mock_open.assert_not_called()

    @patch("main.observer.observe_candidate")
    @patch("main.open_position")
    @patch("main.load_positions")
    @patch("main.scan_tokens")
    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    def test_high_dump_risk_token_is_blocked_by_gating(
        self, mock_monitor, mock_prices, mock_scan,
        mock_positions, mock_open, mock_observe
    ):
        mock_positions.side_effect = [[], []]
        mock_scan.return_value = [{
            "address": "TOKEN_DUMP_RISK",
            "price_usd": 0.01,
            "paper_eligible": True,
        }]
        mock_observe.return_value = {
            "risk_score": 65.0,
            "risk_tier": "VERY_HIGH",
            "warning_signals": ["Severe dump risk detected"],
        }

        main.run_cycle()

        mock_open.assert_not_called()

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


class TestFastPoller(unittest.TestCase):

    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    @patch("main.load_positions")
    def test_position_watcher_calls_monitor_when_positions_exist(
        self, mock_load, mock_monitor, mock_prices
    ):
        """
        position_watcher should call monitor_positions when there are open
        positions and prices are available.  We run it in a thread and kill
        it after one iteration via a stop event simulated by a side_effect.
        """
        mock_load.return_value = [{"token": "FAST_TOKEN"}]
        mock_prices.return_value = {"FAST_TOKEN": 0.50}
        mock_monitor.return_value = []

        # Run watcher long enough for one iteration (interval is 15 s but we
        # patch sleep so it returns immediately).
        stop_event = threading.Event()

        original_sleep = time.sleep

        call_count = [0]

        def fake_sleep(secs):
            call_count[0] += 1
            if call_count[0] >= 2:
                stop_event.set()
            original_sleep(0)

        with patch("main.time.sleep", side_effect=fake_sleep):
            t = threading.Thread(target=main.position_watcher, daemon=True)
            t.start()
            stop_event.wait(timeout=5)

        mock_monitor.assert_called()

    @patch("main.fetch_position_prices")
    @patch("main.monitor_positions")
    @patch("main.load_positions")
    def test_position_watcher_skips_monitor_with_no_positions(
        self, mock_load, mock_monitor, mock_prices
    ):
        """position_watcher must NOT call monitor_positions when no open positions."""
        mock_load.return_value = []
        mock_prices.return_value = {}
        mock_monitor.return_value = []

        stop_event = threading.Event()
        call_count = [0]

        def fake_sleep(secs):
            call_count[0] += 1
            if call_count[0] >= 2:
                stop_event.set()

        with patch("main.time.sleep", side_effect=fake_sleep):
            t = threading.Thread(target=main.position_watcher, daemon=True)
            t.start()
            stop_event.wait(timeout=5)

        mock_monitor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
