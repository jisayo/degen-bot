"""
Predictive Dump Detection System for DEGEN-BOT.

Evaluates 7 indicator categories to identify tokens showing early warning
signs of impending price collapse, liquidity drain, whale distribution,
or developer dumps before entry.
"""

import math
from typing import Dict, Any, List, Optional, Tuple


# Default Risk Weight Allocation (Total: 100 points)
WEIGHTS = {
    "liquidity": 20,
    "whale": 20,
    "developer": 20,
    "pressure": 15,
    "momentum": 10,
    "anomalies": 10,
    "safety": 5,
}

# Risk Classification Tiers
TIER_THRESHOLDS = [
    (24, "LOW"),
    (44, "MODERATE"),
    (64, "HIGH"),
    (79, "VERY_HIGH"),
    (100, "CRITICAL"),
]


def classify_risk_tier(score: float) -> str:
    """Map a 0-100 risk score into standard risk tiers."""
    for upper_bound, tier in TIER_THRESHOLDS:
        if score <= upper_bound:
            return tier
    return "CRITICAL"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely parse finite positive float, returning default if invalid or None."""
    if value is None or isinstance(value, bool):
        return default
    try:
        num = float(value)
        return num if math.isfinite(num) and num >= 0 else default
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_signed_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely parse finite float (positive or negative), returning default if invalid or None."""
    if value is None or isinstance(value, bool):
        return default
    try:
        num = float(value)
        return num if math.isfinite(num) else default
    except (TypeError, ValueError, OverflowError):
        return default


class PredictiveDumpDetector:
    """
    Evaluates multi-dimensional risk signals to predict impending price collapses
    and rug pulls on Solana memecoin pools before execution.
    """

    def __init__(self, weights: Optional[Dict[str, int]] = None):
        self.weights = weights or dict(WEIGHTS)

    def evaluate_liquidity_risk(
        self,
        token_data: Dict[str, Any],
        rugcheck_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        1. Liquidity Behaviour (Max: 20 pts)
        - Detect sudden liquidity withdrawals
        - Liquidity changes over time
        - Unstable or artificially inflated liquidity (Liquidity/MC ratio)
        - Liquidity concentration & lock status
        - Exit capacity (can available liquidity support our exit?)
        """
        max_pts = self.weights["liquidity"]
        score = 0.0
        reasons = []
        details = {}

        liquidity = _safe_float(token_data.get("liquidity_usd"))
        market_cap = _safe_float(token_data.get("market_cap_usd"))
        trade_size = _safe_float(token_data.get("intended_trade_size_usd"), 4.17)

        details["liquidity_usd"] = liquidity
        details["market_cap_usd"] = market_cap

        # Zero or missing liquidity is critical
        if liquidity is None or liquidity <= 0:
            reasons.append("Zero or unverified pool liquidity")
            return float(max_pts), reasons, details

        # Check Liquidity-to-Market-Cap Health Ratio (Solana benchmark: >= 15%)
        if market_cap and market_cap > 0:
            ratio = liquidity / market_cap
            details["liquidity_mc_ratio"] = round(ratio, 4)
            if ratio < 0.08:
                score += 8.0
                reasons.append(f"Severely thin liquidity ratio ({ratio*100:.1f}% < 8% of MC)")
            elif ratio < 0.15:
                score += 5.0
                reasons.append(f"Fragile liquidity ratio ({ratio*100:.1f}% < 15% of MC)")

        # Liquidity Depth vs Exit Capacity (Can pool absorb our exit without >2% impact?)
        if trade_size and trade_size > 0:
            pool_impact_pct = (trade_size / liquidity) * 100
            details["exit_impact_pct"] = round(pool_impact_pct, 4)
            if pool_impact_pct > 2.0:
                score += 5.0
                reasons.append(f"Insufficient pool depth for clean exit (size is {pool_impact_pct:.1f}% of pool)")

        # Liquidity concentration & unlock status from RugCheck
        if rugcheck_data:
            lp_locked_pct = _safe_float(rugcheck_data.get("lpLockedPct"))
            details["lp_locked_pct"] = lp_locked_pct
            if lp_locked_pct is not None:
                if lp_locked_pct < 50.0:
                    score += 7.0
                    reasons.append(f"High liquidity drain risk: only {lp_locked_pct:.1f}% LP locked/burned")
                elif lp_locked_pct < 80.0:
                    score += 4.0
                    reasons.append(f"Sub-optimal LP lock: {lp_locked_pct:.1f}% locked")

            # Check risks list (handles both string names and dict objects)
            risks = rugcheck_data.get("risks", [])
            risk_names = [r.get("name") if isinstance(r, dict) else str(r) for r in risks]
            if any("Low Liquidity" in r for r in risk_names):
                score += 5.0
                reasons.append("RugCheck flags low liquidity depth")
            if any("Unlocked" in r or "LP Unlocked" in r for r in risk_names):
                score += 7.0
                reasons.append("RugCheck flags large amount of unlocked liquidity")
            if any("Low amount of LP Providers" in r for r in risk_names):
                score += 3.0
                reasons.append("RugCheck flags low number of LP providers (fragile pool)")

        # Cap at component max
        return min(score, float(max_pts)), reasons, details

    def evaluate_whale_distribution_risk(
        self,
        token_data: Dict[str, Any],
        rugcheck_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        2. Whale Activity & Supply Concentration (Max: 20 pts)
        - Wallets holding unusually large token supplies
        - Large sells vs small buys (distribution into retail)
        - Coordinated concentration
        """
        max_pts = self.weights["whale"]
        score = 0.0
        reasons = []
        details = {}

        # 1. Order flow distribution imbalance (Large sells vs small buys)
        vol_h1 = _safe_float(token_data.get("volume_1h"))
        buys_h1 = _safe_float(token_data.get("buys_1h"))
        sells_h1 = _safe_float(token_data.get("sells_1h"))
        buy_vol_h1 = _safe_float(token_data.get("buy_volume_1h"))
        sell_vol_h1 = _safe_float(token_data.get("sell_volume_1h"))

        if buys_h1 and sells_h1 and buys_h1 > 0 and sells_h1 > 0:
            if buy_vol_h1 is not None and sell_vol_h1 is not None:
                avg_buy_usd = buy_vol_h1 / buys_h1
                avg_sell_usd = sell_vol_h1 / sells_h1
            elif vol_h1 is not None and vol_h1 > 0:
                # Estimate: if sells are few but volume is significant, estimate sell impact
                # When sell volume is not split by API, check transaction asymmetry
                avg_buy_usd = vol_h1 / (buys_h1 + sells_h1)
                avg_sell_usd = (vol_h1 / (buys_h1 + sells_h1)) * (buys_h1 / max(sells_h1, 1.0))
            else:
                avg_buy_usd = 0.0
                avg_sell_usd = 0.0

            details["avg_buy_size_usd"] = round(avg_buy_usd, 2)
            details["avg_sell_size_usd"] = round(avg_sell_usd, 2)

            # Whales dumping large clips into small retail buys
            if avg_sell_usd > 2.5 * avg_buy_usd:
                score += 8.0
                reasons.append(
                    f"Whale distribution pattern: average sell (${avg_sell_usd:.0f}) is >2.5x average buy (${avg_buy_usd:.0f})"
                )
            elif avg_sell_usd > 1.4 * avg_buy_usd:
                score += 4.0
                reasons.append(
                    f"Bearish order asymmetry: average sell (${avg_sell_usd:.0f}) exceeds average buy (${avg_buy_usd:.0f})"
                )

        # 2. Wallet Supply Concentration (RugCheck topHolders / risks)
        if rugcheck_data:
            top_holders = rugcheck_data.get("topHolders", [])
            details["top_holders_analyzed"] = len(top_holders)

            if isinstance(top_holders, list) and top_holders:
                # Exclude standard Raydium / Pump.fun AMM pool addresses if marked or identifiable
                non_pool_holders = [
                    h for h in top_holders
                    if isinstance(h, dict) and not h.get("isPool", False)
                ]

                # Max single non-pool wallet holding
                percentages = [_safe_float(h.get("pct"), 0.0) or 0.0 for h in non_pool_holders]
                top1_pct = max(percentages) if percentages else 0.0
                top10_sum = sum(sorted(percentages, reverse=True)[:10])

                details["top1_holder_pct"] = round(top1_pct, 2)
                details["top10_holder_pct"] = round(top10_sum, 2)

                if top1_pct > 15.0:
                    score += 10.0
                    reasons.append(f"Dangerous whale concentration: single wallet controls {top1_pct:.1f}% of supply")
                elif top1_pct > 8.0:
                    score += 6.0
                    reasons.append(f"High single whale concentration: top holder owns {top1_pct:.1f}% of supply")

                if top10_sum > 40.0:
                    score += 7.0
                    reasons.append(f"Extreme top-10 concentration: {top10_sum:.1f}% of supply controlled by top 10")
                elif top10_sum > 25.0:
                    score += 4.0
                    reasons.append(f"Elevated top-10 concentration: {top10_sum:.1f}% held by top 10")

            # Check for RugCheck concentration warnings
            risks = rugcheck_data.get("risks", [])
            risk_names = [r.get("name") if isinstance(r, dict) else str(r) for r in risks]
            if any("Single holder" in r for r in risk_names):
                score += 9.0
                reasons.append("RugCheck flags single holder outsized ownership")
            if any("Top 10" in r or "High ownership" in r or "holder concentration" in r for r in risk_names):
                score += 8.0
                reasons.append("RugCheck flags concentrated wallet ownership")
            if any("High holder correlation" in r for r in risk_names):
                score += 6.0
                reasons.append("RugCheck flags suspected Sybil cluster / correlated wallets")

        return min(score, float(max_pts)), reasons, details

    def evaluate_developer_risk(
        self,
        token_data: Dict[str, Any],
        rugcheck_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        3. Developer and Insider Activity (Max: 20 pts)
        - Deployer wallet holdings
        - Developer token sales
        - Flag tokens with concentrated insider ownership
        """
        max_pts = self.weights["developer"]
        score = 0.0
        reasons = []
        details = {}

        if not rugcheck_data:
            # Missing rugcheck data cannot be assumed safe
            reasons.append("Developer and insider audit unavailable (unverified)")
            return 8.0, reasons, details

        creator = rugcheck_data.get("creator")
        creator_balance_pct = _safe_float(rugcheck_data.get("creatorBalancePct"))
        insider_pct = _safe_float(rugcheck_data.get("insiderHoldingPct"))

        details["creator_address"] = creator
        details["creator_balance_pct"] = creator_balance_pct
        details["insider_holding_pct"] = insider_pct

        risks = rugcheck_data.get("risks", [])
        risk_names = [r.get("name") if isinstance(r, dict) else str(r) for r in risks]

        # 1. Did creator already sell or dump or have history of rugging?
        if any("Creator sold" in r or "Dev sold" in r for r in risk_names):
            score += 12.0
            reasons.append("Creator has actively sold tokens into market")
        if any("history of rugged" in r or "rugged tokens" in r for r in risk_names):
            score += 14.0
            reasons.append("Creator has verified on-chain history of rugged tokens")

        # 2. Does creator still hold an outsized amount?
        if creator_balance_pct is not None:
            if creator_balance_pct > 5.0:
                score += 10.0
                reasons.append(f"Deployer holds dangerous {creator_balance_pct:.1f}% token supply")
            elif creator_balance_pct > 2.0:
                score += 5.0
                reasons.append(f"Deployer retains {creator_balance_pct:.1f}% supply")

        # 3. Insider holding percentage
        if insider_pct is not None:
            if insider_pct > 20.0:
                score += 8.0
                reasons.append(f"Insiders control {insider_pct:.1f}% of supply")
            elif insider_pct > 10.0:
                score += 4.0
                reasons.append(f"Elevated insider ownership ({insider_pct:.1f}%)")

        if any("High insider" in r or "Single holder" in r for r in risk_names):
            score += 5.0
            reasons.append("RugCheck flags suspected insider clusters")

        return min(score, float(max_pts)), reasons, details

    def evaluate_buy_sell_pressure_risk(
        self,
        token_data: Dict[str, Any],
        candles: Optional[List[List[float]]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        4. Buy/Sell Pressure & Flow Dynamics (Max: 15 pts)
        - Buy volume against sell volume
        - Changes in buy/sell transaction ratios
        - Increasing sell pressure
        """
        max_pts = self.weights["pressure"]
        score = 0.0
        reasons = []
        details = {}

        buys_h1 = _safe_float(token_data.get("buys_1h"), 0.0) or 0.0
        sells_h1 = _safe_float(token_data.get("sells_1h"), 0.0) or 0.0
        total_tx = buys_h1 + sells_h1

        if total_tx > 0:
            buy_ratio = buys_h1 / total_tx
            details["buy_ratio_1h"] = round(buy_ratio, 4)

            # Heavy sell pressure
            if buy_ratio < 0.45:
                score += 10.0
                reasons.append(f"Sellers dominate order flow: only {buy_ratio*100:.1f}% buys (< 45%)")
            elif buy_ratio < 0.55:
                score += 6.0
                reasons.append(f"Weak buying momentum: {buy_ratio*100:.1f}% buys (< 55%)")

        # If 5-minute activity is available, compare 5m trend to 1h trend (Momentum Decay)
        buys_m5 = _safe_float(token_data.get("buys_5m"))
        sells_m5 = _safe_float(token_data.get("sells_5m"))

        if buys_m5 is not None and sells_m5 is not None and (buys_m5 + sells_m5) > 5:
            ratio_5m = buys_m5 / (buys_m5 + sells_m5)
            details["buy_ratio_5m"] = round(ratio_5m, 4)
            if total_tx > 0:
                buy_ratio_1h = buys_h1 / total_tx
                # If 5m ratio is substantially lower than 1h ratio, buying has stalled
                if ratio_5m < buy_ratio_1h - 0.15:
                    score += 5.0
                    reasons.append(
                        f"Rapid buy decay: 5m buy ratio ({ratio_5m*100:.1f}%) collapsed below 1h baseline ({buy_ratio_1h*100:.1f}%)"
                    )

        # Inspect recent candles for consecutive red distribution bars
        if candles and len(candles) >= 3:
            recent = candles[-3:]
            red_bars = sum(1 for c in recent if c[4] < c[1])  # close < open
            details["recent_red_bars_count"] = red_bars
            if red_bars == 3:
                score += 4.0
                reasons.append("3 consecutive bearish candle closes preceding entry")

        return min(score, float(max_pts)), reasons, details

    def evaluate_price_momentum_risk(
        self,
        token_data: Dict[str, Any],
        candles: Optional[List[List[float]]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        5. Price Action and Momentum Anomalies (Max: 10 pts)
        - Price exhaustion (long upper wicks indicating overhead rejection)
        - Lower highs and weakening structure
        - Divergence between price rises and declining volume
        """
        max_pts = self.weights["momentum"]
        score = 0.0
        reasons = []
        details = {}

        # Check DexScreener priceChange if provided in token_data
        price_change_1h = _safe_signed_float(token_data.get("price_change_1h"))
        price_change_m5 = _safe_signed_float(token_data.get("price_change_m5"))
        if price_change_1h is not None:
            details["price_change_1h"] = round(price_change_1h, 2)
            if price_change_1h < -15.0:
                score += 6.0
                reasons.append(f"Severe 1-hour price decline ({price_change_1h:+.1f}%)")
            elif price_change_1h < 0.0:
                score += 3.0
                reasons.append(f"Negative 1-hour price momentum ({price_change_1h:+.1f}%)")

        if price_change_m5 is not None:
            details["price_change_m5"] = round(price_change_m5, 2)
            if price_change_m5 < -5.0:
                score += 4.0
                reasons.append(f"Sharp 5-minute price decline ({price_change_m5:+.1f}%)")

        if not candles or len(candles) < 2:
            return min(score, float(max_pts)), reasons, details

        # Inspect latest candle for Upper Wick Rejection (Shooting star / supply overhang)
        latest = candles[-1]
        c_open, c_high, c_low, c_close, c_vol = latest[1], latest[2], latest[3], latest[4], latest[5]
        candle_range = c_high - c_low

        if candle_range > 0:
            upper_wick = c_high - max(c_open, c_close)
            upper_wick_ratio = upper_wick / candle_range
            details["upper_wick_ratio"] = round(upper_wick_ratio, 4)

            # Heavy rejection at highs
            if upper_wick_ratio > 0.50:
                score += 5.0
                reasons.append(f"Heavy overhead rejection: upper wick accounts for {upper_wick_ratio*100:.1f}% of candle range")
            elif upper_wick_ratio > 0.35:
                score += 3.0
                reasons.append(f"Notable price rejection at local highs ({upper_wick_ratio*100:.1f}% wick)")

        # Inspect for Volume-Price Bearish Divergence (Price pushed higher, but volume died)
        if len(candles) >= 2:
            prev_candle = candles[-2]
            if c_close > prev_candle[4] and c_vol < prev_candle[5] * 0.5:
                score += 4.0
                reasons.append("Bearish volume divergence: price rose while volume collapsed > 50%")

            # Lower high check
            if c_high < prev_candle[2] and c_close < prev_candle[4]:
                score += 3.0
                reasons.append("Weakening price structure: lower high and lower close confirmed")

        return min(score, float(max_pts)), reasons, details

    def evaluate_trading_anomalies_risk(
        self,
        token_data: Dict[str, Any],
        candles: Optional[List[List[float]]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        6. Trading Activity & Wash Trading Anomalies (Max: 10 pts)
        - Volume/Liquidity ratio > 10.0 (wash trading or pump frenzy)
        - Micro-transaction spam (high transactions, negligible volume)
        """
        max_pts = self.weights["anomalies"]
        score = 0.0
        reasons = []
        details = {}

        liquidity = _safe_float(token_data.get("liquidity_usd"))
        volume_1h = _safe_float(token_data.get("volume_1h"))
        buys_1h = _safe_float(token_data.get("buys_1h"), 0.0) or 0.0
        sells_1h = _safe_float(token_data.get("sells_1h"), 0.0) or 0.0
        total_tx = buys_1h + sells_1h

        if liquidity and volume_1h and liquidity > 0:
            vol_liq_ratio = volume_1h / liquidity
            details["volume_liquidity_ratio"] = round(vol_liq_ratio, 2)

            if vol_liq_ratio > 15.0:
                score += 6.0
                reasons.append(f"Extreme volume/liquidity ratio ({vol_liq_ratio:.1f}x > 15x): suspected circular wash trading")
            elif vol_liq_ratio > 10.0:
                score += 4.0
                reasons.append(f"High volume/liquidity ratio ({vol_liq_ratio:.1f}x): elevated churn risk")

        if total_tx > 50 and volume_1h is not None:
            avg_trade = volume_1h / total_tx
            details["avg_trade_usd"] = round(avg_trade, 2)
            if avg_trade < 5.0:
                score += 5.0
                reasons.append(f"Micro-bot transaction spam detected: average trade size is only ${avg_trade:.2f}")

        return min(score, float(max_pts)), reasons, details

    def evaluate_token_safety_risk(
        self,
        rugcheck_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        7. Token Safety & Contract Authorities (Max: 5 pts)
        - Mint authority not revoked
        - Freeze authority not revoked
        - Rugged status
        """
        max_pts = self.weights["safety"]
        score = 0.0
        reasons = []
        details = {}

        if not rugcheck_data:
            reasons.append("Token contract verification unavailable")
            return 3.0, reasons, details

        mint_auth = rugcheck_data.get("mint_authority")
        freeze_auth = rugcheck_data.get("freeze_authority")
        is_rugged = rugcheck_data.get("rugged", False)
        risks = rugcheck_data.get("risks", [])
        risk_names = [r.get("name") if isinstance(r, dict) else str(r) for r in risks]

        details["mint_authority"] = mint_auth
        details["freeze_authority"] = freeze_auth
        details["is_rugged"] = is_rugged

        if is_rugged:
            score += 5.0
            reasons.append("Token already confirmed rugged by RugCheck")

        if (mint_auth is not None and str(mint_auth).strip() != "") or any("Mint Authority" in r for r in risk_names):
            score += 3.0
            reasons.append("Active mint authority: creator can inflate supply")

        if (freeze_auth is not None and str(freeze_auth).strip() != "") or any("Freeze Authority" in r for r in risk_names):
            score += 3.0
            reasons.append("Active freeze authority: accounts can be frozen (honeypot risk)")

        return min(score, float(max_pts)), reasons, details

    def evaluate(
        self,
        token_data: Dict[str, Any],
        rugcheck_data: Optional[Dict[str, Any]] = None,
        candles: Optional[List[List[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete multi-category predictive dump risk assessment.
        Returns composite 0-100 score, component breakdown, warning signals,
        risk tier, and predictive time window horizon estimates.
        """
        liq_score, liq_reasons, liq_det = self.evaluate_liquidity_risk(token_data, rugcheck_data)
        whale_score, whale_reasons, whale_det = self.evaluate_whale_distribution_risk(token_data, rugcheck_data)
        dev_score, dev_reasons, dev_det = self.evaluate_developer_risk(token_data, rugcheck_data)
        pres_score, pres_reasons, pres_det = self.evaluate_buy_sell_pressure_risk(token_data, candles)
        mom_score, mom_reasons, mom_det = self.evaluate_price_momentum_risk(token_data, candles)
        anom_score, anom_reasons, anom_det = self.evaluate_trading_anomalies_risk(token_data, candles)
        safe_score, safe_reasons, safe_det = self.evaluate_token_safety_risk(rugcheck_data)

        total_score = round(
            liq_score + whale_score + dev_score + pres_score + mom_score + anom_score + safe_score,
            2
        )
        total_score = min(max(total_score, 0.0), 100.0)
        risk_tier = classify_risk_tier(total_score)

        all_reasons = (
            liq_reasons + whale_reasons + dev_reasons +
            pres_reasons + mom_reasons + anom_reasons + safe_reasons
        )

        # Confidence level based on data completeness
        has_rugcheck = rugcheck_data is not None and isinstance(rugcheck_data, dict)
        has_candles = candles is not None and len(candles) >= 2
        if has_rugcheck and has_candles:
            confidence = "HIGH"
        elif has_rugcheck or has_candles:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Predictive dump probability hypotheses across time horizons
        # Scaled non-linearly based on composite risk
        dump_prob_5m = round(min(total_score * 0.70, 95.0), 1)
        dump_prob_15m = round(min(total_score * 0.85, 98.0), 1)
        dump_prob_30m = round(min(total_score * 0.95, 99.0), 1)
        dump_prob_60m = round(min(total_score * 1.00, 99.0), 1)

        return {
            "token": token_data.get("address", token_data.get("token", "UNKNOWN")),
            "risk_score": total_score,
            "risk_tier": risk_tier,
            "confidence": confidence,
            "warning_signals": all_reasons,
            "warning_count": len(all_reasons),
            "breakdown": {
                "liquidity_risk": round(liq_score, 2),
                "whale_distribution_risk": round(whale_score, 2),
                "developer_activity_risk": round(dev_score, 2),
                "buy_sell_pressure_risk": round(pres_score, 2),
                "price_momentum_risk": round(mom_score, 2),
                "trading_anomalies_risk": round(anom_score, 2),
                "token_safety_risk": round(safe_score, 2),
            },
            "predictive_horizons": {
                "dump_risk_5m_pct": dump_prob_5m,
                "dump_risk_15m_pct": dump_prob_15m,
                "dump_risk_30m_pct": dump_prob_30m,
                "dump_risk_60m_pct": dump_prob_60m,
            },
            "diagnostics": {
                "liquidity": liq_det,
                "whale": whale_det,
                "developer": dev_det,
                "pressure": pres_det,
                "momentum": mom_det,
                "anomalies": anom_det,
                "safety": safe_det,
            },
        }

    def should_reject(
        self,
        evaluation: Dict[str, Any],
        rejection_threshold: float = 45.0,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determines whether entry should be rejected based on validated risk threshold.
        Default threshold: 45.0 (High Risk tier and above).
        """
        score = evaluation.get("risk_score", 0.0)
        tier = evaluation.get("risk_tier", "LOW")
        warnings = evaluation.get("warning_signals", [])

        if score >= rejection_threshold:
            primary_reason = warnings[0] if warnings else f"Risk score {score:.1f} >= {rejection_threshold}"
            return True, f"Dump detector rejected ({tier} risk: {score:.1f}/100) — {primary_reason}"

        return False, None
