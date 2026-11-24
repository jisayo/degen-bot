import math

from rugcheck_api import get_rugcheck_report, summarise_risk


def check_rug_risk(token: dict) -> dict:
    risks = []
    score = 0
    rugcheck = None
    data_valid = True

    def number(value):
        try:
            result = float(value)
            return result if math.isfinite(result) and result >= 0 else None
        except (TypeError, ValueError):
            return None

    liquidity = number(token.get("liquidity_usd"))
    volume = number(token.get("volume_1h"))
    buys = number(token.get("buys_1h"))
    sells = number(token.get("sells_1h"))

    if any(v is None for v in (liquidity, volume, buys, sells)):
        risks.append("Missing or invalid market data")
        score = 100
        data_valid = False

    if liquidity is not None:
        if liquidity <= 0:
            risks.append("No verified liquidity")
            score += 100

    if volume is not None and volume <= 0:
        risks.append("No trading volume")
        score += 25

    if buys is not None and sells is not None:
        if buys + sells < 10:
            risks.append("Very low trading activity")
            score += 15

        if buys > 10 * max(sells, 1) and buys >= 30:
            risks.append("Unusually buy-heavy activity")
            score += 10

    try:
        address = token.get("address")
        if not address:
            raise ValueError("Missing token address")

        report = get_rugcheck_report(address)
        rugcheck = summarise_risk(report)

        raw_score = rugcheck.get("risk_score")

        if (
            not isinstance(raw_score, (int, float))
            or isinstance(raw_score, bool)
            or not math.isfinite(raw_score)
            or not 0 <= raw_score <= 100
        ):
            raise ValueError("Invalid RugCheck normalized score")

        # Include RugCheck's normalized score in our risk score.
        score = max(score, int(raw_score))

        if report.get("rugged") is True:
            risks.append("RugCheck reports this token as rugged")
            score = 100

        for item in rugcheck.get("risks", []):
            level = str(item.get("level", "unknown")).lower()

            if level in {"danger", "critical", "high"}:
                risks.append(f"RugCheck: {item.get('name', 'Unknown risk')}")
                score += 30
            elif level in {"warn", "warning"}:
                risks.append(f"RugCheck warning: {item.get('name', 'Unknown risk')}")
                score += 10
            elif level not in {"info", "informational"}:
                risks.append("RugCheck contains an unknown risk level")
                score += 30

        # Check top holder supply concentration
        top_holders = report.get("topHolders", [])
        if isinstance(top_holders, list) and top_holders:
            non_pool_holders = [
                h for h in top_holders
                if isinstance(h, dict) and not h.get("isPool", False)
            ]
            percentages = [
                float(h.get("pct", 0) or 0)
                for h in non_pool_holders
                if h.get("pct") is not None
            ]
            top1_pct = max(percentages) if percentages else 0.0
            top10_sum = sum(sorted(percentages, reverse=True)[:10])

            if top1_pct > 15.0:
                risks.append(f"RugCheck: Single holder owns {top1_pct:.1f}% of supply")
                score = max(score, 75)
            elif top1_pct > 10.0:
                risks.append(f"RugCheck warning: Top holder owns {top1_pct:.1f}% of supply")
                score = max(score, score + 15)

            if top10_sum > 40.0:
                risks.append(f"RugCheck: Top 10 holders own {top10_sum:.1f}% of supply")
                score = max(score, 70)

    except Exception as error:
        risks.append(f"RugCheck validation failed: {type(error).__name__}")
        score = 100
        data_valid = False

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
        "trade_allowed": (
            data_valid
            and rugcheck is not None
            and score < 30
        ),
        "report": report if data_valid else None,
    }
