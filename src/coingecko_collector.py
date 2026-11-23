
import os
import json
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "results" / "launch_data" / "november_2026"

SOURCE_DIR = DATA_DIR / "coingecko" / "source_batches"
OUTPUT_DIR = DATA_DIR / "coingecko" / "1m_5m"
BATCH_DIR = OUTPUT_DIR / "batches"

NETWORK = "solana"
AGGREGATE = 5
CANDLE_LIMIT = 1000

API_BASE = "https://api.coingecko.com/api/v3"

load_dotenv(ROOT / ".env")

API_KEYS = []
for name in (
    "COINGECKO_DEMO_API_KEY_1",
    "COINGECKO_DEMO_API_KEY_2",
    "COINGECKO_DEMO_API_KEY",
):
    value = os.getenv(name, "").strip()
    if value and value not in API_KEYS:
        API_KEYS.append(value)

HEADERS = {"accept": "application/json"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HELPERS
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)



def load_pools():
    source_dir = SOURCE_DIR
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)

    pools = []
    seen = set()

    for number in range(1, 25):
        path = source_dir / f"batch_{number:02d}.jsonl"
        if not path.exists():
            raise FileNotFoundError(path)

        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue

                record = json.loads(line)
                address = record.get("id")
                created_at = record.get("created_at")
                tokens = [
                    token.get("id")
                    for token in record.get("tokens", [])
                    if token.get("id")
                    and token.get("id") !=
                    "So11111111111111111111111111111111111111112"
                ]

                if not address or not created_at or not tokens:
                    continue
                if address in seen:
                    raise ValueError(f"Duplicate pool: {address}")

                created = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )

                pools.append({
                    "pool_address": address,
                    "created_at": created_at,
                    "launch_timestamp": int(created.timestamp()),
                    "token_address": tokens[0],
                    "source_record": {}
                })
                seen.add(address)

    return pools


class CoinGeckoRequestError(Exception):
    """Raised when a CoinGecko request fails after retries."""


class CoinGeckoNotFoundError(CoinGeckoRequestError):
    """Raised when CoinGecko returns HTTP 404."""


def api_request(url, params=None, retries=5):
    if not API_KEYS:
        raise RuntimeError("No CoinGecko API keys configured.")

    last_error = "Unknown API failure"
    rejected_keys = set()

    for attempt in range(retries):
        rate_limited = False

        for index, api_key in enumerate(API_KEYS):
            if index in rejected_keys:
                continue

            try:
                response = session.get(
                    url,
                    params=params,
                    timeout=30,
                    headers={"x-cg-demo-api-key": api_key}
                )

                status = response.status_code

                if status in (401, 403):
                    rejected_keys.add(index)
                    logging.warning(
                        "CoinGecko key slot %s rejected: HTTP %s",
                        index + 1, status
                    )
                    continue

                if status == 429:
                    rate_limited = True
                    last_error = "HTTP 429 rate limit"
                    logging.warning(
                        "Key slot %s rate limited; trying next key.",
                        index + 1
                    )
                    continue

                if status == 404:
                    raise CoinGeckoNotFoundError(
                        f"HTTP 404: pool endpoint unavailable. "
                        f"Response: {response.text[:300]}"
                    )

                if status >= 500:
                    last_error = f"HTTP {status} server error"
                    logging.warning(
                        "CoinGecko server error: HTTP %s", status
                    )
                    continue

                response.raise_for_status()
                return response.json()

            except (CoinGeckoRequestError, RuntimeError):
                raise

            except (requests.RequestException, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logging.warning(
                    "Request failed using key slot %s: %s",
                    index + 1, last_error
                )

        if len(rejected_keys) == len(API_KEYS):
            raise RuntimeError(
                "All configured CoinGecko API keys were rejected."
            )

        if attempt < retries - 1:
            wait = min(60, 5 * (attempt + 1)) if rate_limited else 2 * (attempt + 1)
            logging.warning("Retrying in %s seconds.", wait)
            time.sleep(wait)

    raise CoinGeckoRequestError(
        f"CoinGecko request failed after {retries} attempts: {last_error}"
    )


# ============================================================
# COINGECKO API
# ============================================================

def test_authentication():
    url = f"{API_BASE}/onchain/networks/{NETWORK}/dexes"
    results = []

    for index, api_key in enumerate(API_KEYS, start=1):
        try:
            response = session.get(
                url,
                params={"page": 1},
                timeout=30,
                headers={"x-cg-demo-api-key": api_key}
            )

            status = response.status_code

            if status == 200:
                response.json()
                logging.info("API key slot %s: AUTHENTICATED", index)
                results.append(True)
            elif status == 429:
                logging.warning(
                    "API key slot %s: RATE LIMITED (not an auth failure)",
                    index
                )
                results.append(False)
            else:
                logging.error(
                    "API key slot %s: HTTP %s",
                    index, status
                )
                results.append(False)

        except (requests.RequestException, ValueError) as exc:
            logging.error(
                "API key slot %s: %s",
                index, type(exc).__name__
            )
            results.append(False)

    successful = sum(results)

    logging.info(
        "Authentication results: %s/%s keys successful",
        successful, len(API_KEYS)
    )

    if successful == 0:
        raise RuntimeError(
            "No CoinGecko API keys authenticated successfully."
        )

    return True


def download_pool_ohlcv(pool):
    address = pool["pool_address"]
    launch = pool["launch_timestamp"]
    start = (launch // (AGGREGATE * 60)) * (AGGREGATE * 60)
    end = launch + 86400

    url = (
        f"{API_BASE}/onchain/networks/{NETWORK}/"
        f"pools/{address}/ohlcv/minute"
    )

    params = {
        "aggregate": AGGREGATE,
        "limit": CANDLE_LIMIT,
        "currency": "usd",
        "token": pool["token_address"],
        "before_timestamp": end,
        "include_empty_intervals": "true"
    }

    data = api_request(url, params)
    if not data:
        return None

    attributes = data.get("data", {}).get("attributes", {})
    raw_candles = attributes.get("ohlcv_list", [])
    candles = []

    for row in raw_candles:
        if len(row) != 6:
            continue

        timestamp, open_, high, low, close, volume = row
        timestamp = int(timestamp)

        if not start <= timestamp < end:
            continue

        candles.append({
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(
                timestamp, timezone.utc
            ).isoformat(),
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume)
        })

    return {
        "pool_address": address,
        "token_address": pool["token_address"],
        "network": NETWORK,
        "interval": f"{AGGREGATE}m",
        "provider": "coingecko",
        "launch_time": pool["created_at"],
        "window_end": datetime.fromtimestamp(
            end, timezone.utc
        ).isoformat(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "candles": sorted(candles, key=lambda x: x["timestamp"])
    }

def validate_result(result):
    if not result:
        return False, "No response"

    candles = result.get("candles", [])

    if not candles:
        return True, "No candles"

    previous = None

    for candle in candles:
        prices = [
            candle["open"],
            candle["high"],
            candle["low"],
            candle["close"]
        ]

        if any(p <= 0 for p in prices):
            return False, "Invalid price"

        if candle["high"] < max(
            candle["open"], candle["close"]
        ):
            return False, "Invalid high"

        if candle["low"] > min(
            candle["open"], candle["close"]
        ):
            return False, "Invalid low"

        if previous is not None:
            if candle["timestamp"] <= previous:
                return False, "Duplicate or unordered candles"

        previous = candle["timestamp"]

    return True, "Valid"


# ============================================================
# SAMPLE COLLECTION
# ============================================================


def collect_sample(sample_size=20):
    pools = load_pools()

    # Build a diversified sample: high volume, high liquidity,
    # low liquidity, and evenly distributed records.
    selected = []
    selected_ids = set()

    def add(records, limit):
        for pool in records:
            if len(selected) >= sample_size or limit <= 0:
                break
            address = pool["pool_address"]
            if address not in selected_ids:
                selected.append(pool)
                selected_ids.add(address)
                limit -= 1

    quarter = max(1, sample_size // 4)

    add(sorted(
        pools,
        key=lambda p: p["source_record"].get("volume_usd_24h") or 0,
        reverse=True
    ), quarter)

    add(sorted(
        pools,
        key=lambda p: p["source_record"].get("liquidity_usd") or 0,
        reverse=True
    ), quarter)

    add(sorted(
        pools,
        key=lambda p: p["source_record"].get("liquidity_usd") or 0
    ), quarter)

    remaining = [p for p in pools if p["pool_address"] not in selected_ids]
    needed = min(sample_size - len(selected), len(remaining))

    if needed:
        indexes = [
            round(i * (len(remaining) - 1) / max(needed - 1, 1))
            for i in range(needed)
        ]
        add([remaining[i] for i in indexes], needed)

    output_file = OUTPUT_DIR / "sample_results.jsonl"
    existing = set()

    if output_file.exists():
        with output_file.open() as f:
            for line in f:
                try:
                    existing.add(json.loads(line).get("pool_address"))
                except json.JSONDecodeError:
                    continue

    pending = [
        p for p in selected
        if p["pool_address"] not in existing
    ]

    summary = {
        "dataset_pools": len(pools),
        "sample_target": len(selected),
        "already_collected": len(selected) - len(pending),
        "new_requests": len(pending),
        "successful": 0,
        "failed": 0,
        "valid": 0,
        "invalid": 0
    }

    with output_file.open("a") as output:
        for index, pool in enumerate(pending, 1):
            logging.info(
                "[%s/%s] %s",
                index, len(pending), pool["pool_address"]
            )

            result = download_pool_ohlcv(pool)

            if result is None:
                summary["failed"] += 1
                result = {
                    "pool_address": pool["pool_address"],
                    "status": "request_failed",
                    "candles": []
                }
            else:
                summary["successful"] += 1

            valid, reason = validate_result(result)
            result["validation"] = {
                "valid": valid,
                "reason": reason
            }

            if valid:
                summary["valid"] += 1
            else:
                summary["invalid"] += 1

            output.write(json.dumps(result) + "\n")
            output.flush()

            logging.info(
                "Candles: %s | Valid: %s | %s",
                len(result.get("candles", [])), valid, reason
            )

            time.sleep(2)

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary_file = OUTPUT_DIR / (
        "sample_summary_" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") +
        ".json"
    )

    with summary_file.open("x") as f:
        json.dump(summary, f, indent=2)

    logging.info("SAMPLE COMPLETE")
    logging.info(json.dumps(summary, indent=2))

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test-auth",
        action="store_true"
    )

    parser.add_argument(
        "--sample",
        type=int,
        default=0
    )

    args = parser.parse_args()

    if not API_KEYS:
        raise RuntimeError(
            "Set COINGECKO_DEMO_API_KEY_1 and/or "
            "COINGECKO_DEMO_API_KEY_2 in .env"
        )

    prepare_directories()

    if args.test_auth:
        test_authentication()

    elif args.sample:
        test_authentication()
        collect_sample(args.sample)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
