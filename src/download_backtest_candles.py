import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

BASE = Path("results/historical_data")
POOLS_FILE = BASE / "pools.json"
OUT_DIR = BASE / "candles"

START = int(datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp())

BASE_URL = "https://api.geckoterminal.com/api/v2/networks/solana"
DELAY = 7
HISTORY_SECONDS = 7 * 24 * 60 * 60
OUT_DIR.mkdir(parents=True, exist_ok=True)

pools_data = json.loads(POOLS_FILE.read_text())
pools = pools_data.get("pools", [])

known_pool = "12jc1DzJpzbCDaKuM4brAKh9jcFry2TLG1FfGsL4ftCG"

# Support both pool_address and address.
if not any(
    p.get("address") == known_pool
    or p.get("pool_address") == known_pool
    for p in pools
):
    pools.append({
        "pool_address": known_pool,
        "name": "Known historical test pool",
    })

# Deduplicate pools while preserving order.
unique_pools = {}
for pool in pools:
    address = pool.get("pool_address") or pool.get("address")
    if address:
        unique_pools.setdefault(address, pool)

session = requests.Session()
session.headers.update({"User-Agent": "degen-bot-backtest/1.0"})

saved = 0
skipped = 0
failed = 0

for i, (address, pool) in enumerate(unique_pools.items(), 1):
    output = OUT_DIR / f"{address}.json"

    # Use each pool's creation time as its historical start.
    created_at = pool.get("created_at")
    if created_at:
        pool_start = int(
            datetime.fromisoformat(
                created_at.replace("Z", "+00:00")
            ).timestamp()
        )
        pool_end = pool_start + HISTORY_SECONDS
    else:
        # Preserve the old date window for pools without a timestamp.
        pool_start = START
        pool_end = END

    # Skip only existing files containing actual candles.
    if output.exists():
        try:
            existing = json.loads(output.read_text())
            if existing.get("candles"):
                print(f"[{i}/{len(unique_pools)}] Already saved: {address}")
                skipped += 1
                continue
        except (json.JSONDecodeError, OSError):
            pass

    url = f"{BASE_URL}/pools/{address}/ohlcv/minute"

    try:
        response = session.get(
            url,
            params={
                "aggregate": 15,
                "limit": 1000,
                "currency": "usd",
                "before_timestamp": pool_end,
            },
            timeout=30,
        )

        if response.status_code == 429:
            print("Rate limited (429). Stopping safely; rerun later.")
            break

        response.raise_for_status()
        payload = response.json()
        candles = (
            payload.get("data", {})
            .get("attributes", {})
            .get("ohlcv_list", [])
        )

        candles = [
            c for c in candles
            if isinstance(c, list)
            and len(c) >= 6
            and pool_start <= c[0] < pool_end
        ]
        candles.sort(key=lambda c: c[0])

        if not candles:
            print(f"[{i}/{len(unique_pools)}] No candles: {address}")
            failed += 1
            continue

        record = {
            "pool_address": address,
            "name": pool.get("name", ""),
            "source": "GeckoTerminal OHLCV",
            "interval_minutes": 15,
            "period_start_utc": datetime.fromtimestamp(
                pool_start, timezone.utc
            ).isoformat(),
            "period_end_exclusive_utc": datetime.fromtimestamp(
                pool_end, timezone.utc
            ).isoformat(),
            "candles": candles,
        }

        # Write only validated, non-empty candle results.
        output.write_text(json.dumps(record, indent=2))
        saved += 1
        print(f"[{i}/{len(unique_pools)}] {address}: {len(candles)} candles")

    except (requests.RequestException, ValueError, TypeError) as exc:
        failed += 1
        print(f"[{i}/{len(unique_pools)}] Failed {address}: {exc}")

    time.sleep(DELAY)

print("\nDownload pass complete.")
print("New files saved:", saved)
print("Existing files skipped:", skipped)
print("Failed or empty results:", failed)
print("Output directory:", OUT_DIR)
