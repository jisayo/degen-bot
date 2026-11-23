"""
telegram_notifier.py - Real-Time Telegram Alerts for DegenBot.

Sends instant notifications for:
- Discovered eligible memecoin opportunities
- Opened positions (Paper Trading $0 risk)
- Closed positions (Trailing Take-Profit, Stop-Loss, Peak Gain metrics)

Configured via environment variables:
  TELEGRAM_BOT_TOKEN: Bot API token from @BotFather
  TELEGRAM_CHAT_ID: Telegram user or channel ID to receive alerts
"""

import os
import logging
from typing import Optional, Dict, Any
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("telegram_notifier")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def get_telegram_config() -> tuple[Optional[str], Optional[str]]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    return token, chat_id


def is_configured() -> bool:
    token, chat_id = get_telegram_config()
    return bool(token and chat_id)


def send_message(text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
    """Send an HTML/Markdown formatted message to Telegram."""
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        return False

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        logger.warning(f"Telegram API error {response.status_code}: {response.text}")
        return False
    except Exception as exc:
        logger.warning(f"Failed to deliver Telegram notification: {exc}")
        return False


def notify_position_opened(
    token: str,
    symbol: str,
    entry_price: float,
    trade_size_usd: float,
    market_cap: float = 0.0,
    liquidity: float = 0.0,
    pair_url: str = "",
) -> bool:
    """Send alert when DegenBot opens a new paper position."""
    display_symbol = symbol.upper() if symbol and symbol != "UNKNOWN" else "MEME"
    chart_link = f'\n🔗 <a href="{pair_url}">View on DexScreener</a>' if pair_url else ""

    text = (
        f"🟢 <b>[PAPER TRADE] Position Opened</b>\n\n"
        f"🪙 <b>Token:</b> ${display_symbol}\n"
        f"📍 <b>Address:</b> <code>{token}</code>\n"
        f"💵 <b>Entry Price:</b> ${entry_price:.8g}\n"
        f"💰 <b>Size:</b> ${trade_size_usd:.2f} (Simulated)\n"
    )

    if market_cap > 0:
        text += f"📊 <b>Market Cap:</b> ${market_cap:,.0f}\n"
    if liquidity > 0:
        text += f"💧 <b>Liquidity:</b> ${liquidity:,.0f}\n"

    text += (
        f"🎯 <b>Strategy:</b> Solana Trailing Stop (15% Ratchet)\n"
        f"{chart_link}"
    )
    return send_message(text)


def notify_position_closed(exit_trade: Dict[str, Any]) -> bool:
    """Send alert when DegenBot closes a position."""
    token = exit_trade.get("token", "Unknown")
    symbol = exit_trade.get("symbol", "").upper() or "MEME"
    reason = exit_trade.get("reason", "EXIT")
    entry_price = float(exit_trade.get("entry_price", 0.0))
    exit_price = float(exit_trade.get("exit_price", 0.0))
    pnl = float(exit_trade.get("pnl", 0.0))
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
    peak_gain_pct = exit_trade.get("peak_gain_pct")
    balance = exit_trade.get("balance")

    if "PROFIT" in reason or pnl > 0:
        header = "🎉 <b>[TAKE PROFIT] Position Closed</b>"
        pnl_emoji = "🟢"
    else:
        header = "🛑 <b>[STOP LOSS] Position Closed</b>"
        pnl_emoji = "🔴"

    text = (
        f"{header}\n\n"
        f"🪙 <b>Token:</b> ${symbol}\n"
        f"📍 <b>Address:</b> <code>{token}</code>\n"
        f"📥 <b>Entry:</b> ${entry_price:.8g} ➔ 📤 <b>Exit:</b> ${exit_price:.8g}\n"
        f"{pnl_emoji} <b>Net PnL:</b> ${pnl:+.4f} ({pnl_pct:+.2f}%)\n"
    )

    if peak_gain_pct is not None:
        text += f"📈 <b>Post-Activation Peak:</b> +{peak_gain_pct:.2f}%\n"

    text += f"⚡ <b>Exit Reason:</b> <code>{reason}</code>\n"

    if balance is not None:
        text += f"💼 <b>Paper Balance:</b> ${float(balance):.2f}\n"

    return send_message(text)


def notify_opportunity_found(token_data: Dict[str, Any]) -> bool:
    """Send alert when a new eligible token passes all pre-trade filters."""
    symbol = token_data.get("symbol", "").upper() or "MEME"
    address = token_data.get("address", "")
    age = token_data.get("token_age_minutes", 0.0)
    liquidity = token_data.get("liquidity_usd", 0.0)
    market_cap = token_data.get("market_cap_usd", 0.0)
    score = (token_data.get("opportunity") or {}).get("opportunity_score", 0)
    pair_url = token_data.get("pair_url", "")
    chart_link = f'\n🔗 <a href="{pair_url}">DexScreener Link</a>' if pair_url else ""

    text = (
        f"⚡ <b>New Memecoin Discovered</b>\n\n"
        f"🪙 <b>Symbol:</b> ${symbol}\n"
        f"⏱️ <b>Age:</b> {age:.1f} minutes\n"
        f"💧 <b>Liquidity:</b> ${liquidity:,.0f}\n"
        f"📊 <b>Market Cap:</b> ${market_cap:,.0f}\n"
        f"⭐ <b>Opportunity Score:</b> {score}/100\n"
        f"✅ <b>Status:</b> Pre-trade gates passed (Paper eligible)\n"
        f"{chart_link}"
    )
    return send_message(text)


if __name__ == "__main__":
    import sys
    print("Testing Telegram Notifier configuration...")
    token, chat_id = get_telegram_config()
    print(f"Token configured: {'YES' if token else 'NO'}")
    print(f"Chat ID configured: {'YES' if chat_id else 'NO'}")

    if not is_configured():
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file to enable alerts.")
        sys.exit(0)

    success = send_message("🤖 <b>DegenBot Online!</b>\nTelegram alerts successfully connected to your server.")
    if success:
        print("Success! Test alert sent to your Telegram.")
    else:
        print("Failed to send test message. Check your bot token and chat ID.")
