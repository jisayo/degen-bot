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

# Staged exits: sell 50% of the original position at +50%, then
# 25% of the original position at +100%, and trail the final 25%.
FIRST_TAKE_PROFIT_PCT = 0.50
FIRST_TAKE_PROFIT_SELL_FRACTION = 0.50
SECOND_TAKE_PROFIT_PCT = 1.00
SECOND_TAKE_PROFIT_SELL_FRACTION = 0.25
STOP_LOSS_PCT = 0.15
TRAILING_STOP_PCT = 0.15

# Backwards-compatible name for code/tests that imported the old setting.
TAKE_PROFIT_PCT = FIRST_TAKE_PROFIT_PCT

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
    state = {}
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open() as file:
                state = json.load(file)
        except Exception:
            state = {}
    state["balance"] = round(balance, 4)
    if "initial_balance" not in state:
        state["initial_balance"] = round(balance, 4)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2))
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
        "original_quantity": quantity,
        "trade_size": trade_size,
        "entry_fee": entry_fee,
        "first_take_profit_done": False,
        "second_take_profit_done": False,
        "trailing_stop_active": False,
        "opened_at": now(),
    }

    positions.append(position)
    save_positions(positions)

    print(f"Paper position opened: {token} at ${entry_price}")
    return position


def _trade_record(position, exit_price, quantity_to_close, reason):
    """Calculate a paper exit for a portion of the current position."""
    quantity = float(position["quantity"])
    if quantity_to_close <= 0 or quantity_to_close > quantity + 1e-12:
        raise ValueError("Invalid quantity for paper exit.")

    fraction = min(1.0, quantity_to_close / quantity)
    cost_basis = float(position["trade_size"]) * fraction
    entry_fee = float(position["entry_fee"]) * fraction
    actual_exit = float(exit_price) * (1 - SLIPPAGE_RATE)
    proceeds = quantity_to_close * actual_exit
    exit_fee = proceeds * FEE_RATE
    total_fees = entry_fee + exit_fee
    pnl = proceeds - cost_basis - total_fees

    balance = load_balance()
    new_balance = round(balance + pnl, 4)
    if not math.isfinite(new_balance) or new_balance < 0:
        raise ValueError("Closing this position would make balance invalid.")

    trade = {
        "timestamp": now(),
        "token": position["token"],
        "entry_price": position["entry_price"],
        "exit_price": float(exit_price),
        "trade_size": round(cost_basis, 4),
        "fees": round(total_fees, 4),
        "slippage": SLIPPAGE_RATE * 100,
        "pnl": round(pnl, 4),
        "balance": new_balance,
        "reason": str(reason),
    }
    return trade, new_balance, fraction


def _close_quantity(token, exit_price, quantity_to_close, reason):
    """Record a partial paper exit and persist the remaining position."""
    if not valid_price(exit_price):
        raise ValueError("Exit price must be finite and greater than zero.")

    positions = load_positions()
    token = str(token)
    index = next(
        (i for i, p in enumerate(positions) if p["token"] == token),
        None,
    )
    if index is None:
        raise ValueError("No open position found for this token.")

    position = positions[index]
    trade, new_balance, fraction = _trade_record(
        position, float(exit_price), float(quantity_to_close), reason
    )

    remaining_fraction = max(0.0, 1.0 - fraction)
    remaining_quantity = float(position["quantity"]) * remaining_fraction
    remaining_basis = float(position["trade_size"]) * remaining_fraction
    remaining_entry_fee = float(position["entry_fee"]) * remaining_fraction

    # Record the trade before mutating the saved state, matching the existing
    # lifecycle's write ordering.
    record_trade(trade)
    save_balance(new_balance)

    if remaining_quantity <= 1e-12:
        positions.pop(index)
    else:
        position["quantity"] = remaining_quantity
        position["trade_size"] = remaining_basis
        position["entry_fee"] = remaining_entry_fee
        positions[index] = position

    save_positions(positions)
    print(f"Paper position partially/fully exited: {token} ({reason})")
    print(f"Realised net P/L: ${trade['pnl']:.4f}")
    print(f"Paper balance: ${trade['balance']:.4f}")
    return trade


def close_position(token, exit_price, reason="Manual paper exit"):
    """Close all remaining quantity of an existing simulated position."""
    positions = load_positions()
    token = str(token)
    position = next(
        (p for p in positions if p["token"] == token),
        None,
    )
    if position is None:
        raise ValueError("No open position found for this token.")

    return _close_quantity(
        token, exit_price, float(position["quantity"]), reason
    )


def monitor_positions(price_map):
    """Apply hard stop, staged targets, then trail the final remainder.

    price_map maps token addresses to their latest observed USD prices.
    No real orders are placed.
    """
    if not isinstance(price_map, dict):
        raise ValueError("price_map must be a dictionary.")

    positions = load_positions()
    actions = []

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

        # Legacy saved positions are supported by using their current
        # quantity as the original quantity if that field is absent.
        original_quantity = float(
            position.get("original_quantity", position["quantity"])
        )
        position.setdefault("original_quantity", original_quantity)
        position.setdefault("first_take_profit_done", False)
        position.setdefault("second_take_profit_done", False)
        position.setdefault("trailing_stop_active", False)

        if price <= entry * (1 - STOP_LOSS_PCT):
            actions.append((token, price, "Stop loss", "all", None))
            continue

        if (
            not position["first_take_profit_done"]
            and price >= entry * (1 + FIRST_TAKE_PROFIT_PCT)
        ):
            quantity = original_quantity * FIRST_TAKE_PROFIT_SELL_FRACTION
            actions.append((
                token, price, "Take profit 1 (+50%)", quantity,
                "first_take_profit_done",
            ))
            position["first_take_profit_done"] = True

        if (
            not position["second_take_profit_done"]
            and price >= entry * (1 + SECOND_TAKE_PROFIT_PCT)
        ):
            quantity = original_quantity * SECOND_TAKE_PROFIT_SELL_FRACTION
            actions.append((
                token, price, "Take profit 2 (+100%)", quantity,
                "second_take_profit_done",
            ))
            position["second_take_profit_done"] = True
            position["trailing_stop_active"] = True

        if (
            position["trailing_stop_active"]
            and price <= peak * (1 - TRAILING_STOP_PCT)
        ):
            actions.append((token, price, "Trailing stop", "all", None))

    save_positions(positions)

    closed = []
    for token, price, reason, quantity, stage_field in actions:
        try:
            if quantity == "all":
                trade = close_position(token, price, reason)
            else:
                current = next(
                    (p for p in load_positions() if p["token"] == token),
                    None,
                )
                if current is None:
                    continue
                close_qty = min(float(quantity), float(current["quantity"]))
                trade = _close_quantity(token, price, close_qty, reason)

                if stage_field:
                    current_positions = load_positions()
                    for current_position in current_positions:
                        if current_position["token"] == token:
                            current_position[stage_field] = True
                    save_positions(current_positions)
            closed.append(trade)
        except ValueError as error:
            print(f"Paper exit skipped for {token}: {error}")

    return closed


def main():
    initialise()
    print("Paper trader ready — no real trades executed.")
    print(f"Paper balance: ${load_balance():.2f}")
    print(f"Open positions: {len(load_positions())}")


if __name__ == "__main__":
    main()
