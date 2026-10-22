import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://api.geckoterminal.com/api/v2/networks/solana"
OUTPUT_DIR = Path("results/historical_data")
JSON_FILE = OUTPUT_DIR / "pools.json"
CSV_FILE = OUTPUT_DIR / "pools.csv"

START_DATE = "2026-10-10T00:00:00+00:00"
END_DATE = "2026-10-18T00:00:00+00:00"
MAX_PAGES = 10
REQUEST_DELAY = 7
TIMEOUT = 20

session = requests.Session()
session.headers.update({"User-Agent": "degen-bot-historical-research/1.0"})


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pools = {}
    errors = []

    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}/new_pools"
        try:
            response = session.get(
                url, params={"page": page}, timeout=TIMEOUT
            )
            print(f"Page {page}: HTTP {response.status_code}")
            response.raise_for_status()
            data = response.json().get("data", [])

            if not isinstance(data, list) or not data:
                print("No more pool records returned.")
                break

            oldest_date = None

            for item in data:
                attributes = item.get("attributes", {})
                address = attributes.get("address")
                created = attributes.get("pool_created_at")
                created_dt = parse_date(created)

                if created_dt and (
                    oldest_date is None or created_dt < oldest_date
                ):
                    oldest_date = created_dt

                if not address or not created_dt:
                    continue

                if not (
                    parse_date(START_DATE)
                    <= created_dt
                    < parse_date(END_DATE)
                ):
                    continue

                pools[address] = {
                    "pool_address": address,
                    "name": attributes.get("name"),
                    "created_at": created,
                    "reserve_usd": attributes.get("reserve_in_usd"),
                    "market_cap_usd": attributes.get("market_cap_usd"),
                    "fdv_usd": attributes.get("fdv_usd"),
                    "source": "GeckoTerminal new_pools",
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }

            print(f"  Records: {len(data)}; matched range: {len(pools)}")

            # Pagination is recent-first; stop once records are older
            # than the requested window.
            if oldest_date and oldest_date < parse_date(START_DATE):
                break

        except (requests.RequestException, ValueError) as exc:
            errors.append({"page": page, "error": str(exc)})
            print(f"  Request failed: {exc}")
            break

        if page < MAX_PAGES:
            time.sleep(REQUEST_DELAY)

    records = sorted(pools.values(), key=lambda row: row["created_at"])
    JSON_FILE.write_text(json.dumps({
        "period_utc": {"start": START_DATE, "end_exclusive": END_DATE},
        "source": "GeckoTerminal new_pools endpoint",
        "coverage_warning": (
            "This is a limited paginated discovery sample, not a complete "
            "historical token universe. Current pagination may not expose "
            "all pools created in the requested period."
        ),
        "pool_count": len(records),
        "errors": errors,
        "pools": records,
    }, indent=2))

    fields = [
        "pool_address", "name", "created_at", "reserve_usd",
        "market_cap_usd", "fdv_usd", "source", "collected_at",
    ]
    with CSV_FILE.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f"\nSaved {len(records)} pool records.")
    print(f"JSON: {JSON_FILE}")
    print(f"CSV:  {CSV_FILE}")
    print("Coverage is not guaranteed complete.")


if __name__ == "__main__":
    main()
