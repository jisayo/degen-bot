import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")
TRADE_LOG = DATA_DIR / "paper_trades.csv"
STATE_FILE = DATA_DIR / "paper_state.json"
POSITIONS_FILE = DATA_DIR / "open_positions.json"

STARTING_BALANCE = 50.00
MIN_TRADE_SIZE = 1.00

TRADE_SIZE_PCT = 0.20
FEE_RATE = 0.01
SLIPPAGE_RATE = 0.01

TAKE_PROFIT_PCT = 0.50
STOP_LOSS_PCT = 0.15
TRAILING_STOP_PCT = 0.15

FIELDS = [
    "timestamp", "token", "entry_price", "exit_price",
    "trade_size", "fees", "slippage", "pnl", "balance", "reason"
]


def now():
    return datetime.now(timezone.utc).isoformat()


def valid_price(price):
    if isinstance(price, bool):
        return False
    try:
        return math.isfinite(float(price)) and float(price) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def initialise():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not TRADE_LOG.exists():
        with TRADE_LOG.open("w", newline="") as file:
            csv.DictWriter(file, fieldnames=FIELDS).writeheader()

    if not STATE_FILE.exists():
        save_balance(STARTING_BALANCE)

    if not POSITIONS_FILE.exists():
        save_positions([])


def load_balance():
    initialise()
    with STATE_FILE.open() as file:
        state = json.load(file)

    balance = float(state["balance"])
    if not math.isfinite(balance) or balance < 0:
        raise ValueError("Invalid paper balance state.")

    return balance


def save_balance(balance):
    if not math.isfinite(float(balance)) or balance < 0:
        raise ValueError("Balance must be finite and non-negative.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"balance": round(balance, 4)}))
    temporary.replace(STATE_FILE)


def load_positions():
    initialise()
    with POSITIONS_FILE.open() as file:
        positions = json.load(file)

    if not isinstance(positions, list):
        raise ValueError("Invalid open positions file.")

    return positions


def save_positions(positions):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = POSITIONS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(positions, indent=2))
    temporary.replace(POSITIONS_FILE)


def simulate_trade(token, entry_price, exit_price, balance):
    if not valid_price(entry_price) or not valid_price(exit_price):
        raise ValueError("Prices must be finite and greater than zero.")

    if not math.isfinite(float(balance)) or balance <= 0:
        raise ValueError("Insufficient or invalid paper balance.")
    trade_size = round(float(balance) * TRADE_SIZE_PCT, 4)
    if trade_size < MIN_TRADE_SIZE:
        raise ValueError("Calculated trade size is below the $1 minimum.")

    entry_price = float(entry_price)
    exit_price = float(exit_price)

    actual_entry = entry_price * (1 + SLIPPAGE_RATE)
    actual_exit = exit_price * (1 - SLIPPAGE_RATE)

    quantity = trade_size / actual_entry
    gross_pnl = quantity * (actual_exit - actual_entry)
    fees = (trade_size + quantity * actual_exit) * FEE_RATE
    pnl = gross_pnl - fees
    new_balance = round(balance + pnl, 4)

    if not math.isfinite(pnl) or new_balance < 0:
        raise ValueError("Invalid trade result or negative paper balance.")

    return {
        "timestamp": now(),
        "token": str(token),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "trade_size": trade_size,
        "fees": round(fees, 4),
        "slippage": SLIPPAGE_RATE * 100,
        "pnl": round(pnl, 4),
        "balance": new_balance,
        "reason": "Paper simulation",
    }


def record_trade(trade):
    initialise()
    with TRADE_LOG.open("a", newline="") as file:
        csv.DictWriter(file, fieldnames=FIELDS).writerow(trade)


def execute_paper_trade(token, entry_price, exit_price):
    """Compatibility helper: simulate and record a completed trade."""
    balance = load_balance()
    trade = simulate_trade(token, entry_price, exit_price, balance)

    record_trade(trade)
    save_balance(trade["balance"])

    print(f"Paper trade recorded: {token}")
    print(f"Net P/L: ${trade['pnl']:.4f}")
    print(f"New balance: ${trade['balance']:.4f}")

    return trade


def open_position(token, entry_price):
    """Open a simulated position; no real funds or orders are used."""
    if not token or not valid_price(entry_price):
        raise ValueError("Token and a valid entry price are required.")

    positions = load_positions()
    token = str(token)

    if any(p["token"] == token for p in positions):
        raise ValueError("A position for this token is already open.")

    balance = load_balance()
    if balance <= 0:
        raise ValueError("Insufficient paper balance.")
    trade_size = round(balance * TRADE_SIZE_PCT, 4)
    if trade_size < MIN_TRADE_SIZE:
        raise ValueError("Calculated trade size is below the $1 minimum.")

    actual_entry = float(entry_price) * (1 + SLIPPAGE_RATE)
    quantity = trade_size / actual_entry
    entry_fee = trade_size * FEE_RATE

    position = {
        "token": token,
        "entry_price": float(entry_price),
        "actual_entry_price": actual_entry,
        "highest_price": actual_entry,
        "quantity": quantity,
        "trade_size": trade_size,
        "entry_fee": entry_fee,
        "opened_at": now(),
    }

    positions.append(position)
    save_positions(positions)

    print(f"Paper position opened: {token} at ${entry_price}")
    return position


def close_position(token, exit_price, reason="Manual paper exit"):
    """Close an existing simulated position and record its net P/L."""
    if not valid_price(exit_price):
        raise ValueError("Exit price must be finite and greater than zero.")

    positions = load_positions()
    token = str(token)

    position = next(
        (p for p in positions if p["token"] == token),
        None,
    )
    if position is None:
        raise ValueError("No open position found for this token.")

    balance = load_balance()
    actual_exit = float(exit_price) * (1 - SLIPPAGE_RATE)
    quantity = float(position["quantity"])
    proceeds = quantity * actual_exit
    exit_fee = proceeds * FEE_RATE
    fees = float(position["entry_fee"]) + exit_fee

    pnl = proceeds - float(position["trade_size"]) - fees
    new_balance = round(balance + pnl, 4)

    if not math.isfinite(new_balance) or new_balance < 0:
        raise ValueError("Closing this position would make balance invalid.")

    trade = {
        "timestamp": now(),
        "token": token,
        "entry_price": position["entry_price"],
        "exit_price": float(exit_price),
        "trade_size": position["trade_size"],
        "fees": round(fees, 4),
        "slippage": SLIPPAGE_RATE * 100,
        "pnl": round(pnl, 4),
        "balance": new_balance,
        "reason": str(reason),
    }

    remaining = [p for p in positions if p["token"] != token]

    # Write the completed trade before updating state.
    record_trade(trade)
    save_balance(new_balance)
    save_positions(remaining)

    print(f"Paper position closed: {token}")
    print(f"Net P/L: ${trade['pnl']:.4f}")
    print(f"Paper balance: ${trade['balance']:.4f}")

    return trade



def monitor_positions(price_map):
    """Monitor paper positions and close those hitting an exit rule.

    price_map maps token symbols to their latest observed prices.
    """
    if not isinstance(price_map, dict):
        raise ValueError("price_map must be a dictionary.")

    positions = load_positions()
    results = []

    for position in positions:
        token = position["token"]

        if token not in price_map:
            continue

        price = price_map[token]
        if not valid_price(price):
            continue

        price = float(price)
        entry = float(position["actual_entry_price"])
        peak = max(float(position.get("highest_price", entry)), price)
        position["highest_price"] = peak

        reason = None

        if price >= entry * (1 + TAKE_PROFIT_PCT):
            reason = "Take profit"
        elif price <= entry * (1 - STOP_LOSS_PCT):
            reason = "Stop loss"
        elif price <= peak * (1 - TRAILING_STOP_PCT):
            reason = "Trailing stop"

        if reason:
            results.append((token, price, reason))

    save_positions(positions)

    closed = []
    for token, price, reason in results:
        closed.append(close_position(token, price, reason))

    return closed


def main():
    initialise()
    print("Paper trader ready — no real trades executed.")
    print(f"Paper balance: ${load_balance():.2f}")
    print(f"Open positions: {len(load_positions())}")


if __name__ == "__main__":
    main()