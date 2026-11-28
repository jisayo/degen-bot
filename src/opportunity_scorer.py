import math

MIN_OPPORTUNITY_SCORE = 50
MIN_LIQUIDITY_USD = 20000.0
MIN_MARKET_CAP_USD = 75000.0
MIN_LIQUIDITY_MC_RATIO = 0.15
MIN_LIQUIDITY_MC_RATIO_MIDCAP = 0.08  # Adaptive floor for >= $200k MC tokens
MIDCAP_THRESHOLD_USD = 200000.0
MIN_TRADES = 50
MIN_VOLUME_1H_USD = 25000.0
MAX_VOLUME_LIQUIDITY_RATIO = 10.0
MAX_VOLUME_LIQUIDITY_RATIO_DEEP = 20.0  # Allowed turnover for >= $20k liquidity pools
MIN_BUY_RATIO = 0.55  # Minimum 55% buy-to-sell ratio
MAX_BUY_RATIO = 0.90  # Reject > 90% buy-only imbalance (honeypot/spoof guard)
MIN_BUY_RATIO_WITH_5M_MOMENTUM = 0.55
MULTI_SOURCE_BONUS = 5  # Score bonus when discovered on >= 2 independent feeds

# --- Momentum / chart-based entry gates ---
# Applied on top of the structural filters (liquidity, risk, etc.)
# All use data DexScreener already returns — no extra API calls.

# Reject if the last 5-minute candle is red (price_change_m5 < 0).
# A red 5-min bar means we'd be entering an active dump.
REQUIRE_GREEN_5M = True

# Reject if net 5-minute order flow is sell-dominated.
# Requires buys_5m > sells_5m at time of entry.
REQUIRE_5M_BUY_DOMINANCE = True

# Minimum number of 5-minute buys to confirm active accumulation
# (guards against tokens that look bullish but are actually dead).
MIN_5M_BUYS = 3

# Minimum 5-minute USD volume to ensure active dollar flow right now.
MIN_VOLUME_5M_USD = 500.0

# Reject if price already pumped more than this % in the last hour.
# Entering after a 400%+ 1h move almost always means buying the top.
MAX_PUMP_1H_PCT = 400.0

# Anti-FOMO 5-minute spike cap: avoid buying after a vertical +150% 5m candle.
MAX_PUMP_5M_PCT = 150.0

# Volume acceleration: buys+sells in the last 5 min should represent
# at least this fraction of what we'd expect from a steady h1 pace.
# Computed as: (buys_5m + sells_5m) / ((buys_1h + sells_1h) / 12)
# A value >= 0.5 means activity is at least half the hourly average pace.
# Keeps out tokens whose 5-min flow is drying up after the initial pump.
MIN_5M_ACCELERATION = 0.5


def _to_number(value):
    """Return a valid non-negative finite number, or None."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number) or number < 0:
        return None

    return number


def score_opportunity(token: dict) -> dict:
    """Score a token and determine whether it qualifies for paper trading."""
    if not isinstance(token, dict):
        return {
            "opportunity_score": 0,
            "eligible_for_paper_trading": False,
            "reasons": ["Invalid token data"],
        }

    fields = (
        "liquidity_usd",
        "market_cap_usd",
        "volume_1h",
        "buys_1h",
        "sells_1h",
    )

    values = {
        field: _to_number(token.get(field))
        for field in fields
    }

    invalid_fields = [
        field for field, value in values.items()
        if value is None
    ]

    if invalid_fields:
        return {
            "opportunity_score": 0,
            "eligible_for_paper_trading": False,
            "reasons": [
                f"Invalid or missing market data: {', '.join(invalid_fields)}"
            ],
        }

    liquidity = values["liquidity_usd"]
    market_cap = values["market_cap_usd"]
    volume = values["volume_1h"]
    buys = values["buys_1h"]
    sells = values["sells_1h"]

    # Trade counts must be whole numbers.
    if not buys.is_integer() or not sells.is_integer():
        return {
            "opportunity_score": 0,
            "eligible_for_paper_trading": False,
            "reasons": ["Invalid trade counts"],
        }

    buys = int(buys)
    sells = int(sells)

    score = 0
    reasons = []

    # Liquidity
    if liquidity >= 20_000:
        score += 30
        reasons.append("Strong liquidity")
    elif liquidity >= 5_000:
        score += 20
        reasons.append("Moderate liquidity")
    elif liquidity > 0:
        score += 5
        reasons.append("Low liquidity")

    # Adaptive volume/liquidity ceiling: deeper ($20k+) pools tolerate up to 20x
    # hourly turnover; shallow pools (<$20k) stay strictly capped at 10x.
    max_vol_liq_ratio = (
        MAX_VOLUME_LIQUIDITY_RATIO_DEEP
        if liquidity >= MIN_LIQUIDITY_USD
        else MAX_VOLUME_LIQUIDITY_RATIO
    )

    # Volume relative to liquidity
    if liquidity > 0:
        ratio = volume / liquidity

        if 1 <= ratio <= max_vol_liq_ratio:
            score += 20
            reasons.append("Healthy volume/liquidity ratio")
        elif ratio > max_vol_liq_ratio:
            reasons.append(
                "Very high volume; investigate wash trading"
            )

    # Extreme reported volume relative to liquidity can indicate wash
    # trading or unreliable data. Hard-block it rather than merely warning.
    volume_liquidity_ratio = volume / liquidity if liquidity > 0 else None
    extreme_volume_ratio = (
        volume_liquidity_ratio is not None
        and volume_liquidity_ratio > max_vol_liq_ratio
    )
    if extreme_volume_ratio:
        reasons.append(
            "Volume/liquidity ratio exceeds "
            f"{max_vol_liq_ratio:g}x; blocked for review"
        )

    # Trading activity
    trades = buys + sells

    if trades >= 200:
        score += 20
        reasons.append("Strong trading activity")
    elif trades >= 50:
        score += 10
        reasons.append("Moderate trading activity")

    # Buy/sell balance
    buy_ratio = None
    if trades > 0:
        buy_ratio = buys / trades

        if 0.55 <= buy_ratio <= 0.75:
            score += 15
            reasons.append("Positive buying pressure (55–75% buys)")
        elif buy_ratio > MAX_BUY_RATIO:
            reasons.append(
                f"Extreme buy imbalance ({buy_ratio*100:.1f}% > {MAX_BUY_RATIO*100:.0f}%); blocked for honeypot/spoof risk"
            )

    # Multi-source confirmation bonus
    source_count = int(token.get("source_count") or 1)
    if source_count >= 2:
        score += MULTI_SOURCE_BONUS
        reasons.append(f"Multi-feed confirmation ({source_count} sources)")

    # Adaptive liquidity/MC ratio: >= 15% for < $200k MC, >= 8% for >= $200k MC
    required_liq_mc_ratio = (
        MIN_LIQUIDITY_MC_RATIO_MIDCAP
        if market_cap >= MIDCAP_THRESHOLD_USD
        else MIN_LIQUIDITY_MC_RATIO
    )

    # Liquidity compared with market capitalisation
    liquidity_mc_ratio = (
        liquidity / market_cap if market_cap > 0 else None
    )

    if market_cap <= 0:
        reasons.append("Missing or invalid market cap")
    else:
        if market_cap < MIN_MARKET_CAP_USD:
            reasons.append(
                f"Market cap (${market_cap:,.2f}) below minimum of ${MIN_MARKET_CAP_USD:,.2f}"
            )
        if liquidity_mc_ratio < required_liq_mc_ratio:
            reasons.append(f"Liquidity below {int(required_liq_mc_ratio * 100)}% of market cap")

    # ------------------------------------------------------------------ #
    # CHART-BASED ENTRY GATES (use data already returned by DexScreener) #
    # ------------------------------------------------------------------ #

    # --- 1-hour trajectory ---
    raw_pc_1h = token.get("price_change_1h")
    price_change_1h = None
    if raw_pc_1h is not None:
        try:
            val = float(raw_pc_1h)
            if math.isfinite(val):
                price_change_1h = val
        except (ValueError, TypeError):
            pass

    is_down_trending = price_change_1h is not None and price_change_1h < 0.0
    if is_down_trending:
        reasons.append(
            f"Negative 1-hour price change ({price_change_1h:+.1f}%) indicates down-trending asset"
        )

    # Anti-top cap: reject if already up >400% in the last hour.
    # Entering after a vertical parabolic move almost always means buying the top.
    is_extended_pump = (
        price_change_1h is not None and price_change_1h > MAX_PUMP_1H_PCT
    )
    if is_extended_pump:
        reasons.append(
            f"Token already up {price_change_1h:+.0f}% in the last hour — likely buying the top (cap: {MAX_PUMP_1H_PCT:.0f}%)"
        )

    # --- 5-minute momentum (most recent candle) ---
    raw_pc_m5 = token.get("price_change_m5")
    price_change_m5 = None
    if raw_pc_m5 is not None:
        try:
            val = float(raw_pc_m5)
            if math.isfinite(val):
                price_change_m5 = val
        except (ValueError, TypeError):
            pass

    # Require the last 5-min candle to be green (not dumping right now).
    is_5m_red = (
        REQUIRE_GREEN_5M
        and price_change_m5 is not None
        and price_change_m5 < 0.0
    )
    if is_5m_red:
        reasons.append(
            f"Last 5-minute candle is red ({price_change_m5:+.1f}%) — active dump in progress"
        )

    # Anti-FOMO 5m spike cap: reject single-candle vertical pumps (> +150% in 5 min).
    is_5m_fomo_spike = (
        price_change_m5 is not None
        and price_change_m5 > MAX_PUMP_5M_PCT
    )
    if is_5m_fomo_spike:
        reasons.append(
            f"5-minute candle already spiked {price_change_m5:+.0f}% — anti-FOMO cap ({MAX_PUMP_5M_PCT:.0f}%)"
        )

    # --- 5-minute order flow ---
    buys_5m = token.get("buys_5m")
    sells_5m = token.get("sells_5m")

    buys_5m_int = None
    sells_5m_int = None
    if buys_5m is not None:
        try:
            buys_5m_int = int(buys_5m)
        except (ValueError, TypeError):
            pass
    if sells_5m is not None:
        try:
            sells_5m_int = int(sells_5m)
        except (ValueError, TypeError):
            pass

    # Require net buy dominance in the last 5 minutes.
    is_5m_sell_dominated = (
        REQUIRE_5M_BUY_DOMINANCE
        and buys_5m_int is not None
        and sells_5m_int is not None
        and buys_5m_int <= sells_5m_int
    )
    if is_5m_sell_dominated:
        reasons.append(
            f"5-min order flow is sell-dominated ({buys_5m_int}B / {sells_5m_int}S) — no active accumulation"
        )

    # Require minimum buy count in the last 5 minutes (not a dead token).
    is_5m_inactive = (
        buys_5m_int is not None
        and buys_5m_int < MIN_5M_BUYS
    )
    if is_5m_inactive:
        reasons.append(
            f"Only {buys_5m_int} buys in the last 5 minutes (minimum: {MIN_5M_BUYS}) — inactive"
        )

    # --- 5-minute USD volume check ---
    volume_5m = _to_number(token.get("volume_5m"))
    is_5m_low_volume = (
        volume_5m is not None
        and volume_5m < MIN_VOLUME_5M_USD
    )
    if is_5m_low_volume:
        reasons.append(
            f"5-min USD volume (${volume_5m:,.2f}) below minimum of ${MIN_VOLUME_5M_USD:,.2f}"
        )

    # --- Volume acceleration: is 5-min activity >= half the expected hourly pace? ---
    # Expected pace per 5 min = (buys_1h + sells_1h) / 12
    # We want: (buys_5m + sells_5m) / expected_pace >= MIN_5M_ACCELERATION
    is_volume_decelerating = False
    if (
        buys_5m_int is not None and sells_5m_int is not None
        and trades > 0
    ):
        expected_5m_pace = trades / 12.0
        actual_5m_trades = buys_5m_int + sells_5m_int
        acceleration_ratio = actual_5m_trades / expected_5m_pace if expected_5m_pace > 0 else 1.0
        if acceleration_ratio < MIN_5M_ACCELERATION:
            is_volume_decelerating = True
            reasons.append(
                f"5-min volume fading: {actual_5m_trades} trades vs expected pace of "
                f"{expected_5m_pace:.0f}/5min (ratio: {acceleration_ratio:.2f}x, min: {MIN_5M_ACCELERATION}x)"
            )

    # Adaptive 1h buy/sell ratio:
    # Require >= 55% when 5m momentum is explicitly confirmed green + buy-led;
    # otherwise enforce the stricter 60% (60:40) baseline.
    has_confirmed_5m_momentum = (
        price_change_m5 is not None
        and price_change_m5 >= 0.0
        and buys_5m_int is not None
        and sells_5m_int is not None
        and buys_5m_int > sells_5m_int
    )
    required_buy_ratio = (
        MIN_BUY_RATIO_WITH_5M_MOMENTUM
        if has_confirmed_5m_momentum
        else MIN_BUY_RATIO
    )

    # Paper-trading entry requirements
    eligible = (
        score >= MIN_OPPORTUNITY_SCORE
        and liquidity >= MIN_LIQUIDITY_USD
        and market_cap >= MIN_MARKET_CAP_USD
        and liquidity_mc_ratio is not None
        and liquidity_mc_ratio >= required_liq_mc_ratio
        and volume >= MIN_VOLUME_1H_USD
        and trades >= MIN_TRADES
        and not extreme_volume_ratio
        and buy_ratio is not None
        and required_buy_ratio <= buy_ratio <= MAX_BUY_RATIO
        and not is_down_trending
        and not is_extended_pump
        and not is_5m_red
        and not is_5m_fomo_spike
        and not is_5m_sell_dominated
        and not is_5m_inactive
        and not is_5m_low_volume
        and not is_volume_decelerating
    )

    if buy_ratio is not None and buy_ratio < required_buy_ratio:
        reasons.append(
            f"Buy/sell ratio ({buy_ratio*100:.1f}%) below minimum requirement ({required_buy_ratio*100:.0f}%)"
        )

    if liquidity < MIN_LIQUIDITY_USD:
        reasons.append(
            f"Liquidity (${liquidity:,.2f}) below minimum of ${MIN_LIQUIDITY_USD:,.2f}"
        )

    if score < MIN_OPPORTUNITY_SCORE:
        reasons.append(
            f"Opportunity score below minimum of {MIN_OPPORTUNITY_SCORE}"
        )

    if trades < MIN_TRADES:
        reasons.append(
            f"Insufficient trading activity: fewer than {MIN_TRADES} trades"
        )

    if volume <= 0:
        reasons.append("No trading volume")
    elif volume < MIN_VOLUME_1H_USD:
        reasons.append(
            f"1h volume (${volume:,.2f}) below minimum of ${MIN_VOLUME_1H_USD:,.2f}"
        )

    return {
        "opportunity_score": min(score, 100),
        "eligible_for_paper_trading": eligible,
        "reasons": reasons,
    }