from pathlib import Path
import json
import sys

from backtest_engine import run_backtest
import backtest_engine


SETTINGS = [
    (20, 10),
    (30, 10),
    (30, 15),
    (50, 10),
    (50, 15),
    (75, 15),
    (100, 20),
]

DATA_DIR = Path("results/historical_data/candles")


def main():
    results = []

    for take_profit, trailing_stop in SETTINGS:
        backtest_engine.TAKE_PROFIT_PCT = take_profit / 100
        backtest_engine.TRAILING_STOP_PCT = trailing_stop / 100

        for path in sorted(DATA_DIR.glob("*.json")):
            report = run_backtest(path)

            results.append({
                "take_profit_pct": take_profit,
                "trailing_stop_pct": trailing_stop,
                "pool": report.get("pool"),
                "trades": report.get("trades", 0),
                "win_rate_pct": report.get("win_rate_pct", 0),
                "net_pnl": report.get("net_pnl", 0),
                "final_balance": report.get("final_balance", 0),
                "max_drawdown_pct": report.get("max_drawdown_pct", 0),
                "error": report.get("error", ""),
            })

    output = Path("results/backtest/strategy_comparison.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2))

    print("\nSTRATEGY COMPARISON")
    print("-" * 78)

    for item in results:
        print(
            f"TP {item['take_profit_pct']:>3}% | "
            f"Trail {item['trailing_stop_pct']:>2}% | "
            f"Trades {item['trades']:>3} | "
            f"Win rate {item['win_rate_pct']:>6}% | "
            f"P/L ${item['net_pnl']:>8} | "
            f"Final ${item['final_balance']:>8}"
        )

    print(f"\nSaved results to: {output}")


if __name__ == "__main__":
    main()