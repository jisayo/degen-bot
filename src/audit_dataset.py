import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = Path("results/launch_data")
CANDLES = Path("results/historical_data/candles")

def read_jsonl(path):
    rows = []
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    pass
    return rows

def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return None

print("\n========== DEGEN BOT DATA AUDIT ==========")

files = {
    "pools": ROOT / "pools.jsonl",
    "initial_observations": ROOT / "observations.jsonl",
    "tracked_observations": ROOT / "tracked_observations.jsonl",
}

datasets = {}
for name, path in files.items():
    rows = read_jsonl(path)
    datasets[name] = rows
    print(f"\n{name}: {len(rows):,} records | exists={path.exists()}")

pools = datasets["pools"]
initial = datasets["initial_observations"]
tracked = datasets["tracked_observations"]

pool_ids = {
    str(r.get("pool_address") or r.get("address"))
    for r in pools
    if r.get("pool_address") or r.get("address")
}
print(f"\nUnique pool records: {len(pool_ids):,}")

for name, rows in [("Initial", initial), ("Tracked", tracked)]:
    counts = Counter(
        str(r.get("pool_address") or r.get("address"))
        for r in rows
        if r.get("pool_address") or r.get("address")
    )
    values = list(counts.values())
    print(f"\n{name} observation coverage:")
    print(f"  Pools observed: {len(counts):,}")
    print(f"  One observation: {sum(v == 1 for v in values):,}")
    print(f"  2-4 observations: {sum(2 <= v <= 4 for v in values):,}")
    print(f"  5+ observations: {sum(v >= 5 for v in values):,}")
    print(f"  Maximum per pool: {max(values, default=0)}")

if tracked:
    grouped = defaultdict(list)
    for r in tracked:
        key = r.get("pool_address") or r.get("address")
        t = parse_time(r.get("observed_at"))
        if key and t:
            grouped[str(key)].append(t)

    spans = []
    for times in grouped.values():
        times.sort()
        if len(times) >= 2:
            spans.append((times[-1] - times[0]).total_seconds() / 3600)

    if spans:
        spans.sort()
        print("\nTracking duration:")
        print(f"  Pools with 2+ timestamped observations: {len(spans):,}")
        print(f"  Median hours: {spans[len(spans)//2]:.2f}")
        print(f"  Maximum hours: {max(spans):.2f}")

print("\n========== CANDLE DATA ==========")
candle_files = list(CANDLES.glob("*.json")) if CANDLES.exists() else []
print(f"Candle files: {len(candle_files):,}")

valid_files = 0
total_candles = 0
intervals = Counter()
candle_pool_ids = set()

for path in candle_files:
    try:
        data = json.loads(path.read_text())
        candles = data.get("candles", [])
        valid = [
            c for c in candles
            if isinstance(c, list) and len(c) >= 6
            and all(isinstance(x, (int, float)) for x in c[:6])
            and c[0] > 0 and c[1] > 0
            and c[2] > 0 and c[3] > 0
            and c[4] > 0 and c[5] >= 0
        ]
        if valid:
            valid_files += 1
            total_candles += len(valid)
            candle_pool_ids.add(path.stem)
            timestamps = [int(c[0]) for c in valid]
            gaps = [
                timestamps[i] - timestamps[i-1]
                for i in range(1, len(timestamps))
                if timestamps[i] > timestamps[i-1]
            ]
            if gaps:
                intervals[Counter(gaps).most_common(1)[0][0]] += 1
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

print(f"Valid candle files: {valid_files:,}")
print(f"Total valid candles: {total_candles:,}")
print(f"Unique pools with candles: {len(candle_pool_ids):,}")
print(f"Pools with records but no candle file: {len(pool_ids - candle_pool_ids):,}")
print("Most common candle spacing (seconds):")
for seconds, count in intervals.most_common(5):
    print(f"  {seconds}: {count} files")

print("\n========== BACKTEST READINESS ==========")
tracked_ids = {
    str(r.get("pool_address") or r.get("address"))
    for r in tracked
    if r.get("pool_address") or r.get("address")
}
print(f"Pools in launch records: {len(pool_ids):,}")
print(f"Pools with tracked observations: {len(tracked_ids):,}")
print(f"Pools with historical candles: {len(candle_pool_ids):,}")
print(f"Pools with both tracking and candles: {len(tracked_ids & candle_pool_ids):,}")
print("\nAudit complete. No source data was modified.")
