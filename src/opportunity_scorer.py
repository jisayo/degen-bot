def score_opportunity(token: dict) -> dict:
    score = 0
    reasons = []

    liquidity = float(token.get("liquidity_usd") or 0)
    volume = float(token.get("volume_24h") or 0)
    buys = int(token.get("buys_24h") or 0)
    sells = int(token.get("sells_24h") or 0)

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

    # Trading volume relative to liquidity
    if liquidity > 0:
        ratio = volume / liquidity
        if 1 <= ratio <= 10:
            score += 20
            reasons.append("Healthy volume/liquidity ratio")
        elif ratio > 10:
            score += 5
            reasons.append("Very high volume; investigate wash trading")

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
            reasons.append("Extreme buy imbalance; investigate")

    # Basic minimum requirements
    eligible = liquidity >= 5_000 and volume > 0 and trades >= 20

    return {
        "opportunity_score": min(score, 100),
        "eligible_for_paper_trading": eligible,
        "reasons": reasons,
    }
