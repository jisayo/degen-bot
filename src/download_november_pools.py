import os
import json
import time
import requests

from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT / ".env")

API_KEY = os.getenv("DEXPAPRIKA_API_KEY")
if not API_KEY:
    raise SystemExit("ERROR: DEXPAPRIKA_API_KEY missing")

URL = "https://api.dexpaprika.com/networks/solana/pools/search"
OUT = ROOT / "results/launch_data/november_2026"
BATCH_DIR = OUT / "batches"

START = datetime(2026, 11, 1, tzinfo=timezone.utc)
END = datetime(2026, 11, 4, tzinfo=timezone.utc)
BATCH_HOURS = 3
PAGE_LIMIT = 100

BATCH_DIR.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({"Authorization": API_KEY})

def pool_id(pool):
    value = pool.get("id") or pool.get("pool_address") or pool.get("address")
    if not value:
        raise ValueError("Pool record has no identifiable pool ID")
    return str(value)

def fetch_batch(start, end):
    params = {
        "created_after": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_before": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": PAGE_LIMIT,
    }

    records = {}
    cursor = None
    seen_cursors = set()
    page = 0

    while True:
        request_params = dict(params)
        if cursor:
            request_params["cursor"] = cursor

        response = None

        for attempt in range(6):
            try:
                response = session.get(
                    URL,
                    params=request_params,
                    timeout=40,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    wait = min(60, 2 ** attempt)
                    print(f"  HTTP {response.status_code}; retrying in {wait}s")
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                break

            except requests.RequestException:
                if attempt == 5:
                    raise
                wait = min(60, 2 ** attempt)
                print(f"  Request error; retrying in {wait}s")
                time.sleep(wait)

        if response is None or not response.ok:
            raise RuntimeError("Unable to retrieve API page")

        data = response.json()
        results = data.get("results", [])

        if not isinstance(results, list):
            raise ValueError("Unexpected API response format")

        page += 1

        for pool in results:
            records[pool_id(pool)] = pool

        print(
            f"  Page {page}: {len(results)} pools | "
            f"{len(records)} unique"
        )

        if not data.get("has_next_page"):
            break

        next_cursor = data.get("next_cursor")

        if not next_cursor:
            raise RuntimeError("More pages reported but cursor missing")

        if next_cursor in seen_cursors:
            raise RuntimeError("Repeated pagination cursor detected")

        seen_cursors.add(next_cursor)
        cursor = next_cursor
        time.sleep(0.5)

    return records, page


def main():
    manifest = {
        "period_start": START.isoformat(),
        "period_end": END.isoformat(),
        "batch_hours": BATCH_HOURS,
        "expected_batches": 24,
        "completed_batches": [],
    }

    batch_start = START
    batch_number = 1

    while batch_start < END:
        batch_end = min(
            batch_start + timedelta(hours=BATCH_HOURS),
            END
        )

        batch_file = BATCH_DIR / f"batch_{batch_number:02d}.jsonl"

        print(f"\nBATCH {batch_number:02d}/24")
        print(f"UTC: {batch_start} -> {batch_end}")

        if batch_file.exists():
            print("Already completed; skipping.")
            batch_start = batch_end
            batch_number += 1
            continue

        records, pages = fetch_batch(batch_start, batch_end)

        temp_file = batch_file.with_suffix(".tmp")

        with temp_file.open("w") as f:
            for record in records.values():
                f.write(json.dumps(record) + "\n")

        temp_file.replace(batch_file)

        print(f"Saved: {len(records)} unique pools")
        print(f"Pages downloaded: {pages}")

        manifest["completed_batches"].append({
            "batch": batch_number,
            "start": batch_start.isoformat(),
            "end": batch_end.isoformat(),
            "unique_pools": len(records),
            "pages": pages,
        })

        batch_start = batch_end
        batch_number += 1

    print("\nBuilding combined dataset...")

    all_pools = {}

    for batch_file in sorted(BATCH_DIR.glob("batch_*.jsonl")):
        with batch_file.open() as f:
            for line in f:
                if line.strip():
                    pool = json.loads(line)
                    all_pools[pool_id(pool)] = pool

    combined = OUT / "pools.jsonl"
    temp_combined = OUT / "pools.jsonl.tmp"

    with temp_combined.open("w") as f:
        for pool in all_pools.values():
            f.write(json.dumps(pool) + "\n")

    temp_combined.replace(combined)

    manifest["completed_batch_count"] = len(
        list(BATCH_DIR.glob("batch_*.jsonl"))
    )
    manifest["total_unique_pools"] = len(all_pools)
    manifest["complete"] = (
        manifest["completed_batch_count"] == 24
    )

    with (OUT / "manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)

    print("\n========== COLLECTION SUMMARY ==========")
    print("Completed batches:", manifest["completed_batch_count"], "/ 24")
    print("Unique pools:", len(all_pools))
    print("Complete:", manifest["complete"])
    print("Dataset:", combined)
    print("Manifest:", OUT / "manifest.json")


if __name__ == "__main__":
    main()
