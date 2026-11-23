import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

INTERVAL = 900
SOURCE_DIR = Path("results/launch_data/november_2026/coingecko/batches")
OUTPUT_DIR = Path("results/backtest/november_2026/clean_cohort")
CANDLE_DIR = OUTPUT_DIR / "candles"


def to_timestamp(value):
    return int(
        datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    )


def iso_utc(timestamp):
    return datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).isoformat()


def main():
    if not SOURCE_DIR.is_dir():
        raise SystemExit(f"Missing source directory: {SOURCE_DIR}")

    if OUTPUT_DIR.exists():
        raise SystemExit(
            f"Output already exists: {OUTPUT_DIR}\n"
            "Refusing to overwrite existing research data."
        )

    records = []
    seen_pools = set()
    source_errors = []

    for path in sorted(SOURCE_DIR.glob("batch_*.jsonl")):
        with path.open() as file:
            for line_number, line in enumerate(file, 1):
                try:
                    record = json.loads(line)
                    pool = record["pool_address"]

                    if pool in seen_pools:
                        raise ValueError(f"Duplicate pool: {pool}")

                    seen_pools.add(pool)
                    records.append(record)

                except Exception as error:
                    source_errors.append({
                        "file": str(path),
                        "line": line_number,
                        "error": str(error),
                    })

    if source_errors:
        raise SystemExit(
            f"Found {len(source_errors)} source errors. "
            "No output has been created."
        )

    if len(records) != 6108 or len(seen_pools) != 6108:
        raise SystemExit(
            f"Expected 6,108 unique records; found {len(records)} "
            f"records and {len(seen_pools)} unique pools."
        )

    OUTPUT_DIR.mkdir(parents=True)
    CANDLE_DIR.mkdir()

    manifest_records = []
    selected_count = 0
    reason_counts = Counter()
    candle_total = 0

    for record in records:
        pool = record["pool_address"]
        status = record.get("status", "unknown")
        raw_candles = record.get("candles") or []

        item = {
            "pool_address": pool,
            "status": status,
            "selected": False,
            "raw_candle_count": len(raw_candles),
            "eligible_candle_count": 0,
            "exclusion_reason": None,
        }

        if status != "ok":
            item["exclusion_reason"] = f"source_status_{status}"
            reason_counts[item["exclusion_reason"]] += 1
            manifest_records.append(item)
            continue

        launch = to_timestamp(record["launch_time"])
        window_end = to_timestamp(record["window_end"])

        # Only retain bars fully contained in the 24-hour window.
        candles = [
            candle for candle in raw_candles
            if candle["timestamp"] + INTERVAL <= window_end
        ]

        item["eligible_candle_count"] = len(candles)

        if len(candles) < 2:
            item["exclusion_reason"] = "insufficient_candles"
            reason_counts[item["exclusion_reason"]] += 1
            manifest_records.append(item)
            continue

        timestamps = [c["timestamp"] for c in candles]

        if any(
            b - a != INTERVAL
            for a, b in zip(timestamps, timestamps[1:])
        ):
            item["exclusion_reason"] = "internal_gaps"
            reason_counts[item["exclusion_reason"]] += 1
            manifest_records.append(item)
            continue

        first_close = timestamps[0] + INTERVAL
        last_close = timestamps[-1] + INTERVAL

        start_delay = first_close - launch
        end_delay = window_end - last_close

        if not 0 <= start_delay <= INTERVAL:
            item["exclusion_reason"] = "start_edge_outside_tolerance"
            reason_counts[item["exclusion_reason"]] += 1
            manifest_records.append(item)
            continue

        if not 0 <= end_delay <= INTERVAL:
            item["exclusion_reason"] = "end_edge_outside_tolerance"
            reason_counts[item["exclusion_reason"]] += 1
            manifest_records.append(item)
            continue

        # The first bar's close is the earliest entry observation.
        # Shift every timestamp to its interval-close time.
        converted = [
            [
                candle["timestamp"] + INTERVAL,
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
            ]
            for candle in candles
        ]

        output = {
            "pool_address": pool,
            "source": "coingecko",
            "interval_minutes": 15,
            "timestamp_convention": "interval_close",
            "launch_time": record["launch_time"],
            "window_end": record["window_end"],
            "candles": converted,
        }

        (CANDLE_DIR / f"{pool}.json").write_text(
            json.dumps(output, separators=(",", ":"))
        )

        item.update({
            "selected": True,
            "exclusion_reason": None,
            "start_delay_seconds": start_delay,
            "end_delay_seconds": end_delay,
            "first_close_utc": iso_utc(first_close),
            "last_close_utc": iso_utc(last_close),
        })

        selected_count += 1
        candle_total += len(converted)
        reason_counts["selected"] += 1
        manifest_records.append(item)

    # The previously audited clean cohort should contain exactly 162 pools.
    if selected_count != 162:
        raise SystemExit(
            f"Expected 162 selected pools, got {selected_count}. "
            f"Inspect the generated manifest before proceeding."
        )

    manifest = {
        "dataset": "November 2026 CoinGecko clean cohort",
        "source": str(SOURCE_DIR),
        "total_source_records": len(records),
        "unique_pool_records": len(seen_pools),
        "selected_pools": selected_count,
        "selected_candles": candle_total,
        "interval_minutes": 15,
        "observation_window_hours": 24,
        "selection_rules": [
            "source status is ok",
            "exclude candles whose interval ends after window_end",
            "at least 2 eligible candles",
            "no internal missing 15-minute intervals",
            "first completed candle no more than 15 minutes after launch",
            "last completed candle no more than 15 minutes before window_end",
        ],
        "timestamp_convention": "All converted candle timestamps represent interval close.",
        "reason_counts": dict(reason_counts),
        "records": manifest_records,
    }

    (OUTPUT_DIR / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    print("NOVEMBER ADAPTER PREPARATION COMPLETE")
    print(f"Source records: {len(records)}")
    print(f"Unique pools: {len(seen_pools)}")
    print(f"Selected pools: {selected_count}")
    print(f"Selected candles: {candle_total}")
    print("\nSelection and exclusion counts:")
    for reason, count in sorted(reason_counts.items()):
        print(f"  {reason}: {count}")

    print(f"\nCandle directory: {CANDLE_DIR}")
    print(f"Manifest: {OUTPUT_DIR / 'cohort_manifest.json'}")


if __name__ == "__main__":
    main()
