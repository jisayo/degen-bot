import csv
import json
import math
from pathlib import Path

STARTING_BALANCE = 50.00
TRADE_SIZE_PCT = 0.20
FEE_RATE = 0.01
SLIPPAGE_RATE = 0.01
TAKE_PROFIT_PCT = 0.50
STOP_LOSS_PCT = 0.15
TRAILING_STOP_PCT = 0.15

DATA_DIR = Path("results/historical_data/candles")
OUTPUT_DIR = Path("results/backtest")


def load_candles(path):
    """Load, validate, deduplicate and sort OHLCV candles."""
    data = json.loads(path.read_text())
    candles = data.get("candles", [])

    valid = []
    seen = set()

    for candle in candles:
        if not isinstance(candle, (list, tuple)) or len(candle) < 6:
            continue

        timestamp, open_, high, low, close, volume = candle[:6]

        values = [timestamp, open_, high, low, close, volume]

        if not all(
            isinstance(value, (int, float))
            and math.isfinite(value)
            for value in values
        ):
            continue

        if timestamp < 0 or timestamp in seen:
            continue

        if not all(
            isinstance(price, (int, float)) and price > 0
            for price in (open_, high, low, close)
        ):
            continue

        if volume < 0:
            continue

        if high < max(open_, close, low):
            continue

        if low > min(open_, close, high):
            continue

        seen.add(timestamp)
        valid.append([
            timestamp, open_, high, low, close, volume
        ])

    return sorted(valid, key=lambda candle: candle[0])


def calculate_exit(candles, entry_index, entry_price):
    """Calculate exits using only information available at each candle."""
    take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
    stop_loss = entry_price * (1 - STOP_LOSS_PCT)
    highest = entry_price

    for candle in candles[entry_index + 1:]:
        timestamp, open_, high, low, close, volume = candle

        # Stop level uses highs from completed candles only.
        trailing_stop = highest * (1 - TRAILING_STOP_PCT)
        active_stop = max(stop_loss, trailing_stop)

        # Account for gaps at the candle open.
        if open_ <= active_stop:
            return timestamp, open_, "GAP_STOP"

        if open_ >= take_profit:
            return timestamp, take_profit, "TAKE_PROFIT"

        stop_hit = low <= active_stop
        target_hit = high >= take_profit

        # If both are touched, assume the stop came first.
        if stop_hit:
            return timestamp, active_stop, "STOP_OR_TRAILING"

        if target_hit:
            return timestamp, take_profit, "TAKE_PROFIT"

        # Only update the trailing reference after checking exits.
        highest = max(highest, high)

    last = candles[-1]
    return last[0], last[4], "END_OF_DATA"


def run_backtest(path):
    candles = load_candles(path)

    if len(candles) < 2:
        return {
            "pool": path.stem,
            "error": "Not enough valid candles",
        }

    balance = STARTING_BALANCE
    peak_equity = STARTING_BALANCE
    max_drawdown_pct = 0.0
    trades = []
    index = 0

    while index < len(candles) - 1:
        entry_candle = candles[index]
        entry_price = entry_candle[4]

        allocation = balance * TRADE_SIZE_PCT

        if allocation <= 0:
            break

        # Apply buy-side slippage.
        actual_entry = entry_price * (1 + SLIPPAGE_RATE)
        quantity = allocation / actual_entry
        entry_fee = allocation * FEE_RATE

        exit_time, raw_exit, reason = calculate_exit(
            candles, index, actual_entry
        )

        # Apply sell-side slippage.
        exit_price = raw_exit * (1 - SLIPPAGE_RATE)
        gross_proceeds = quantity * exit_price
        exit_fee = gross_proceeds * FEE_RATE

        # Allocation is returned through sale proceeds.
        # Fees are additional costs.
        net_pnl = (
            gross_proceeds - allocation - entry_fee - exit_fee
        )
        balance += net_pnl

        trade = {
            "entry_time": entry_candle[0],
            "exit_time": exit_time,
            "entry_price": actual_entry,
            "exit_price": exit_price,
            "allocation": allocation,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "net_pnl": net_pnl,
            "balance": balance,
            "exit_reason": reason,
        }
        trades.append(trade)

        # Track peak and drawdown using conservative intratrade
        # estimates from each candle while the position is open.
        entry_fee_equity = balance - net_pnl
        position_peak = entry_fee_equity

        for candle in candles[index + 1:]:
            timestamp, open_, high, low, close, volume = candle

            if timestamp > exit_time:
                break

            mark_value = quantity * close
            unrealised_equity = (
                entry_fee_equity - allocation - entry_fee
                + mark_value
            )

            peak_equity = max(peak_equity, unrealised_equity)

            if peak_equity > 0:
                drawdown = (
                    (peak_equity - unrealised_equity)
                    / peak_equity * 100
                )
                max_drawdown_pct = max(
                    max_drawdown_pct, drawdown
                )

        peak_equity = max(peak_equity, balance)

        if peak_equity > 0:
            drawdown = (
                (peak_equity - balance) / peak_equity * 100
            )
            max_drawdown_pct = max(
                max_drawdown_pct, drawdown
            )

        exit_index = next(
            (
                i for i, candle in enumerate(candles)
                if candle[0] >= exit_time
            ),
            len(candles) - 1,
        )

        index = exit_index + 1

    wins = sum(1 for trade in trades if trade["net_pnl"] > 0)

    return {
        "pool": path.stem,
        "candles": len(candles),
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": (
            round(wins / len(trades) * 100, 2)
            if trades else 0
        ),
        "starting_balance": STARTING_BALANCE,
        "final_balance": round(balance, 4),
        "net_pnl": round(balance - STARTING_BALANCE, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "trade_details": trades,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reports = []

    for path in sorted(DATA_DIR.glob("*.json")):
        print(f"Testing {path.stem}...")
        try:
            reports.append(run_backtest(path))
        except (OSError, ValueError, KeyError, TypeError) as error:
            reports.append({
                "pool": path.stem,
                "error": str(error),
            })

    report_path = OUTPUT_DIR / "backtest_7d.json"
    report_path.write_text(json.dumps(reports, indent=2))

    summary_path = OUTPUT_DIR / "backtest_7d_summary.csv"

    fields = [
        "pool",
        "candles",
        "trades",
        "wins",
        "losses",
        "win_rate_pct",
        "starting_balance",
        "final_balance",
        "net_pnl",
        "max_drawdown_pct",
        "error",
    ]

    with summary_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for report in reports:
            writer.writerow({
                key: report.get(key, "")
                for key in fields
            })

    print(f"\nSaved detailed report: {report_path}")
    print(f"Saved summary: {summary_path}")

    for report in reports:
        print(
            f"{report['pool']}: "
            f"trades={report.get('trades', 0)}, "
            f"net P/L=${report.get('net_pnl', 0)}, "
            f"final=${report.get('final_balance', 0)}, "
            f"win rate={report.get('win_rate_pct', 0)}%"
        )


if __name__ == "__main__":
    main()