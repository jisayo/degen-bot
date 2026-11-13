import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.geckoterminal.com/api/v2/networks/solana"
OUT_DIR = Path("results/launch_data")
POOLS_FILE = OUT_DIR / "pools.jsonl"
TRACK_FILE = OUT_DIR / "tracked_observations.jsonl"

BATCH_SIZE = 10
BATCH_DELAY = 15
CYCLE_DELAY = 300
TIMEOUT = 20

session = requests.Session()
session.headers.update({"User-Agent": "degen-bot-pool-tracker/1.0"})


def now():
    return datetime.now(timezone.utc).isoformat()


def load_pools():
    pools = {}
    files = [OUT_DIR / "launch_pool_map.jsonl"]

    for path in files:
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                    address = row.get("pool_address") or row.get("address")
                    if address:
                        pools[address] = row
                except (json.JSONDecodeError, TypeError):
                    continue

    return pools


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Pool tracker running. Press Ctrl+C to stop.")
    print("Output:", TRACK_FILE)
    print("Paper research only; no trades are executed.")

    while True:
        pools = load_pools()
        addresses = list(pools)
        saved = 0
        errors = 0

        if not addresses:
            print("No pools found. Start the launch collector first.")
            time.sleep(CYCLE_DELAY)
            continue

        for start in range(0, len(addresses), BATCH_SIZE):
            batch = addresses[start:start + BATCH_SIZE]
            url = f"{BASE_URL}/pools/multi/{','.join(batch)}"

            try:
                response = session.get(url, timeout=TIMEOUT)

                if response.status_code == 429:
                    print("Rate limited; waiting 120 seconds.")
                    time.sleep(120)
                    break

                response.raise_for_status()
                items = response.json().get("data", [])

                for item in items:
                    attrs = item.get("attributes", {})
                    address = attrs.get("address")

                    if not address:
                        item_id = item.get("id", "")
                        if item_id.startswith("solana_"):
                            address = item_id[len("solana_"):]

                    if not address:
                        continue

                    snapshot = {
                        "pool_address": address,
                        "observed_at": now(),
                        "name": attrs.get("name"),
                        "created_at": attrs.get("pool_created_at"),
                        "price_usd": attrs.get("base_token_price_usd"),
                        "reserve_usd": attrs.get("reserve_in_usd"),
                        "fdv_usd": attrs.get("fdv_usd"),
                        "market_cap_usd": attrs.get("market_cap_usd"),
                        "price_change_percentage": attrs.get("price_change_percentage"),
                        "transactions": attrs.get("transactions"),
                        "volume_usd": attrs.get("volume_usd"),
                        "market_data": attrs,
                    }

                    with TRACK_FILE.open("a") as f:
                        f.write(json.dumps(snapshot) + "\n")
                    saved += 1

                print(
                    f"Batch {start // BATCH_SIZE + 1}: "
                    f"{len(items)} returned; snapshots saved={saved}"
                )

            except (requests.RequestException, ValueError) as exc:
                errors += 1
                print("Request error:", exc)

            time.sleep(BATCH_DELAY)

        print(
            f"{now()} | known pools={len(addresses)} | "
            f"snapshots saved={saved} | errors={errors}"
        )
        time.sleep(CYCLE_DELAY)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPool tracker stopped.")
