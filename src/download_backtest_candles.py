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

OUT_DIR.mkdir(parents=True, exist_ok=True)
pools_data = json.loads(POOLS_FILE.read_text())
pools = pools_data.get("pools", [])

# Include the known older test pool, even if discovery missed it.
known_pool = "12jc1DzJpzbCDaKuM4brAKh9jcFry2TLG1FfGsL4ftCG"
if not any(p.get("address") == known_pool for p in pools):
    pools.append({"address": known_pool, "name": "Known historical test pool"})

session = requests.Session()
results = []

for i, pool in enumerate(pools, 1):
    address = pool.get("address") or pool.get("pool_address")
    if not address:
        continue

    output = OUT_DIR / f"{address}.json"
    if output.exists():
        print(f"[{i}/{len(pools)}] Already saved: {address}")
        continue

    url = (
        "https://api.geckoterminal.com/api/v2/networks/solana/"
        f"pools/{address}/ohlcv/minute"
    )

    try:
        response = session.get(
            url,
            params={
                "aggregate": 15,
                "limit": 1000,
                "currency": "usd",
                "before_timestamp": END,
            },
            timeout=30,
        )

        if response.status_code == 429:
            print("Rate limited. Stopping safely; rerun later.")
            break

        response.raise_for_status()
        data = response.json()
        candles = data.get("data", {}).get("attributes", {}).get(
            "ohlcv_list", []
        )
        candles = [
            c for c in candles
            if len(c) >= 6 and START <= c[0] < END
        ]
        candles.sort(key=lambda c: c[0])

        record = {
            "pool_address": address,
            "name": pool.get("name", ""),
            "source": "GeckoTerminal OHLCV",
            "interval_minutes": 15,
            "period_start_utc": datetime.fromtimestamp(
                START, timezone.utc
            ).isoformat(),
            "period_end_exclusive_utc": datetime.fromtimestamp(
                END, timezone.utc
            ).isoformat(),
            "candles": candles,
        }
        output.write_text(json.dumps(record, indent=2))
        results.append((address, len(candles)))
        print(f"[{i}/{len(pools)}] {address}: {len(candles)} candles")

    except Exception as exc:
        print(f"[{i}/{len(pools)}] Failed {address}: {exc}")

    time.sleep(7)

print("\nFinished this download pass.")
print("New pool files:", len(results))
print("Candle files saved under:", OUT_DIR)
