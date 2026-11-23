import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

import coingecko_collector as cg

DATA = cg.DATA_DIR
SOURCE_BATCH_DIR = DATA / "coingecko" / "source_batches"
OUT = DATA / "coingecko" / "1m_5m"
BATCH_OUT = OUT / "batches"
WRAPPED_SOL = "So11111111111111111111111111111111111111112"


def load_batch(number):
    path = SOURCE_BATCH_DIR / f"batch_{number:02d}.jsonl"
    if not path.exists():
        raise FileNotFoundError(path)

    pools = []
    seen = set()

    with path.open() as f:
        for line in f:
            if not line.strip():
                continue

            r = json.loads(line)
            address = r.get("id")
            if not address or address in seen:
                raise ValueError(f"Missing or duplicate pool: {address}")
            seen.add(address)

            tokens = [
                t.get("id") for t in r.get("tokens", [])
                if t.get("id") and t.get("id") != WRAPPED_SOL
            ]
            created = r.get("created_at")

            if not created or not tokens:
                pools.append({
                    "pool_address": address,
                    "source_metadata_unavailable": True
                })
                continue

            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            pools.append({
                "pool_address": address,
                "token_address": tokens[0],
                "created_at": created,
                "launch_timestamp": int(dt.timestamp())
            })

    return pools


def completed_ids(path):
    done = set()
    if not path.exists():
        return done

    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("status") in (
                    "unavailable", "source_metadata_unavailable"
                ):
                    done.add(r["pool_address"])
                elif (
                    r.get("status") in ("ok", "no_candles")
                    and r.get("validation", {}).get("valid") is True
                ):
                    done.add(r["pool_address"])
            except (ValueError, KeyError, TypeError):
                continue
    return done


def collect_batch(number, limit, delay):
    pools = load_batch(number)
    output = BATCH_OUT / f"batch_{number:02d}.jsonl"
    errors = OUT / "errors.jsonl"

    done = completed_ids(output)

    for pool in pools:
        if pool.get("source_metadata_unavailable"):
            address = pool["pool_address"]
            if address not in done:
                record = {
                    "pool_address": address,
                    "batch": number,
                    "status": "source_metadata_unavailable",
                    "error": "Token address or launch timestamp unavailable"
                }
                with output.open("a") as f:
                    f.write(json.dumps(record) + "\n")
                done.add(address)

    eligible = [p for p in pools if not p.get(
        "source_metadata_unavailable"
    )]
    pending = [p for p in eligible if p["pool_address"] not in done]
    if limit:
        pending = pending[:limit]

    print(f"Batch {number:02d}: source={len(pools)}, "
          f"queryable={len(eligible)}, completed={len(done)}, "
          f"pending={len(pending)}")

    for i, pool in enumerate(pending, 1):
        address = pool["pool_address"]
        print(f"[{i}/{len(pending)}] {address}")

        try:
            result = cg.download_pool_ohlcv(pool)
        except cg.CoinGeckoNotFoundError as exc:
            record = {
                "pool_address": address,
                "batch": number,
                "status": "unavailable",
                "error": str(exc),
                "attempted_at": datetime.now(timezone.utc).isoformat()
            }
            with output.open("a") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
            print("unavailable: HTTP 404; not retrying")
            time.sleep(delay)
            continue
        except RuntimeError:
            raise
        except Exception as exc:
            result = None
            error = str(exc)
        else:
            error = "API request failed or returned no usable response"

        if result is None:
            record = {
                "pool_address": address,
                "batch": number,
                "status": "request_failed",
                "error": error,
                "attempted_at": datetime.now(timezone.utc).isoformat()
            }
            with errors.open("a") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
            print("Request failed; will retry next run")
        else:
            valid, reason = cg.validate_result(result)
            result["status"] = (
                "no_candles" if valid and not result["candles"]
                else "ok" if valid else "invalid"
            )
            result["validation"] = {"valid": valid, "reason": reason}
            result["batch"] = number

            with output.open("a") as f:
                f.write(json.dumps(result) + "\n")
                f.flush()

            print(f"{result['status']}: {len(result['candles'])} candles")

        time.sleep(delay)


def write_manifest():
    manifest = {
        "provider": "coingecko",
        "network": "solana",
        "interval": "15m",
        "window_hours": 24,
        "source_batches": 24,
        "totals": {"ok": 0, "no_candles": 0, "invalid": 0, "unavailable": 0, "source_metadata_unavailable": 0},
        "batches": {},
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    for n in range(1, 25):
        path = BATCH_OUT / f"batch_{n:02d}.jsonl"
        counts = {"ok": 0, "no_candles": 0, "invalid": 0, "unavailable": 0, "source_metadata_unavailable": 0}

        if path.exists():
            with path.open() as f:
                for line in f:
                    try:
                        status = json.loads(line).get("status")
                        if status in counts:
                            counts[status] += 1
                    except ValueError:
                        continue

        manifest["batches"][f"{n:02d}"] = counts
        for status, count in counts.items():
            manifest["totals"][status] += count

    temp = OUT / "manifest.json.tmp"
    temp.write_text(json.dumps(manifest, indent=2))
    temp.replace(OUT / "manifest.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, choices=range(1, 25))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=2)
    args = parser.parse_args()

    if args.limit < 0 or args.delay < 0:
        parser.error("--limit and --delay cannot be negative")

    OUT.mkdir(parents=True, exist_ok=True)
    BATCH_OUT.mkdir(parents=True, exist_ok=True)

    cg.test_authentication()

    batches = [args.batch] if args.batch else range(1, 25)
    for number in batches:
        collect_batch(number, args.limit, args.delay)
        write_manifest()


if __name__ == "__main__":
    main()
