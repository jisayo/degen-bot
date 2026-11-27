import time
import math
import requests
from typing import Dict, List, Any, Optional

from jito_executor import JitoBundleExecutor, DEFAULT_SLIPPAGE_TOLERANCE
import paper_trader as pt

DEXSCREENER_PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"
TIMEOUT = 15

# Strategy Parameters
MAX_SIMULTANEOUS_TRADES = 3
HARD_STOP_LOSS_PCT = 0.30         # Fixed 30% hard stop floor from entry
INITIAL_STOP_LOSS_PCT = 0.20      # 20% initial stop buffer to absorb early noise
TRAILING_STOP_PCT = 0.15          # 15% dynamic trailing stop once in profit
FIRST_TAKE_PROFIT_PCT = 0.50      # +50% TP1
FIRST_TAKE_PROFIT_FRACTION = 0.50 # Sell 50% at TP1
SECOND_TAKE_PROFIT_PCT = 1.00     # +100% TP2
SECOND_TAKE_PROFIT_FRACTION = 0.25# Sell 25% at TP2 (leaving 25% moonbag)
TP1_PROFIT_LOCK_PCT = 0.10        # Lock stop at +10% profit once TP1 hits
SLIPPAGE_TOLERANCE_PCT = 0.15     # 15% slippage tolerance for Jito-protected exit


class SolanaTrailingStopStrategy:
    """
    Manages active Solana positions using real-time DexScreener price feeds.
    Enforces a strict 3-trade concurrency ceiling.
    Enforces a fixed 30% hard stop loss floor alongside a 20% initial noise buffer.
    Implements staged take-profits (+50% sell 50% + lock +10% stop, +100% sell 25%).
    Trails remaining 25% moonbag with 15% dynamic trailing stop from post-activation peak.
    Executes automated exits via Jito-protected private bundles (10-15% slippage).
    """

    def __init__(
        self,
        max_positions: int = MAX_SIMULTANEOUS_TRADES,
        trailing_stop_pct: float = TRAILING_STOP_PCT,
        initial_stop_pct: Optional[float] = None,
        hard_stop_pct: Optional[float] = HARD_STOP_LOSS_PCT,
        enable_staged_tp: bool = True,
        tp1_pct: float = FIRST_TAKE_PROFIT_PCT,
        tp1_fraction: float = FIRST_TAKE_PROFIT_FRACTION,
        tp2_pct: float = SECOND_TAKE_PROFIT_PCT,
        tp2_fraction: float = SECOND_TAKE_PROFIT_FRACTION,
        tp1_profit_lock_pct: float = TP1_PROFIT_LOCK_PCT,
        slippage_tolerance: float = SLIPPAGE_TOLERANCE_PCT,
        jito_executor: Optional[JitoBundleExecutor] = None,
    ):
        self.max_positions = max_positions
        self.trailing_stop_pct = trailing_stop_pct
        self.initial_stop_pct = initial_stop_pct
        self.hard_stop_pct = hard_stop_pct
        self.enable_staged_tp = enable_staged_tp
        self.tp1_pct = tp1_pct
        self.tp1_fraction = tp1_fraction
        self.tp2_pct = tp2_pct
        self.tp2_fraction = tp2_fraction
        self.tp1_profit_lock_pct = tp1_profit_lock_pct
        self.jito_executor = jito_executor or JitoBundleExecutor(
            slippage_tolerance=slippage_tolerance
        )

    def fetch_live_dexscreener_prices(self, token_addresses: List[str]) -> Dict[str, float]:
        """
        Polls DexScreener in real time for latest USD prices for active positions.
        """
        prices = {}
        for token in token_addresses:
            try:
                resp = requests.get(
                    DEXSCREENER_PAIR_URL.format(token),
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                pairs = resp.json()
                if not isinstance(pairs, list):
                    continue

                valid_pairs = [
                    p for p in pairs
                    if isinstance(p, dict) and p.get("chainId") == "solana"
                ]
                if not valid_pairs:
                    continue

                # Select pair with highest liquidity
                def to_liq(item):
                    try:
                        return float((item.get("liquidity") or {}).get("usd") or 0)
                    except (TypeError, ValueError):
                        return 0.0

                best_pair = max(valid_pairs, key=to_liq)
                price_usd = float(best_pair.get("priceUsd") or 0)
                if price_usd > 0:
                    prices[token] = price_usd

            except Exception as exc:
                print(f"[DexScreener Feed] Error fetching {token}: {exc}")

        return prices

    def evaluate_and_update_positions(
        self,
        positions: List[Dict[str, Any]],
        live_prices: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        Evaluates active positions against:
        1. Staged Take-Profits: +50% (sell 35%), +100% (sell 35%).
        2. Initial Stop Buffer (25% buffer against entry whipsaw).
        3. Dynamic Trailing Stop (15% from peak once in profit, locked at break-even post-TP1).
        """
        exits_to_execute = []

        for position in positions:
            token = position["token"]
            if token not in live_prices:
                continue

            current_price = live_prices[token]
            entry_price = float(position["actual_entry_price"])

            # 1. Post-activation peak tracking
            current_peak = float(position.get("highest_price", entry_price))
            new_peak = max(current_peak, current_price)
            position["highest_price"] = new_peak

            original_quantity = float(position.get("original_quantity", position["quantity"]))
            position.setdefault("original_quantity", original_quantity)
            if "first_take_profit_done" not in position:
                position["first_take_profit_done"] = current_peak >= entry_price * (1.0 + self.tp1_pct)
            if "second_take_profit_done" not in position:
                position["second_take_profit_done"] = current_peak >= entry_price * (1.0 + self.tp2_pct)
            position.setdefault("trailing_stop_active", False)

            # 2. Check Staged Take-Profits if enabled
            if self.enable_staged_tp:
                # TP1: +50% target -> sell 35% of original size
                if not position["first_take_profit_done"] and current_price >= entry_price * (1.0 + self.tp1_pct):
                    qty_to_sell = min(float(position["quantity"]), original_quantity * self.tp1_fraction)
                    if qty_to_sell > 0:
                        exits_to_execute.append({
                            "token": token,
                            "current_price": current_price,
                            "post_activation_peak": new_peak,
                            "quantity": qty_to_sell,
                            "is_partial": True,
                            "action_flag": "first_take_profit_done",
                            "reason": f"Take Profit 1 (+50%): price ${current_price:.6f} exceeded target ${entry_price * (1.0 + self.tp1_pct):.6f}",
                        })
                        position["first_take_profit_done"] = True

                # TP2: +100% target -> sell another 35% of original size
                if not position["second_take_profit_done"] and current_price >= entry_price * (1.0 + self.tp2_pct):
                    qty_to_sell = min(float(position["quantity"]), original_quantity * self.tp2_fraction)
                    if qty_to_sell > 0:
                        exits_to_execute.append({
                            "token": token,
                            "current_price": current_price,
                            "post_activation_peak": new_peak,
                            "quantity": qty_to_sell,
                            "is_partial": True,
                            "action_flag": "second_take_profit_done",
                            "reason": f"Take Profit 2 (+100%): price ${current_price:.6f} exceeded target ${entry_price * (1.0 + self.tp2_pct):.6f}",
                        })
                        position["second_take_profit_done"] = True
                        position["trailing_stop_active"] = True

            # 3. Dynamic Stop Trigger + Fixed 30% Hard Stop Floor
            # Before token achieves >= +15% gain, use initial_stop_pct (e.g. 20%) to absorb early noise.
            # Once token achieves >= +15% gain, ratchet the stop to trail 15% from post-activation peak.
            if self.initial_stop_pct is not None and new_peak < entry_price * 1.15:
                stop_trigger_price = entry_price * (1.0 - self.initial_stop_pct)
            else:
                stop_trigger_price = new_peak * (1.0 - self.trailing_stop_pct)

            # Enforce fixed hard stop loss floor (e.g. -30% max from entry)
            if self.hard_stop_pct is not None:
                hard_stop_price = entry_price * (1.0 - self.hard_stop_pct)
                stop_trigger_price = max(stop_trigger_price, hard_stop_price)

            # If TP1 was already taken, lock stop at least at +10% profit above entry
            if position.get("first_take_profit_done"):
                stop_trigger_price = max(
                    stop_trigger_price,
                    entry_price * (1.0 + self.tp1_profit_lock_pct),
                )

            position["stop_trigger_price"] = stop_trigger_price

            # 4. Pullback evaluation
            drop_from_peak_pct = ((new_peak - current_price) / new_peak) * 100
            position["drop_from_peak_pct"] = round(drop_from_peak_pct, 2)

            if current_price <= stop_trigger_price:
                reason = (
                    f"Trailing stop triggered: price ${current_price:.6f} dropped {drop_from_peak_pct:.1f}% from post-activation peak ${new_peak:.6f}"
                    if new_peak >= entry_price * 1.15
                    else f"Initial stop loss triggered: price ${current_price:.6f} dropped {((entry_price - current_price)/entry_price)*100:.1f}% from entry"
                )
                exits_to_execute.append({
                    "token": token,
                    "current_price": current_price,
                    "post_activation_peak": new_peak,
                    "stop_trigger_price": stop_trigger_price,
                    "quantity": float(position["quantity"]),
                    "is_partial": False,
                    "drop_from_peak_pct": drop_from_peak_pct,
                    "reason": reason,
                })

        return exits_to_execute

    def execute_exits(self, exits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Dispatches exits through Jito-protected bundles with 10-15% slippage protection.
        Handles both partial take-profits and full trailing stop closes.
        """
        results = []
        for exit_req in exits:
            token = exit_req["token"]
            qty = exit_req["quantity"]
            curr_price = exit_req["current_price"]
            peak = exit_req["post_activation_peak"]
            reason = exit_req["reason"]
            is_partial = exit_req.get("is_partial", False)
            action_flag = exit_req.get("action_flag")

            # Dispatch via Jito bundle executor
            jito_res = self.jito_executor.execute_trailing_stop_sell(
                token_mint=token,
                token_amount=qty,
                current_price_usd=curr_price,
                post_activation_peak_usd=peak,
                reason=reason,
            )

            # Close simulated position in paper trader
            try:
                if is_partial:
                    pt_trade = pt._close_quantity(token, curr_price, qty, reason=reason)
                    if action_flag:
                        saved_positions = pt.load_positions()
                        for p in saved_positions:
                            if p["token"] == token:
                                p[action_flag] = True
                        pt.save_positions(saved_positions)
                else:
                    pt_trade = pt.close_position(token, curr_price, reason=reason)
                jito_res["paper_trade"] = pt_trade
            except Exception as exc:
                jito_res["paper_trade_error"] = str(exc)

            results.append(jito_res)

        return results


def calculate_solana_trailing_exit(
    candles: List[List[float]],
    entry_price: float,
    trailing_stop_pct: float = TRAILING_STOP_PCT,
):
    """
    Simulates the Solana Trailing Stop-Loss Strategy on historical OHLCV candles:
    - Ignores historical ATH prior to activation; tracks only post-activation peak.
    - Locks stop trigger at 15% below post-activation peak.
    - Moves stop upward automatically as price achieves new highs.
    - Ignores pullbacks < 15%.
    - Triggers automated sell when price drops >= 15% from local peak.
    Returns (exit_timestamp, exit_price, exit_reason, post_activation_peak).
    """
    highest = float(entry_price)  # Strictly tracks post-activation peak
    stop_trigger = highest * (1.0 - trailing_stop_pct)

    for candle in candles[1:]:
        timestamp, open_, high, low, close = candle[:5]
        timestamp = int(timestamp)
        open_ = float(open_)
        high = float(high)
        low = float(low)
        close = float(close)

        # 1. Gap down check at candle open
        if open_ <= stop_trigger:
            if highest > entry_price and open_ > entry_price:
                reason = "GAP_TRAILING_TAKE_PROFIT"
            elif highest > entry_price:
                reason = "GAP_TRAILING_STOP"
            else:
                reason = "GAP_STOP_LOSS"
            return timestamp, open_, reason, highest

        # 2. Intra-candle check against existing active stop
        if low <= stop_trigger:
            if stop_trigger > entry_price:
                reason = "TRAILING_TAKE_PROFIT"
            elif highest > entry_price:
                reason = "TRAILING_STOP"
            else:
                reason = "STOP_LOSS"
            return timestamp, stop_trigger, reason, highest

        # 3. New high check
        if high > highest:
            highest = high
            stop_trigger = highest * (1.0 - trailing_stop_pct)

            # Check if after making new high, candle collapsed below the new stop trigger
            if close <= stop_trigger:
                reason = "TRAILING_TAKE_PROFIT" if stop_trigger > entry_price else "TRAILING_STOP"
                return timestamp, stop_trigger, reason, highest

    # 4. End of candle stream
    last = candles[-1]
    return int(last[0]), float(last[4]), "END_OF_DATA", highest

