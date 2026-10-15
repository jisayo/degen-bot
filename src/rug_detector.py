from rugcheck_api import get_rugcheck_report, summarise_risk


def check_rug_risk(token: dict) -> dict:
    risks = []
    score = 0

    liquidity = float(token.get("liquidity_usd") or 0)
    volume = float(token.get("volume_24h") or 0)
    buys = int(token.get("buys_24h") or 0)
    sells = int(token.get("sells_24h") or 0)

    if liquidity <= 0:
        risks.append("No verified liquidity")
        score += 100
    elif liquidity < 5000:
        risks.append("Very low liquidity")
        score += 35

    if volume <= 0:
        risks.append("No trading volume")
        score += 25

    if buys + sells < 10:
        risks.append("Very low trading activity")
        score += 15

    if buys > 10 * max(sells, 1) and buys >= 30:
        risks.append("Unusually buy-heavy activity")
        score += 10

    rugcheck = None
    try:
        report = get_rugcheck_report(token["address"])
        rugcheck = summarise_risk(report)

        if rugcheck["risk_score"] is None:
            risks.append("RugCheck score unavailable")
            score += 50

        for item in rugcheck["risks"]:
            if item["level"].lower() in {"danger", "critical", "high"}:
                risks.append(f"RugCheck: {item['name']}")
                score += 30

    except Exception as error:
        risks.append(f"RugCheck unavailable: {type(error).__name__}")
        score += 50

    score = min(score, 100)

    return {
        "risk_score": score,
        "risk_level": (
            "HIGH" if score >= 60
            else "MEDIUM" if score >= 30
            else "LOW"
        ),
        "risks": risks,
        "rugcheck": rugcheck,
        "trade_allowed": score < 30 and rugcheck is not None,
    }
