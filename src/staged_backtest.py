"""Paper-only historical backtest with staged profit taking."""

from backtest_engine import (
    STARTING_BALANCE,
    TRADE_SIZE_PCT,
    FEE_RATE,
    SLIPPAGE_RATE,
    STOP_LOSS_PCT,
    TRAILING_STOP_PCT,
    load_candles,
)


FIRST_TARGET_PCT = 0.50
FIRST_SELL_FRACTION = 0.50
SECOND_TARGET_PCT = 1.00
SECOND_SELL_FRACTION = 0.25


def calculate_staged_exits(candles, entry_index, entry_price):
    """Return partial exits as (time, price, fraction, reason).

    Fractions are of the original token quantity. Existing stops are
    checked before targets. A newly activated trailing stop applies
    from the following candle because OHLC data cannot establish
    intrabar ordering.
    """
    hard_stop = entry_price * (1 - STOP_LOSS_PCT)
    first_target = entry_price * (1 + FIRST_TARGET_PCT)
    second_target = entry_price * (1 + SECOND_TARGET_PCT)

    remaining = 1.0
    first_done = False
    second_done = False
    trailing_active = False
    highest = entry_price
    exits = []

    for candle in candles[entry_index + 1:]:
        timestamp, open_, high, low, close, volume = candle

        active_stop = hard_stop
        if trailing_active:
            active_stop = max(
                active_stop,
                highest * (1 - TRAILING_STOP_PCT),
            )

        # Stop first if a candle touches both a stop and a target.
        if open_ <= active_stop:
            exits.append((timestamp, open_, remaining, "GAP_STOP"))
            remaining = 0.0
            break

        if low <= active_stop:
            reason = (
                "STOP_OR_TRAILING"
                if trailing_active and active_stop > hard_stop
                else "STOP_LOSS"
            )
            exits.append((timestamp, active_stop, remaining, reason))
            remaining = 0.0
            break

        # Targets execute at their target prices, not at a more
        # optimistic candle high.
        if not first_done and high >= first_target:
            fraction = min(FIRST_SELL_FRACTION, remaining)
            exits.append((
                timestamp, first_target, fraction, "TAKE_PROFIT_1"
            ))
            remaining -= fraction
            first_done = True

        if not second_done and high >= second_target:
            fraction = min(SECOND_SELL_FRACTION, remaining)
            exits.append((
                timestamp, second_target, fraction, "TAKE_PROFIT_2"
            ))
            remaining -= fraction
            second_done = True
            trailing_active = True

        highest = max(highest, high)

        if remaining <= 1e-12:
            remaining = 0.0
            break

    if remaining > 1e-12:
        last = candles[-1]
        exits.append((last[0], last[4], remaining, "END_OF_DATA"))

    return exits


def run_staged_backtest(path):
    candles = load_candles(path)

    if len(candles) < 2:
        return {"pool": path.stem, "error": "Not enough valid candles"}

    balance = STARTING_BALANCE
    trades = []
    index = 0

    while index < len(candles) - 1 and balance > 0:
        entry_candle = candles[index]
        reference_entry = entry_candle[4]
        allocation = balance * TRADE_SIZE_PCT

        if allocation <= 0:
            break

        entry_price = reference_entry * (1 + SLIPPAGE_RATE)
        quantity = allocation / entry_price
        entry_fee = allocation * FEE_RATE

        exits = calculate_staged_exits(candles, index, entry_price)
        total_gross = 0.0
        total_exit_fee = 0.0
        exit_time = entry_candle[0]
        exit_reasons = []

        for timestamp, raw_price, fraction, reason in exits:
            exit_price = raw_price * (1 - SLIPPAGE_RATE)
            proceeds = quantity * fraction * exit_price
            fee = proceeds * FEE_RATE

            total_gross += proceeds
            total_exit_fee += fee
            exit_time = timestamp
            exit_reasons.append(reason)

        net_pnl = total_gross - allocation - entry_fee - total_exit_fee
        balance += net_pnl

        trades.append({
            "entry_time": entry_candle[0],
            "exit_time": exit_time,
            "entry_price": entry_price,
            "allocation": allocation,
            "entry_fee": entry_fee,
            "exit_fee": total_exit_fee,
            "gross_proceeds": total_gross,
            "net_pnl": net_pnl,
            "balance": balance,
            "exit_reason": "+".join(exit_reasons),
            "partial_exits": [
                {
                    "timestamp": timestamp,
                    "price": price * (1 - SLIPPAGE_RATE),
                    "original_quantity_fraction": fraction,
                    "reason": reason,
                }
                for timestamp, price, fraction, reason in exits
            ],
        })

        exit_time_index = next(
            (
                i for i, candle in enumerate(candles)
                if candle[0] >= exit_time
            ),
            len(candles) - 1,
        )
        index = exit_time_index + 1

    wins = sum(trade["net_pnl"] > 0 for trade in trades)

    return {
        "pool": path.stem,
        "candles": len(candles),
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": round(
            wins / len(trades) * 100, 2
        ) if trades else 0,
        "starting_balance": STARTING_BALANCE,
        "final_balance": round(balance, 4),
        "net_pnl": round(balance - STARTING_BALANCE, 4),
        "trade_details": trades,
    }
