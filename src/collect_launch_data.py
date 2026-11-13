import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.geckoterminal.com/api/v2/networks/solana"
OUT_DIR = Path("results/launch_data")
POOLS_FILE = OUT_DIR / "pools.jsonl"
OBS_FILE = OUT_DIR / "observations.jsonl"
DELAY = 120
TIMEOUT = 20

session = requests.Session()
session.headers.update({"User-Agent": "degen-bot-launch-research/1.0"})


def now():
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path, record):
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = set()

    if POOLS_FILE.exists():
        with POOLS_FILE.open() as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["pool_address"])
                except (ValueError, KeyError):
                    continue

    print("Launch collector running. Press Ctrl+C to stop.")
    print("Paper research only; no trades are executed.")

    while True:
        try:
            response = session.get(
                f"{BASE_URL}/new_pools",
                params={"page": 1},
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                print("Rate limited. Waiting 60 seconds.")
                time.sleep(120)
                continue

            response.raise_for_status()
            items = response.json().get("data", [])

            for item in items:
                attrs = item.get("attributes", {})
                address = attrs.get("address")
                if not address:
                    continue

                record = {
                    "pool_address": address,
                    "name": attrs.get("name"),
                    "created_at": attrs.get("pool_created_at"),
                    "first_seen_at": now(),
                    "reserve_usd": attrs.get("reserve_in_usd"),
                    "fdv_usd": attrs.get("fdv_usd"),
                    "source": "GeckoTerminal new_pools",
                }

                if address not in seen:
                    append_jsonl(POOLS_FILE, record)
                    seen.add(address)
                    print("New pool:", address, record["name"])

                # Save repeat observations too, so changes can be analysed.
                append_jsonl(OBS_FILE, {
                    "pool_address": address,
                    "observed_at": now(),
                    "reserve_usd": attrs.get("reserve_in_usd"),
                    "fdv_usd": attrs.get("fdv_usd"),
                    "market_data": attrs,
                })

            print(f"{now()} | Feed records: {len(items)} | Unique pools: {len(seen)}")

        except (requests.RequestException, ValueError) as exc:
            print("Collection error:", exc)

        time.sleep(DELAY)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCollector stopped.")
