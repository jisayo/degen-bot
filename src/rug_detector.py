def check_rug_risk(token: dict) -> dict:
    """Flag basic market risks before a token is considered for trading."""
    risks = []
    score = 0

    liquidity = float(token.get("liquidity_usd") or 0)
    volume = float(token.get("volume_24h") or 0)
    buys = int(token.get("buys_24h") or 0)
    sells = int(token.get("sells_24h") or 0)

    if liquidity <= 0:
        risks.append("No verified liquidity")
        score += 100
    elif liquidity < 5_000:
        risks.append("Very low liquidity")
        score += 35

    if volume <= 0:
        risks.append("No trading volume")
        score += 25

    if buys + sells < 10:
        risks.append("Very low trading activity")
        score += 15

    if sells > 0 and buys / sells > 10:
        risks.append("Unusually buy-heavy activity")
        score += 10

    score = min(score, 100)

    return {
        "risk_score": score,
        "risk_level": (
            "HIGH" if score >= 60
            else "MEDIUM" if score >= 30
            else "LOW"
        ),
        "risks": risks,
        "trade_allowed": score < 30,
    }
