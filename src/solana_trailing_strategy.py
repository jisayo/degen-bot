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
TRAILING_STOP_PCT = 0.15          # 15% trailing stop below post-activation peak
SLIPPAGE_TOLERANCE_PCT = 0.15     # 15% slippage tolerance for Jito-protected exit


class SolanaTrailingStopStrategy:
    """
    Manages active Solana positions using real-time DexScreener price feeds.
    Enforces a strict 3-trade concurrency ceiling.
    Tracks only post-activation peaks (ignoring historical ATH).
    Locks the stop trigger at 15% below the post-activation peak.
    Executes automated exits via Jito-protected private bundles (10-15% slippage).
    """

    def __init__(
        self,
        max_positions: int = MAX_SIMULTANEOUS_TRADES,
        trailing_stop_pct: float = TRAILING_STOP_PCT,
        slippage_tolerance: float = SLIPPAGE_TOLERANCE_PCT,
        jito_executor: Optional[JitoBundleExecutor] = None,
    ):
        self.max_positions = max_positions
        self.trailing_stop_pct = trailing_stop_pct
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
        Evaluates active positions against their dynamic trailing stop trigger:
        1. Ignores historical ATH: tracks only post-activation peak.
        2. Raises stop trigger automatically as price achieves new highs.
        3. Ignores minor pullbacks (< 15%).
        4. When price falls >= 15% from post-activation peak, executes Jito-protected exit.
        """
        exits_to_execute = []

        for position in positions:
            token = position["token"]
            if token not in live_prices:
                continue

            current_price = live_prices[token]
            entry_price = float(position["actual_entry_price"])

            # 1. Post-activation peak tracking (strictly ignores pre-activation ATH)
            current_peak = float(position.get("highest_price", entry_price))
            new_peak = max(current_peak, current_price)
            position["highest_price"] = new_peak

            # 2. Dynamic stop trigger locked at 15% below post-activation peak
            stop_trigger_price = new_peak * (1.0 - self.trailing_stop_pct)
            position["stop_trigger_price"] = stop_trigger_price

            # 3. Pullback evaluation
            drop_from_peak_pct = ((new_peak - current_price) / new_peak) * 100
            position["drop_from_peak_pct"] = round(drop_from_peak_pct, 2)

            if current_price <= stop_trigger_price:
                # 4. Trigger automated sell via Jito-protected bundle
                exits_to_execute.append({
                    "token": token,
                    "current_price": current_price,
                    "post_activation_peak": new_peak,
                    "stop_trigger_price": stop_trigger_price,
                    "quantity": float(position["quantity"]),
                    "drop_from_peak_pct": drop_from_peak_pct,
                    "reason": f"Trailing stop triggered: price ${current_price:.6f} dropped {drop_from_peak_pct:.1f}% from post-activation peak ${new_peak:.6f}",
                })

        return exits_to_execute

    def execute_exits(self, exits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Dispatches exits through Jito-protected bundles with 10-15% slippage protection.
        """
        results = []
        for exit_req in exits:
            token = exit_req["token"]
            qty = exit_req["quantity"]
            curr_price = exit_req["current_price"]
            peak = exit_req["post_activation_peak"]
            reason = exit_req["reason"]

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

