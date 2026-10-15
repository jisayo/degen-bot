from rug_detector import check_rug_risk

# No liquidity: the detector should block this token.
token = {
    "address": "So11111111111111111111111111111111111111112",
    "liquidity_usd": 0,
    "volume_24h": 0,
    "buys_24h": 0,
    "sells_24h": 0,
}

result = check_rug_risk(token)

print("Risk score:", result["risk_score"])
print("Risk level:", result["risk_level"])
print("Reasons:", result["risks"])
print("Trade allowed:", result["trade_allowed"])

assert result["trade_allowed"] is False
print("Test passed!")
