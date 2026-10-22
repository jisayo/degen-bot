import math

MIN_OPPORTUNITY_SCORE = 50
MIN_LIQUIDITY_MC_RATIO = 0.50
MIN_TRADES = 20
MAX_VOLUME_LIQUIDITY_RATIO = 10.0


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
        "volume_24h",
        "buys_24h",
        "sells_24h",
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
    volume = values["volume_24h"]
    buys = values["buys_24h"]
    sells = values["sells_24h"]

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

    # Volume relative to liquidity
    if liquidity > 0:
        ratio = volume / liquidity

        if 1 <= ratio <= 10:
            score += 20
            reasons.append("Healthy volume/liquidity ratio")
        elif ratio > 10:
            reasons.append(
                "Very high volume; investigate wash trading"
            )

    # Extreme reported volume relative to liquidity can indicate wash
    # trading or unreliable data. Hard-block it rather than merely warning.
    volume_liquidity_ratio = volume / liquidity if liquidity > 0 else None
    extreme_volume_ratio = (
        volume_liquidity_ratio is not None
        and volume_liquidity_ratio > MAX_VOLUME_LIQUIDITY_RATIO
    )
    if extreme_volume_ratio:
        reasons.append(
            "Volume/liquidity ratio exceeds "
            f"{MAX_VOLUME_LIQUIDITY_RATIO:g}x; blocked for review"
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
    if trades > 0:
        buy_ratio = buys / trades

        if 0.55 <= buy_ratio <= 0.75:
            score += 15
            reasons.append("Positive buying pressure")
        elif buy_ratio > 0.90:
            reasons.append(
                "Extreme buy imbalance; investigate"
            )

    # Liquidity compared with market capitalisation
    liquidity_mc_ratio = (
        liquidity / market_cap if market_cap > 0 else None
    )

    if market_cap <= 0:
        reasons.append("Missing or invalid market cap")
    elif liquidity_mc_ratio < MIN_LIQUIDITY_MC_RATIO:
        reasons.append("Liquidity below 50% of market cap")

    # Paper-trading entry requirements
    eligible = (
        score >= MIN_OPPORTUNITY_SCORE
        and liquidity > 0
        and liquidity_mc_ratio is not None
        and liquidity_mc_ratio >= MIN_LIQUIDITY_MC_RATIO
        and volume > 0
        and trades >= MIN_TRADES
        and not extreme_volume_ratio
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

    return {
        "opportunity_score": min(score, 100),
        "eligible_for_paper_trading": eligible,
        "reasons": reasons,
    }