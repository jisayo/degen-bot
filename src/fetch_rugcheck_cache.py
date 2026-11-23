import json
import time
import argparse
from pathlib import Path
import requests
import rugcheck_api

CACHE_FILE = Path("data/rugcheck_cache.json")
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
SOURCE_DIR = Path("results/launch_data/november_2026/coingecko/source_batches")
OUT_BATCHES = Path("results/launch_data/november_2026/coingecko/1m_5m/batches")


def load_cohort_tokens():
    """Returns pool_id -> token_mint mapping across all batches."""
    pool_to_token = {}
    for f in sorted(SOURCE_DIR.glob("batch_*.jsonl")):
        for line in f.open():
            if not line.strip():
                continue
            r = json.loads(line)
            pid = r.get("id")
            tokens = [
                t.get("id") for t in r.get("tokens", [])
                if t.get("id") and t.get("id") != "So11111111111111111111111111111111111111112"
            ]
            if pid and tokens:
                pool_to_token[pid] = tokens[0]
    return pool_to_token


def fetch_token_rugcheck(mint: str, max_retries: int = 4):
    """
    Fetches RugCheck report with automatic backoff on 429 rate limits.
    Returns (report_data: dict, status: str).
    """
    url = f"{rugcheck_api.BASE_URL}/{mint}/report"
    delay = 4.0

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=15,
            )

            if resp.status_code == 200:
                report = resp.json()
                score = report.get("score_normalised")
                if score is None:
                    score = report.get("score", 0)
                rugged = bool(report.get("rugged", False))
                risks = [
                    r.get("name") for r in report.get("risks", [])
                    if isinstance(r, dict)
                ]
                return {
                    "mint": mint,
                    "score": score,
                    "rugged": rugged,
                    "risks": risks,
                    "status": "ok",
                }, "ok"

            elif resp.status_code == 429:
                # Rate limited - read retry-after or exponential backoff
                retry_after = resp.headers.get("Retry-After")
                wait_sec = float(retry_after) if retry_after else (delay * attempt)
                print(f"  [429 Rate Limited] Sleeping {wait_sec:.1f}s before retry...")
                time.sleep(wait_sec)
                continue

            elif resp.status_code == 404:
                return {
                    "mint": mint,
                    "score": 100,
                    "rugged": False,
                    "risks": ["Token not found on RugCheck"],
                    "status": "not_found",
                }, "not_found"

            else:
                resp.raise_for_status()

        except requests.RequestException as exc:
            if attempt < max_retries:
                time.sleep(delay)
            else:
                return {
                    "mint": mint,
                    "score": 100,
                    "rugged": False,
                    "risks": [f"Request error: {str(exc)[:60]}"],
                    "status": "error",
                }, "error"

    return {
        "mint": mint,
        "score": 100,
        "rugged": False,
        "risks": ["Max retries exceeded"],
        "status": "error",
    }, "error"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max tokens to process (0 = all)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    pool_to_token = load_cohort_tokens()
    unique_mints = sorted(set(pool_to_token.values()))

    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except Exception:
            cache = {}

    # Only process mints that are either not in cache or previously errored on lookup
    pending = [
        mint for mint in unique_mints
        if mint not in cache or cache[mint].get("status") in ("error", "Lookup failed")
    ]

    if args.limit > 0:
        pending = pending[:args.limit]

    print(f"Total unique tokens: {len(unique_mints)}")
    print(f"Already cached (OK/Not Found): {len(cache) - sum(1 for m in cache.values() if m.get('status') == 'error')}")
    print(f"Pending requests to fetch: {len(pending)}")

    for idx, mint in enumerate(pending, 1):
        print(f"[{idx}/{len(pending)}] RugCheck {mint}...", end="", flush=True)
        record, status = fetch_token_rugcheck(mint)
        cache[mint] = record
        print(f" -> score={record['score']}, rugged={record['rugged']} ({status})")

        if idx % 10 == 0 or idx == len(pending):
            CACHE_FILE.write_text(json.dumps(cache, indent=2))

        time.sleep(args.delay)

    CACHE_FILE.write_text(json.dumps(cache, indent=2))
    print(f"\nRugCheck cache update complete: {len(cache)} total records saved in {CACHE_FILE}")


if __name__ == "__main__":
    main()
