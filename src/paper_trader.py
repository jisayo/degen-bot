import csv
import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")
TRADE_LOG = DATA_DIR / "paper_trades.csv"
STATE_FILE = DATA_DIR / "paper_state.json"

STARTING_BALANCE = 50.00
TRADE_SIZE = 2.00
FEE_RATE = 0.01
SLIPPAGE_RATE = 0.01

FIELDS = [
    "timestamp", "token", "entry_price", "exit_price",
    "trade_size", "fees", "slippage", "pnl", "balance", "reason"
]


def initialise():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not TRADE_LOG.exists():
        with TRADE_LOG.open("w", newline="") as file:
            csv.DictWriter(file, fieldnames=FIELDS).writeheader()

    if not STATE_FILE.exists():
        save_balance(STARTING_BALANCE)


def load_balance():
    initialise()
    with STATE_FILE.open() as file:
        state = json.load(file)
    return float(state["balance"])


def save_balance(balance):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"balance": round(balance, 4)}))
    temporary.replace(STATE_FILE)


def simulate_trade(token, entry_price, exit_price, balance):
    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("Prices must be greater than zero.")

    if balance < TRADE_SIZE:
        raise ValueError("Insufficient paper balance.")

    actual_entry = entry_price * (1 + SLIPPAGE_RATE)
    actual_exit = exit_price * (1 - SLIPPAGE_RATE)

    quantity = TRADE_SIZE / actual_entry
    gross_pnl = quantity * (actual_exit - actual_entry)
    fees = (TRADE_SIZE + quantity * actual_exit) * FEE_RATE
    pnl = gross_pnl - fees

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token": token,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "trade_size": TRADE_SIZE,
        "fees": round(fees, 4),
        "slippage": SLIPPAGE_RATE * 100,
        "pnl": round(pnl, 4),
        "balance": round(balance + pnl, 4),
        "reason": "Paper simulation",
    }


def record_trade(trade):
    initialise()
    with TRADE_LOG.open("a", newline="") as file:
        csv.DictWriter(file, fieldnames=FIELDS).writerow(trade)

def execute_paper_trade(token, entry_price, exit_price):
    balance = load_balance()

    trade = simulate_trade(
        token=token,
        entry_price=entry_price,
        exit_price=exit_price,
        balance=balance,
    )

    if trade["balance"] < 0:
        raise ValueError("Trade would make the paper balance negative.")

    record_trade(trade)
    save_balance(trade["balance"])

    print(f"Paper trade recorded: {token}")
    print(f"Net P/L: ${trade['pnl']:.4f}")
    print(f"New balance: ${trade['balance']:.4f}")

    return trade
def main():
    initialise()
    print("Paper trader ready — no trade executed.")
    print(f"Paper balance: ${load_balance():.2f}")
    print("Scanner integration comes next.")


if __name__ == "__main__":
    main()
