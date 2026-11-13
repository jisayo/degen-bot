import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

API_KEY = os.getenv("DEXPAPRIKA_API_KEY")
if not API_KEY:
    raise SystemExit("Missing DEXPAPRIKA_API_KEY in .env")

ROOT = Path("results/launch_data/november_2026")
OUTPUT = ROOT / "candles"
BATCH_OUTPUT = OUTPUT / "batches"

BATCH_OUTPUT.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.dexpaprika.com/networks/solana/pools"
INTERVAL = "10m"
LIMIT = 144
REQUEST_DELAY = 3.0
MAX_RETRIES = 8

session = requests.Session()
session.headers.update({"Authorization": API_KEY})


def read_completed(path):
    completed = set()
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if record.get("status") in ("ok", "no_candles"):
                        completed.add(record["pool_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return completed


def get_candles(pool):
    pool_id = pool["id"]
    created = datetime.fromisoformat(
        pool["created_at"].replace("Z", "+00:00")
    )
    end = created + timedelta(hours=24)

    params = {
        "start": created.isoformat(),
        "end": end.isoformat(),
        "interval": INTERVAL,
        "limit": LIMIT,
    }

    url = f"{BASE_URL}/{pool_id}/ohlcv"

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=30)

            if response.status_code in (401, 403):
                raise SystemExit(
                    f"Authentication failed: HTTP {response.status_code}. "
                    "Check your API key."
                )

            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")

                try:
                    server_delay = float(retry_after) if retry_after else 0
                except ValueError:
                    server_delay = 0

                delay = max(server_delay, min(5 * (2 ** attempt), 180))

                print(
                    f"Rate limited/server error for {pool_id}. "
                    f"Retrying in {delay:.1f}s "
                    f"(HTTP {response.status_code})"
                )
                time.sleep(delay)
                continue

            response.raise_for_status()
            payload = response.json()

            if isinstance(payload, list):
                candles = payload
            elif isinstance(payload, dict):
                candles = None

                for key in ("ohlcv", "data", "results"):
                    if key in payload:
                        if not isinstance(payload[key], list):
                            return {
                                "pool_id": pool_id,
                                "error": f"Unexpected response structure: {key} is not a list",
                            }
                        candles = payload[key]
                        break

                if candles is None:
                    return {
                        "pool_id": pool_id,
                        "error": f"Unrecognised JSON response keys: {list(payload.keys())}",
                    }
            else:
                return {
                    "pool_id": pool_id,
                    "error": f"Unexpected JSON response type: {type(payload).__name__}",
                }

            return {
                "pool_id": pool_id,
                "pool_created_at": pool["created_at"],
                "request_start": created.isoformat(),
                "request_end": end.isoformat(),
                "interval": INTERVAL,
                "status": "ok" if candles else "no_candles",
                "candle_count": len(candles),
                "candles": candles,
            }

        except requests.RequestException as error:
            if attempt == MAX_RETRIES - 1:
                return {"pool_id": pool_id, "error": str(error)}

            time.sleep(min(2 ** attempt, 120))

    return {"pool_id": pool_id, "error": "Maximum retries exceeded"}


total_completed = 0
total_failed = 0

for batch_num in range(1, 25):
    source = ROOT / "batches" / f"batch_{batch_num:02d}.jsonl"
    destination = BATCH_OUTPUT / f"candles_{batch_num:02d}.jsonl"
    completed = read_completed(destination)

    pools = [
        json.loads(line)
        for line in source.open()
        if line.strip()
    ]

    remaining = [p for p in pools if p["id"] not in completed]

    print(f"\nBatch {batch_num:02d}/24")
    print(f"Pools: {len(pools)} | Already downloaded: {len(completed)}")
    print(f"Remaining: {len(remaining)}")

    for index, pool in enumerate(remaining, 1):
        result = get_candles(pool)

        if "error" in result:
            total_failed += 1
            with (OUTPUT / "errors.jsonl").open("a") as f:
                f.write(json.dumps(result) + "\n")
            print(f"  FAILED {index}/{len(remaining)}: {pool['id']}")
        else:
            with destination.open("a") as f:
                f.write(json.dumps(result) + "\n")

            total_completed += 1
            print(
                f"  {index}/{len(remaining)} "
                f"{result['pool_id']}: {result['candle_count']} candles"
            )

        time.sleep(REQUEST_DELAY)

    print(f"Batch {batch_num:02d} finished.")

# Rebuild combined dataset from completed batch files.
combined = OUTPUT / "all_candles.jsonl"
total_pools = 0
total_candles = 0

with combined.open("w") as output:
    for file in sorted(BATCH_OUTPUT.glob("candles_*.jsonl")):
        with file.open() as source:
            for line in source:
                if not line.strip():
                    continue
                record = json.loads(line)
                output.write(json.dumps(record) + "\n")
                total_pools += 1
                total_candles += record.get("candle_count", 0)

manifest = {
    "interval": INTERVAL,
    "hours_per_pool": 24,
    "expected_pools": 6108,
    "downloaded_pools": total_pools,
    "total_candles": total_candles,
    "failed_this_run": total_failed,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}

(OUTPUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2)
)

print("\n========== DOWNLOAD SUMMARY ==========")
print(json.dumps(manifest, indent=2))
print("Output:", OUTPUT)
