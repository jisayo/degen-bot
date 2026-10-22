import json
from datetime import datetime, timezone
from pathlib import Path

report = Path("results/backtest/backtest_7d.json")
data = json.loads(report.read_text())[0]

print(
    f"{'#':>2} {'ENTRY UTC':17} {'EXIT UTC':17} "
    f"{'HOLD':>6} {'ENTRY $':>12} {'EXIT $':>12} "
    f"{'P/L $':>9} {'EXIT REASON'}"
)
print("-" * 105)

for i, trade in enumerate(data["trade_details"], 1):
    entry = datetime.fromtimestamp(
        trade["entry_time"], timezone.utc
    ).strftime("%m-%d %H:%M")

    exit_time = datetime.fromtimestamp(
        trade["exit_time"], timezone.utc
    ).strftime("%m-%d %H:%M")

    hold = (trade["exit_time"] - trade["entry_time"]) // 60

    print(
        f"{i:2} {entry:17} {exit_time:17} "
        f"{hold:5}m "
        f"{trade['entry_price']:12.8f} "
        f"{trade['exit_price']:12.8f} "
        f"{trade['net_pnl']:9.4f} "
        f"{trade['exit_reason']}"
    )

print("\nSUMMARY")
for key in (
    "trades", "wins", "losses", "win_rate_pct",
    "starting_balance", "final_balance", "net_pnl",
    "max_drawdown_pct",
):
    print(f"{key}: {data.get(key)}")cd ~/degen-bot && code src/test_strategy_settings.py