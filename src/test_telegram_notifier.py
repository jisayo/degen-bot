import unittest
from unittest.mock import patch, MagicMock
import telegram_notifier


class TestTelegramNotifier(unittest.TestCase):

    def test_not_configured_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(telegram_notifier.is_configured())
            self.assertFalse(telegram_notifier.send_message("Hello"))

    def test_configured_when_env_present(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:ABC", "TELEGRAM_CHAT_ID": "456"}):
            self.assertTrue(telegram_notifier.is_configured())

    @patch("requests.post")
    def test_send_message_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"}):
            res = telegram_notifier.send_message("Test message")
            self.assertTrue(res)
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            self.assertIn("test_token", call_url)
            call_json = mock_post.call_args[1]["json"]
            self.assertEqual(call_json["chat_id"], "12345")
            self.assertEqual(call_json["text"], "Test message")

    @patch("requests.post")
    def test_notify_position_opened(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"}):
            res = telegram_notifier.notify_position_opened(
                token="So11111111111111111111111111111111111111112",
                symbol="SOLMEME",
                entry_price=0.0042,
                trade_size_usd=10.0,
                market_cap=50000,
                liquidity=12000,
                pair_url="https://dexscreener.com/solana/abc",
            )
            self.assertTrue(res)
            call_json = mock_post.call_args[1]["json"]
            self.assertIn("Position Opened", call_json["text"])
            self.assertIn("$SOLMEME", call_json["text"])
            self.assertIn("0.0042", call_json["text"])

    @patch("requests.post")
    def test_notify_position_closed_profit(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"}):
            exit_data = {
                "token": "Token123",
                "symbol": "DOGE",
                "reason": "TRAILING_TAKE_PROFIT",
                "entry_price": 0.010,
                "exit_price": 0.025,
                "pnl": 15.0,
                "peak_gain_pct": 180.0,
                "balance": 65.0,
            }
            res = telegram_notifier.notify_position_closed(exit_data)
            self.assertTrue(res)
            call_json = mock_post.call_args[1]["json"]
            self.assertIn("[TAKE PROFIT]", call_json["text"])
            self.assertIn("+180.00%", call_json["text"])
            self.assertIn("TRAILING_TAKE_PROFIT", call_json["text"])

    @patch("requests.post")
    def test_notify_position_closed_stop_loss(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "12345"}):
            exit_data = {
                "token": "Token123",
                "symbol": "DOGE",
                "reason": "STOP_LOSS",
                "entry_price": 0.010,
                "exit_price": 0.0085,
                "pnl": -1.5,
                "balance": 48.5,
            }
            res = telegram_notifier.notify_position_closed(exit_data)
            self.assertTrue(res)
            call_json = mock_post.call_args[1]["json"]
            self.assertIn("[STOP LOSS]", call_json["text"])
            self.assertIn("STOP_LOSS", call_json["text"])


if __name__ == "__main__":
    unittest.main()
