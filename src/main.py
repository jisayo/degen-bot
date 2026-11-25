import time
import requests

from scanner import scan_tokens
from paper_trader import (
    initialise,
    load_positions,
    open_position,
    get_cooldown_tokens,
)
from dump_observer import observer
from solana_trailing_strategy import SolanaTrailingStopStrategy
from telegram_notifier import (
    notify_opportunity_found,
    notify_position_opened,
    notify_position_closed,
)

PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"

def to_float(value):
    try:
        number = float(value)
        return number if number >= 0 and number < float("inf") else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0
TIMEOUT = 15
SCAN_INTERVAL = 60
MAX_OPEN_POSITIONS = 3

trailing_strategy = SolanaTrailingStopStrategy(
    max_positions=MAX_OPEN_POSITIONS,
    initial_stop_pct=0.25,
    enable_staged_tp=True,
)


def monitor_positions(prices):
    """
    Monitors active positions using the Solana Trailing Stop Strategy:
    - Tracks post-activation peaks (ignoring historical ATH).
    - Locks stop trigger at 15% below post-activation peak.
    - Ignores pullbacks < 15%.
    - Executes automated sell via Jito-protected private bundle on >= 15% drop.
    """
    positions = load_positions()
    if not positions or not prices:
        return []
    exits = trailing_strategy.evaluate_and_update_positions(positions, prices)
    return trailing_strategy.execute_exits(exits)


def fetch_position_prices(positions):
    """Fetch latest USD prices for every open paper position."""
    prices = {}

    for position in positions:
        token = position["token"]

        try:
            response = requests.get(
                PAIR_URL.format(token),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            pairs = response.json()

            if not isinstance(pairs, list):
                continue

            valid_pairs = [
                pair for pair in pairs
                if isinstance(pair, dict)
                and pair.get("chainId") == "solana"
            ]

            if not valid_pairs:
                print(f"No current pair data for {token}")
                continue

            pair = max(
                valid_pairs,
                key=lambda item: to_float(
                    (item.get("liquidity") or {}).get("usd")
                ),
            )

            price = pair.get("priceUsd")

            if to_float(price) > 0:
                prices[token] = to_float(price)

        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as error:
            print(f"Price check failed for {token}: {error}")

    return prices


def run_cycle():
    print("\n=== PAPER BOT CYCLE ===")

    # Monitor existing positions independently of new token discovery.
    positions = load_positions()

    if positions:
        prices = fetch_position_prices(positions)
        closed = monitor_positions(prices)
        for exit_item in closed:
            paper_trade = exit_item.get("paper_trade") or {}
            trade_data = {
                "token": exit_item.get("token_mint", paper_trade.get("token", "")),
                "symbol": exit_item.get("symbol", paper_trade.get("symbol", "")),
                "reason": exit_item.get("reason", paper_trade.get("reason", "EXIT")),
                "entry_price": paper_trade.get("entry_price", 0.0),
                "exit_price": exit_item.get("current_price_usd", paper_trade.get("exit_price", 0.0)),
                "pnl": paper_trade.get("pnl", 0.0),
                "peak_gain_pct": exit_item.get("peak_gain_pct"),
                "balance": paper_trade.get("balance"),
            }
            notify_position_closed(trade_data)
        print(f"Positions closed this cycle: {len(closed)}")
    else:
        print("No open paper positions.")

    # Discover tokens and open eligible paper positions only.
    results = scan_tokens()
    positions = load_positions()
    open_tokens = {position["token"] for position in positions}
    cooldown_tokens = get_cooldown_tokens(cooldown_seconds=86400)

    slots = max(0, MAX_OPEN_POSITIONS - len(positions))
    opened = 0

    for item in results:
        if slots <= 0:
            break

        if not isinstance(item, dict) or item.get("paper_eligible") is not True:
            continue

        token = item.get("address")
        price = item.get("price_usd")

        if not token or token in open_tokens or token in cooldown_tokens:
            continue

        # Predictive Dump Detection Gating: Evaluate candidate risk and actively reject high-risk tokens
        try:
            dump_eval = observer.observe_candidate(
                item,
                rugcheck_data=item.get("rugcheck_report") or (item.get("risk") or {}).get("report"),
                context="PRE_ENTRY",
            )
            rejected, reject_reason = observer.detector.should_reject(dump_eval, rejection_threshold=45.0)
            if rejected:
                print(f"[DumpDetector] BLOCKED entry for {token[:12]} ({item.get('symbol', 'TOKEN')}): {reject_reason}")
                continue
            print(f"[DumpDetector] PASSED {token[:12]}... Risk Score: {dump_eval['risk_score']}/100 ({dump_eval['risk_tier']})")
        except Exception as exc:
            print(f"[DumpDetector] Gating evaluation error: {exc}")

        notify_opportunity_found(item)

        try:
            pos = open_position(token, price)
            open_tokens.add(token)
            opened += 1
            slots -= 1
            notify_position_opened(
                token=token,
                symbol=item.get("symbol", "MEME"),
                entry_price=price,
                trade_size_usd=pos.get("trade_size", 0.0) if isinstance(pos, dict) else 0.0,
                market_cap=item.get("market_cap_usd", 0.0),
                liquidity=item.get("liquidity_usd", 0.0),
                pair_url=item.get("pair_url", ""),
            )
        except (ValueError, TypeError) as error:
            print(f"Paper entry skipped for {token}: {error}")

    print(f"New paper positions opened this cycle: {opened}")


def main():
    initialise()
    print("Paper bot started. Live trading is disabled.")

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            print("\nPaper bot stopped.")
            break
        except Exception as error:
            print(f"Cycle error: {error}")

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
