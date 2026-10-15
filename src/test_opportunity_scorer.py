from opportunity_scorer import score_opportunity

token = {
    "liquidity_usd": 25000,
    "volume_24h": 80000,
    "buys_24h": 160,
    "sells_24h": 80,
}

result = score_opportunity(token)

print("Score:", result["opportunity_score"])
print("Paper-trading eligible:", result["eligible_for_paper_trading"])
print("Reasons:", result["reasons"])

assert result["opportunity_score"] > 0
assert result["eligible_for_paper_trading"] is True

print("Test passed!")
