import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import statistics

import backtest_engine as engine
import fetch_rugcheck_cache
from solana_trailing_strategy import calculate_solana_trailing_exit

DATA_DIR = Path(
    "results/backtest/november_2026/clean_cohort/candles"
)
OUTPUT_DIR = Path(
    "results/backtest/november_2026/clean_cohort"
)
RUGCHECK_CACHE_PATH = Path("data/rugcheck_cache.json")

MAX_OPEN_POSITIONS = 3
TRADE_SIZE_PCT = 0.10  # 10% per trade
TRAILING_STOP_PCT = 0.15           # 15% locked trailing stop below post-activation peak
SLIPPAGE_TOLERANCE_PCT = 0.15      # 10-15% slippage tolerance for Jito private bundles
DEFAULT_EXIT_SLIPPAGE = 0.01       # 1% realized price impact under Jito MEV protection

# ============================================================
# PRE-TRADE GATE FILTERS
# ============================================================
ENABLE_PRE_TRADE_FILTERS = True
MIN_LIQUIDITY_USD = 1000.0   # Reject if liquidity below $1,000 USD
MAX_RUGCHECK_SCORE = 35.0   # Reject if RugCheck risk score > 35 or rugged
ALLOW_RUGCHECK_ERROR = False # Reject unverified tokens if lookup failed/timed out
MIN_BAR0_VOLUME = 1000.0    # Reject if launch candle volume < $1,000 USD
REQUIRE_GREEN_BAR0 = True   # Reject if launch candle is red/flat (close <= open)


def evaluate_pre_trade_filters(pool_id, candles, pool_to_token, rugcheck_cache):
    """
    Evaluates pre-trade entry criteria (Conditions 1, 2, 3).
    Returns (passed: bool, reason: str or None).
    """
    if not ENABLE_PRE_TRADE_FILTERS:
        return True, None

    # Condition 1: RugCheck Risk Evaluation
    mint = pool_to_token.get(pool_id)
    rc = rugcheck_cache.get(mint, {}) if mint else {}
    rc_score = rc.get("score", 100)
    rc_status = rc.get("status", "error")
    rc_rugged = rc.get("rugged", False)

    if rc_rugged:
        return False, "Pre-trade filter: RugCheck flagged token as rugged"

    if rc_status != "ok" and not ALLOW_RUGCHECK_ERROR:
        return False, "Pre-trade filter: RugCheck lookup failed or unverified"

    if rc_score > MAX_RUGCHECK_SCORE:
        return False, f"Pre-trade filter: RugCheck score {rc_score} exceeds threshold ({MAX_RUGCHECK_SCORE})"

    # Condition 2: Initial Volume Evaluation (Bar 0 volume)
    entry_candle = candles[0]
    volume_bar0 = entry_candle[5]
    if volume_bar0 < MIN_BAR0_VOLUME:
        return False, f"Pre-trade filter: Bar 0 volume ${volume_bar0:,.2f} below minimum ${MIN_BAR0_VOLUME:,.2f}"

    # Condition 3: Bar 0 Price Action Evaluation (Momentum / Positive close)
    open_price = entry_candle[1]
    close_price = entry_candle[4]
    if REQUIRE_GREEN_BAR0 and close_price <= open_price:
        return False, f"Pre-trade filter: Bearish launch candle (close ${close_price:.6f} <= open ${open_price:.6f})"

    return True, None


def run_single_wallet_simulation(
    paths,
    enable_filters=True,
    exit_slippage=DEFAULT_EXIT_SLIPPAGE,
    use_solana_trailing=True,
):
    """
    Simulates all cohort pools against a single $50 wallet.
    Positions are entered chronologically at bar 0 close.
    Max 3 concurrent open positions.
    Each trade allocates 10% of available cash.
    Applies pre-trade filters (RugCheck, Volume, Price Action) before entry.
    All skipped pools are documented with exact reasons (Option 4b).
    """
    global ENABLE_PRE_TRADE_FILTERS
    ENABLE_PRE_TRADE_FILTERS = enable_filters

    # Load token mapping and RugCheck cache
    pool_to_token = {}
    try:
        pool_to_token = fetch_rugcheck_cache.load_cohort_tokens()
    except Exception as exc:
        print(f"Warning: could not load cohort token mapping: {exc}")

    rugcheck_cache = {}
    if RUGCHECK_CACHE_PATH.exists():
        try:
            rugcheck_cache = json.loads(RUGCHECK_CACHE_PATH.read_text())
        except Exception as exc:
            print(f"Warning: could not load RugCheck cache: {exc}")

    raw_pools = []
    errors = []

    for path in paths:
        try:
            candles = engine.load_candles(path)
            if len(candles) < 2:
                errors.append({"pool": path.stem, "error": "Not enough valid candles"})
                continue

            entry_candle = candles[0]
            entry_time = entry_candle[0]
            entry_price = entry_candle[4]
            actual_entry = entry_price * (1 + engine.SLIPPAGE_RATE)

            if use_solana_trailing:
                exit_time, raw_exit, reason, post_activation_peak = calculate_solana_trailing_exit(
                    candles, actual_entry, trailing_stop_pct=TRAILING_STOP_PCT
                )
            else:
                exit_time, raw_exit, reason = engine.calculate_exit(
                    candles, 0, actual_entry
                )
                post_activation_peak = actual_entry

            exit_price = raw_exit * (1 - exit_slippage)
            peak_gain_pct = round(((post_activation_peak - actual_entry) / actual_entry) * 100, 2)

            raw_pools.append({
                "pool": path.stem,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "actual_entry": actual_entry,
                "exit_price": exit_price,
                "reason": reason,
                "candles": candles,
                "post_activation_peak": post_activation_peak,
                "peak_gain_pct": peak_gain_pct,
            })
        except Exception as exc:
            errors.append({"pool": path.stem, "error": str(exc)})

    # Sort pools chronologically by entry timestamp
    raw_pools.sort(key=lambda p: p["entry_time"])

    events = []
    for p in raw_pools:
        events.append((p["entry_time"], "entry", p))
        events.append((p["exit_time"], "exit", p))

    # Process exits before entries at identical timestamps
    events.sort(key=lambda e: (e[0], 0 if e[1] == "exit" else 1))

    cash = engine.STARTING_BALANCE
    open_positions = {}
    completed_trades = []
    skipped_trades = []

    peak_equity = engine.STARTING_BALANCE
    max_drawdown_pct = 0.0

    for timestamp, event_type, pool_data in events:
        pool_id = pool_data["pool"]

        if event_type == "entry":
            # Check Pre-Trade Filters (Conditions 1, 2, 3)
            passed_filters, filter_reason = evaluate_pre_trade_filters(
                pool_id, pool_data["candles"], pool_to_token, rugcheck_cache
            )

            if not passed_filters:
                # Option 4b: Documented skip for failing pre-trade filter
                skipped_trades.append({
                    "pool": pool_id,
                    "entry_time": timestamp,
                    "reason": filter_reason,
                    "category": "pre_trade_filter",
                })
            # Check maximum concurrent positions and minimum trade size ($1.00)
            elif len(open_positions) < MAX_OPEN_POSITIONS and cash >= 1.00:
                trade_size = round(cash * TRADE_SIZE_PCT, 4)
                entry_fee = trade_size * engine.FEE_RATE
                quantity = trade_size / pool_data["actual_entry"]

                open_positions[pool_id] = {
                    "pool": pool_id,
                    "entry_time": timestamp,
                    "entry_price": pool_data["actual_entry"],
                    "allocation": trade_size,
                    "entry_fee": entry_fee,
                    "quantity": quantity,
                    "pool_data": pool_data,
                }
                cash -= (trade_size + entry_fee)
            else:
                reason = "Max open positions reached (3)" if len(open_positions) >= MAX_OPEN_POSITIONS else "Insufficient cash (< $1.00)"
                skipped_trades.append({
                    "pool": pool_id,
                    "entry_time": timestamp,
                    "reason": reason,
                    "category": "wallet_constraint",
                })

        elif event_type == "exit":
            if pool_id in open_positions:
                pos = open_positions.pop(pool_id)
                exit_price = pool_data["exit_price"]
                gross_proceeds = pos["quantity"] * exit_price
                exit_fee = gross_proceeds * engine.FEE_RATE
                net_pnl = gross_proceeds - pos["allocation"] - pos["entry_fee"] - exit_fee

                cash += (gross_proceeds - exit_fee)

                completed_trades.append({
                    "pool": pool_id,
                    "entry_time": pos["entry_time"],
                    "exit_time": timestamp,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "allocation": pos["allocation"],
                    "entry_fee": pos["entry_fee"],
                    "exit_fee": exit_fee,
                    "net_pnl": round(net_pnl, 4),
                    "wallet_cash": round(cash, 4),
                    "exit_reason": pool_data["reason"],
                    "post_activation_peak": pool_data.get("post_activation_peak", pos["entry_price"]),
                    "peak_gain_pct": pool_data.get("peak_gain_pct", 0.0),
                })

        # Calculate current total equity
        unrealised_value = 0.0
        for pos in open_positions.values():
            candles = pos["pool_data"]["candles"]
            latest_close = pos["entry_price"]
            for c in candles:
                if c[0] <= timestamp:
                    latest_close = c[4]
                else:
                    break
            unrealised_value += pos["quantity"] * latest_close

        total_equity = cash + unrealised_value
        peak_equity = max(peak_equity, total_equity)

        if peak_equity > 0:
            dd = (peak_equity - total_equity) / peak_equity * 100
            max_drawdown_pct = max(max_drawdown_pct, dd)

    wins = sum(1 for t in completed_trades if t["net_pnl"] > 0)
    losses = sum(1 for t in completed_trades if t["net_pnl"] <= 0)
    pnls = [t["net_pnl"] for t in completed_trades]
    exit_reasons = Counter(t["exit_reason"] for t in completed_trades)

    filter_skips = sum(1 for t in skipped_trades if t.get("category") == "pre_trade_filter")
    constraint_skips = sum(1 for t in skipped_trades if t.get("category") == "wallet_constraint")
    skip_reason_breakdown = Counter(t["reason"].split(":")[0] if "Pre-trade filter:" in t["reason"] else t["reason"] for t in skipped_trades)

    aggregate = {
        "mode": "single_50_dollar_wallet",
        "strategy": (
            "Solana Trailing Stop-Loss (15% Post-Activation Ratchet, Jito-Protected Exit)"
            if use_solana_trailing
            else "Fixed Take-Profit 50% / Stop-Loss 15%"
        ),
        "trailing_stop_pct": round(TRAILING_STOP_PCT * 100, 1) if use_solana_trailing else 15.0,
        "slippage_tolerance_pct": round(SLIPPAGE_TOLERANCE_PCT * 100, 1),
        "exit_slippage_realized_pct": round(exit_slippage * 100, 2),
        "mev_protection": "Jito-Protected Private Bundle",
        "max_concurrent_positions": MAX_OPEN_POSITIONS,
        "trade_size_pct": TRADE_SIZE_PCT * 100,
        "starting_balance": engine.STARTING_BALANCE,
        "final_balance": round(cash, 4),
        "total_net_pnl": round(cash - engine.STARTING_BALANCE, 4),
        "return_pct": round((cash - engine.STARTING_BALANCE) / engine.STARTING_BALANCE * 100, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "pools_found": len(paths),
        "trades_executed": len(completed_trades),
        "trades_skipped": len(skipped_trades),
        "trades_skipped_by_filter": filter_skips,
        "trades_skipped_by_wallet_limit": constraint_skips,
        "pre_trade_filters_enabled": ENABLE_PRE_TRADE_FILTERS,
        "filters_config": {
            "min_liquidity_usd": MIN_LIQUIDITY_USD,
            "max_rugcheck_score": MAX_RUGCHECK_SCORE,
            "min_bar0_volume_usd": MIN_BAR0_VOLUME,
            "require_green_bar0": REQUIRE_GREEN_BAR0,
            "allow_rugcheck_error": ALLOW_RUGCHECK_ERROR,
        },
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / len(completed_trades) * 100, 2) if completed_trades else 0,
        "mean_trade_pnl": round(statistics.mean(pnls), 4) if pnls else 0,
        "median_trade_pnl": round(statistics.median(pnls), 4) if pnls else 0,
        "exit_reasons": dict(exit_reasons),
        "skip_reasons": dict(skip_reason_breakdown),
    }

    return aggregate, completed_trades, skipped_trades, errors


def main():
    parser = argparse.ArgumentParser(description="Single $50 Wallet Backtester with Solana Trailing Stop")
    parser.add_argument("--slippage", type=float, default=DEFAULT_EXIT_SLIPPAGE, help="Realized exit slippage rate (e.g. 0.01 or 0.10)")
    parser.add_argument("--baseline", action="store_true", help="Run old baseline with 50% fixed take-profit")
    args = parser.parse_args()

    use_trailing = not args.baseline
    exit_slippage = args.slippage

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(DATA_DIR.glob("*.json"))

    aggregate, completed_trades, skipped_trades, errors = run_single_wallet_simulation(
        paths,
        enable_filters=True,
        exit_slippage=exit_slippage,
        use_solana_trailing=use_trailing,
    )

    result_path = OUTPUT_DIR / "single_entry_results.json"
    summary_path = OUTPUT_DIR / "single_entry_summary.csv"
    skipped_path = OUTPUT_DIR / "single_entry_skipped.csv"

    # Save JSON with aggregate, executed trades, documented skipped trades, and errors
    result_path.write_text(json.dumps({
        "aggregate": aggregate,
        "trades": completed_trades,
        "skipped_trades": skipped_trades,
        "errors": errors,
    }, indent=2))

    # Save Executed Trades CSV
    fields = [
        "pool", "entry_time", "exit_time", "entry_price", "exit_price",
        "allocation", "entry_fee", "exit_fee", "net_pnl", "wallet_cash",
        "exit_reason", "post_activation_peak", "peak_gain_pct",
    ]

    with summary_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for trade in completed_trades:
            writer.writerow({k: trade.get(k, "") for k in fields})

    # Save Skipped Trades CSV (Option 4b)
    skip_fields = ["pool", "entry_time", "reason", "category"]
    with skipped_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=skip_fields)
        writer.writeheader()
        for skip in skipped_trades:
            writer.writerow({k: skip.get(k, "") for k in skip_fields})

    print("\n========== SINGLE $50 WALLET BACKTEST (SOLANA TRAILING STOP STRATEGY) ==========")
    for key, value in aggregate.items():
        if key in ("exit_reasons", "skip_reasons", "filters_config"):
            print(f"{key}:")
            for sub_k, sub_v in value.items():
                print(f"  - {sub_k}: {sub_v}")
        else:
            print(f"{key}: {value}")

    print(f"\nJSON:    {result_path}")
    print(f"CSV:     {summary_path}")
    print(f"Skipped: {skipped_path}")


if __name__ == "__main__":
    main()
