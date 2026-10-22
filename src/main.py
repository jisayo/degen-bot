import time
import requests

from scanner import scan_tokens
from paper_trader import (
    initialise,
    load_positions,
    monitor_positions,
    open_position,
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
MAX_OPEN_POSITIONS = 1


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
        print(f"Positions closed this cycle: {len(closed)}")
    else:
        print("No open paper positions.")

    # Discover tokens and open eligible paper positions only.
    results = scan_tokens()
    positions = load_positions()
    open_tokens = {position["token"] for position in positions}

    slots = max(0, MAX_OPEN_POSITIONS - len(positions))
    opened = 0

    for item in results:
        if slots <= 0:
            break

        if not isinstance(item, dict) or item.get("paper_eligible") is not True:
            continue

        token = item.get("address")
        price = item.get("price_usd")

        if not token or token in open_tokens:
            continue

        try:
            open_position(token, price)
            open_tokens.add(token)
            opened += 1
            slots -= 1
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
