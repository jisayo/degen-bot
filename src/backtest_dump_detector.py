"""
Historical Validation Framework for Predictive Dump Detector.

Validates the predictive dump detection engine against November 2026 research
datasets (162 clean cohort pools and 1,440 RugCheck records) across
5m, 15m, 30m, and 60m forward windows without look-ahead bias.
"""

import json
import glob
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict

from predictive_dump_detector import PredictiveDumpDetector, classify_risk_tier
import fetch_rugcheck_cache


ROOT = Path(__file__).resolve().parent.parent
CLEAN_COHORT_DIR = ROOT / "results/backtest/november_2026/clean_cohort"
CANDLE_DIR = CLEAN_COHORT_DIR / "candles"
RUGCHECK_CACHE_PATH = ROOT / "data/rugcheck_cache.json"
SINGLE_ENTRY_RESULTS = CLEAN_COHORT_DIR / "single_entry_results.json"
FIVE_MIN_BATCH_DIR = ROOT / "results/launch_data/november_2026/coingecko/1m_5m/batches"


def load_rugcheck_cache() -> Dict[str, Any]:
    if RUGCHECK_CACHE_PATH.exists():
        try:
            return json.loads(RUGCHECK_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def load_pool_to_token_map() -> Dict[str, str]:
    try:
        return fetch_rugcheck_cache.load_cohort_tokens()
    except Exception:
        return {}


def run_historical_validation(
    thresholds: List[float] = [25.0, 35.0, 45.0, 55.0, 65.0],
    dump_pcts: List[float] = [20.0, 35.0, 50.0],
) -> Dict[str, Any]:
    """
    Evaluates predictive dump detector at entry time (t=0) and forward horizons
    across all cohort pools.
    """
    detector = PredictiveDumpDetector()
    pool_to_token = load_pool_to_token_map()
    rugcheck_cache = load_rugcheck_cache()

    candle_files = sorted(CANDLE_DIR.glob("*.json"))
    if not candle_files:
        raise RuntimeError(f"No candle files found in {CANDLE_DIR}")

    evaluations = []
    
    # Also load 5m candle batches for higher-resolution 5m/15m/30m/60m analysis if available
    five_min_pools = {}
    for batch_file in sorted(FIVE_MIN_BATCH_DIR.glob("batch_*.jsonl")):
        try:
            for line in batch_file.open():
                if not line.strip():
                    continue
                item = json.loads(line)
                pid = item.get("pool_address")
                candles = item.get("candles", [])
                if pid and candles:
                    # Format as [[ts, open, high, low, close, volume], ...]
                    five_min_pools[pid] = [
                        [c["timestamp"], c["open"], c["high"], c["low"], c["close"], c["volume"]]
                        for c in candles if isinstance(c, dict) and "close" in c
                    ]
        except Exception:
            pass

    for cpath in candle_files:
        pool_id = cpath.stem
        try:
            data = json.loads(cpath.read_text())
            candles_15m = data.get("candles", [])
            if len(candles_15m) < 4:
                continue

            mint = pool_to_token.get(pool_id)
            rc_data = rugcheck_cache.get(mint, {}) if mint else {}

            # Check if we have 5m candles for this pool, otherwise use 15m candles
            candles_5m = five_min_pools.get(pool_id)
            active_candles = candles_5m if (candles_5m and len(candles_5m) >= 12) else candles_15m
            is_5m = (active_candles is candles_5m)

            # Bar 0 is the observation/entry candle
            bar0 = active_candles[0]
            entry_time = bar0[0]
            entry_price = bar0[4]  # close of bar 0
            entry_volume = bar0[5]

            # Reconstruct initial token_data feature dict using strictly pre-entry data
            initial_token_data = {
                "address": mint or pool_id,
                "pool_address": pool_id,
                "price_usd": entry_price,
                "volume_1h": entry_volume * (12 if is_5m else 4),
                "buys_1h": 50 if bar0[4] >= bar0[1] else 20,
                "sells_1h": 20 if bar0[4] >= bar0[1] else 50,
                "liquidity_usd": rc_data.get("liquidity", 15000.0) if rc_data else 15000.0,
                "market_cap_usd": entry_price * 1_000_000_000.0,
            }

            # Strictly historical feature evaluation (at bar 0)
            eval_result = detector.evaluate(
                initial_token_data,
                rugcheck_data=rc_data,
                candles=[bar0],
            )
            score = eval_result["risk_score"]

            # Calculate Forward Ground Truth Maximum Drops over future windows
            # Windows: 15m, 30m, 60m, and full duration
            def calc_max_drop(start_idx: int, window_bars: int) -> float:
                future_bars = active_candles[start_idx : start_idx + window_bars]
                if not future_bars:
                    return 0.0
                min_low = min(b[3] for b in future_bars)
                drop = ((entry_price - min_low) / entry_price) * 100.0
                return max(0.0, drop)

            # Determine bar counts per window
            bars_5m = 1 if is_5m else 1
            bars_15m = 3 if is_5m else 1
            bars_30m = 6 if is_5m else 2
            bars_60m = 12 if is_5m else 4
            bars_full = len(active_candles)

            drop_5m = calc_max_drop(1, bars_5m)
            drop_15m = calc_max_drop(1, bars_15m)
            drop_30m = calc_max_drop(1, bars_30m)
            drop_60m = calc_max_drop(1, bars_60m)
            drop_full = calc_max_drop(1, bars_full)

            # Calculate lead time: index of first candle that breached -20% or -35%
            lead_time_min = None
            for idx, bar in enumerate(active_candles[1:], 1):
                cur_drop = ((entry_price - bar[3]) / entry_price) * 100.0
                if cur_drop >= 35.0:
                    delta_sec = bar[0] - entry_time
                    lead_time_min = round(delta_sec / 60.0, 1)
                    break

            evaluations.append({
                "pool": pool_id,
                "token": mint,
                "risk_score": score,
                "risk_tier": eval_result["risk_tier"],
                "warnings": eval_result["warning_signals"],
                "breakdown": eval_result["breakdown"],
                "drop_5m": drop_5m,
                "drop_15m": drop_15m,
                "drop_30m": drop_30m,
                "drop_60m": drop_60m,
                "drop_full": drop_full,
                "lead_time_min": lead_time_min,
            })
        except Exception as exc:
            continue

    total_tokens = len(evaluations)

    # Compute Statistical Matrix across all Horizons and Thresholds
    matrix = {}
    windows = [
        ("5m", "drop_5m"),
        ("15m", "drop_15m"),
        ("30m", "drop_30m"),
        ("60m", "drop_60m"),
        ("full", "drop_full"),
    ]

    for win_name, drop_key in windows:
        matrix[win_name] = {}
        for dump_threshold in dump_pcts:
            thresh_key = f"dump_{int(dump_threshold)}pct"
            matrix[win_name][thresh_key] = {}

            for score_threshold in thresholds:
                score_key = f"score_{int(score_threshold)}"
                tp = 0
                fp = 0
                fn = 0
                tn = 0
                lead_times = []

                for ev in evaluations:
                    predicted_dump = ev["risk_score"] >= score_threshold
                    actual_dump = ev[drop_key] >= dump_threshold

                    if predicted_dump and actual_dump:
                        tp += 1
                        if ev["lead_time_min"] is not None:
                            lead_times.append(ev["lead_time_min"])
                    elif predicted_dump and not actual_dump:
                        fp += 1
                    elif not predicted_dump and actual_dump:
                        fn += 1
                    else:
                        tn += 1

                precision = (tp / (tp + fp)) * 100.0 if (tp + fp) > 0 else 0.0
                recall = (tp / (tp + fn)) * 100.0 if (tp + fn) > 0 else 0.0
                f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
                false_alarm_rate = (fp / (fp + tn)) * 100.0 if (fp + tn) > 0 else 0.0
                avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0.0

                matrix[win_name][thresh_key][score_key] = {
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "tn": tn,
                    "precision_pct": round(precision, 2),
                    "recall_pct": round(recall, 2),
                    "f1_score": round(f1, 2),
                    "false_alarm_rate_pct": round(false_alarm_rate, 2),
                    "missed_dumps": fn,
                    "avg_lead_time_min": avg_lead_time,
                }

    # Evaluate overlap with existing single-entry backtest results
    single_entry_stats = {"overlap_evaluated": False}
    if SINGLE_ENTRY_RESULTS.exists():
        try:
            single_data = json.loads(SINGLE_ENTRY_RESULTS.read_text())
            trades = single_data.get("trades", [])
            stopped_out = [t for t in trades if t.get("exit_reason") == "STOP_LOSS"]
            profitable = [t for t in trades if t.get("exit_reason") == "TRAILING_TAKE_PROFIT"]

            eval_by_pool = {ev["pool"]: ev for ev in evaluations}
            stopped_pools = [t["pool"] for t in stopped_out]
            profit_pools = [t["pool"] for t in profitable]

            stopped_flagged_45 = sum(1 for p in stopped_pools if eval_by_pool.get(p, {}).get("risk_score", 0) >= 45.0)
            stopped_flagged_35 = sum(1 for p in stopped_pools if eval_by_pool.get(p, {}).get("risk_score", 0) >= 35.0)
            profit_flagged_45 = sum(1 for p in profit_pools if eval_by_pool.get(p, {}).get("risk_score", 0) >= 45.0)

            single_entry_stats = {
                "overlap_evaluated": True,
                "total_trades": len(trades),
                "stop_losses_total": len(stopped_out),
                "take_profits_total": len(profitable),
                "stop_losses_flagged_at_45": stopped_flagged_45,
                "stop_losses_prevented_pct_at_45": round((stopped_flagged_45 / len(stopped_out)) * 100, 1) if stopped_out else 0,
                "stop_losses_flagged_at_35": stopped_flagged_35,
                "take_profits_wrongly_blocked_at_45": profit_flagged_45,
            }
        except Exception as exc:
            single_entry_stats = {"overlap_evaluated": False, "error": str(exc)}

    # Indicator efficacy ranking (which component contributed the most to catching dumps)
    indicator_scores_on_dumps = defaultdict(list)
    for ev in evaluations:
        if ev["drop_full"] >= 35.0:  # Confirmed dump
            for k, val in ev["breakdown"].items():
                indicator_scores_on_dumps[k].append(val)

    indicator_efficacy = {}
    for comp, vals in indicator_scores_on_dumps.items():
        indicator_efficacy[comp] = round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "dataset_pools_analyzed": total_tokens,
        "indicator_efficacy_ranking": dict(sorted(indicator_efficacy.items(), key=lambda x: x[1], reverse=True)),
        "single_entry_overlap": single_entry_stats,
        "performance_matrix": matrix,
        "sample_evaluations": evaluations[:5],
    }


if __name__ == "__main__":
    results = run_historical_validation()
    print(json.dumps(results, indent=2))
