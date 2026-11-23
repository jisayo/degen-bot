import csv
import json
import statistics
from collections import Counter
from pathlib import Path

import backtest_engine as engine

ROOT = Path("results/backtest/november_2026/clean_cohort")
CANDLE_DIR = ROOT / "candles"
RESULTS_FILE = ROOT / "backtest_results.json"
SUMMARY_FILE = ROOT / "backtest_summary.csv"

def main():
    if not CANDLE_DIR.is_dir():
        raise SystemExit(f"Missing candle directory: {CANDLE_DIR}")

    if RESULTS_FILE.exists() or SUMMARY_FILE.exists():
        raise SystemExit("Baseline output already exists. Refusing to overwrite.")

    files = sorted(CANDLE_DIR.glob("*.json"))
    if len(files) != 162:
        raise SystemExit(f"Expected 162 candle files; found {len(files)}")

    results = []
    errors = []
    exit_reasons = Counter()

    for index, path in enumerate(files, 1):
        print(f"[{index}/{len(files)}] Backtesting {path.stem}")

        try:
            result = engine.run_backtest(path)
            if not isinstance(result, dict):
                raise ValueError(f"Unexpected engine result: {type(result).__name__}")

            results.append(result)

            for trade in result.get("trade_details", []):
                reason = (
                    trade.get("exit_reason")
                    or trade.get("exit_type")
                    or trade.get("reason")
                    or "UNKNOWN"
                )
                exit_reasons[str(reason)] += 1

        except Exception as error:
            errors.append({
                "pool": path.stem,
                "error": str(error),
            })

    if not results:
        raise SystemExit("No successful backtests. No report written.")

    trades = sum(int(r.get("trades", 0)) for r in results)
    wins = sum(int(r.get("wins", 0)) for r in results)
    losses = sum(int(r.get("losses", 0)) for r in results)

    net_pnls = [float(r.get("net_pnl", 0)) for r in results]
    drawdowns = [float(r.get("max_drawdown_pct", 0)) for r in results]
    final_balances = [float(r.get("final_balance", 0)) for r in results]

    summary = {
        "dataset": "November 2026 CoinGecko clean cohort",
        "run_type": "exit_mechanics_baseline_not_scanner_entry_backtest",
        "pools_expected": len(files),
        "pools_tested": len(results),
        "pool_errors": len(errors),
        "pools_with_trades": sum(int(r.get("trades", 0)) > 0 for r in results),
        "total_trades": trades,
        "wins": wins,
        "losses": losses,
        "aggregate_win_rate_pct": round(wins / trades * 100, 4) if trades else 0,
        "sum_of_independent_pool_net_pnl": round(sum(net_pnls), 4),
        "mean_pool_net_pnl": round(statistics.mean(net_pnls), 4),
        "median_pool_net_pnl": round(statistics.median(net_pnls), 4),
        "mean_pool_final_balance": round(statistics.mean(final_balances), 4),
        "mean_pool_max_drawdown_pct": round(statistics.mean(drawdowns), 4),
        "median_pool_max_drawdown_pct": round(statistics.median(drawdowns), 4),
        "exit_reason_counts": dict(exit_reasons),
        "strategy": {
            name: getattr(engine, name, None)
            for name in (
                "STARTING_BALANCE",
                "TRADE_SIZE_PCT",
                "FEE_RATE",
                "SLIPPAGE_RATE",
                "TAKE_PROFIT_PCT",
                "STOP_LOSS_PCT",
                "TRAILING_STOP_PCT",
            )
        },
        "errors": errors,
        "pool_results": results,
    }

    RESULTS_FILE.write_text(json.dumps(summary, indent=2))

    columns = [
        "pool", "candles", "trades", "wins", "losses",
        "win_rate_pct", "starting_balance", "final_balance",
        "net_pnl", "max_drawdown_pct",
    ]

    with SUMMARY_FILE.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key) for key in columns})

    print("\n========== NOVEMBER EXIT BASELINE ==========")
    print(f"Pools tested: {len(results)}/{len(files)}")
    print(f"Pool errors: {len(errors)}")
    print(f"Total trades: {trades}")
    print(f"Wins / losses: {wins} / {losses}")
    print(f"Aggregate win rate: {summary['aggregate_win_rate_pct']}%")
    print(f"Mean pool net P/L: ${summary['mean_pool_net_pnl']}")
    print(f"Median pool net P/L: ${summary['median_pool_net_pnl']}")
    print(f"Mean pool max drawdown: {summary['mean_pool_max_drawdown_pct']}%")
    print(f"Exit reasons: {dict(exit_reasons)}")
    print(f"\nJSON: {RESULTS_FILE}")
    print(f"CSV:  {SUMMARY_FILE}")

    if errors:
        print("\nPOOL ERRORS:")
        for error in errors:
            print(error)

if __name__ == "__main__":
    main()
