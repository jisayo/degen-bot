import json
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

DATA = Path("results/launch_data")
INPUT = Path(__import__("os").environ.get("LAUNCH_CLASSIFICATIONS_INPUT", str(DATA / "classified_launches.jsonl")))
OUTPUT = DATA / "launch_pool_map.jsonl"
API = "https://api.geckoterminal.com/api/v2/networks/solana/tokens"

def now():
    return datetime.now(timezone.utc).isoformat()

def main():
    DATA.mkdir(parents=True, exist_ok=True)

    launches = {}
    for line in INPUT.read_text().splitlines():
        try:
            row = json.loads(line)
            if row.get("status") == "confirmed_launch" and row.get("mint"):
                launches[row["mint"]] = row
        except (ValueError, TypeError):
            continue

    seen = set()
    if OUTPUT.exists():
        for line in OUTPUT.read_text().splitlines():
            try:
                row = json.loads(line)
                seen.add((row["mint"], row["pool_address"]))
            except (ValueError, KeyError):
                continue

    mapped_mints = {mint for mint, _ in seen}
    session = requests.Session()
    session.headers["User-Agent"] = "degen-bot-launch-research/1.0"
    matched = 0
    empty = 0
    skipped = 0

    for mint, launch in launches.items():
        if mint in mapped_mints:
            skipped += 1
            continue
        try:
            url = f"{API}/{mint}/pools"
            response = session.get(url, timeout=20)

            if response.status_code == 429:
                print("HTTP 429: stopping safely; rerun later.")
                return
            response.raise_for_status()
            pools = response.json().get("data", [])
            count = 0

            for pool in pools:
                a = pool.get("attributes", {})
                rel = pool.get("relationships", {})
                base = rel.get("base_token", {}).get("data", {}).get("id", "")
                quote = rel.get("quote_token", {}).get("data", {}).get("id", "")

                if f"solana_{mint}" not in (base, quote):
                    continue

                address = a.get("address")
                if not address or (mint, address) in seen:
                    continue

                record = {
                    "mint": mint,
                    "launch_signature": launch.get("signature"),
                    "pool_address": address,
                    "pool_name": a.get("name"),
                    "pool_created_at": a.get("pool_created_at"),
                    "price_usd": a.get("base_token_price_usd"),
                    "reserve_usd": a.get("reserve_in_usd"),
                    "volume_usd": a.get("volume_usd"),
                    "transactions": a.get("transactions"),
                    "dex": rel.get("dex", {}).get("data", {}).get("id"),
                    "matched_at": now(),
                }

                with OUTPUT.open("a") as f:
                    f.write(json.dumps(record) + "\n")

                seen.add((mint, address))
                count += 1

            matched += bool(count)
            empty += not bool(count)
            print(mint[:10], "pools:", count)
        except (requests.RequestException, ValueError) as exc:
            print("ERROR", mint[:10], type(exc).__name__)

        time.sleep(10)

    print(f"Launches: {len(launches)} | Already mapped: {skipped} | Matched: {matched} | No match: {empty}")
    print("Output:", OUTPUT)

if __name__ == "__main__":
    main()
