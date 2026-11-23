import json
from pathlib import Path
from collections import Counter

base = Path("results/backtest/november_2026/clean_cohort")
data = json.loads(
    (base / "single_entry_results.json").read_text()
)

counts = Counter()
stop_losses = []
large_losses = []

for report in data["pool_results"]:
    trades = report.get("trade_details", [])

    for trade in trades:
        reason = trade["exit_reason"]
        pnl = trade["net_pnl"]
        counts[reason] += 1

        if reason in ("GAP_STOP", "STOP_OR_TRAILING"):
            raw_exit = trade["exit_price"] / 0.99
            raw_return = (
                raw_exit / trade["entry_price"] - 1
            ) * 100

            item = {
                "pool": report["pool"],
                "reason": reason,
                "net_pnl": pnl,
                "raw_return_pct": raw_return,
                "entry": trade["entry_price"],
                "raw_exit": raw_exit,
            }

            stop_losses.append(item)

            if raw_return <= -15:
                large_losses.append(item)

print("========== EXIT COUNTS ==========")
for reason, count in counts.items():
    print(f"{reason}: {count}")

print("\n========== STOP EXIT ANALYSIS ==========")
print("Stop exits:", len(stop_losses))
print("Stop exits worse than -15%:", len(large_losses))

if stop_losses:
    print(
        "Average raw stop-exit return:",
        round(
            sum(x["raw_return_pct"] for x in stop_losses)
            / len(stop_losses), 2
        ),
        "%",
    )

print("\n========== LARGEST STOP LOSSES ==========")
for item in sorted(
    stop_losses, key=lambda x: x["raw_return_pct"]
)[:15]:
    print(
        f"{item['pool']} | {item['reason']} | "
        f"Return: {item['raw_return_pct']:.2f}% | "
        f"Net P/L: ${item['net_pnl']:.4f}"
    )
