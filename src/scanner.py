import requests
from rug_detector import check_rug_risk
from opportunity_scorer import score_opportunity

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"


def scan_tokens():
    try:
        response = requests.get(API_URL, timeout=15)
        response.raise_for_status()
        profiles = response.json()

        tokens = [
            token for token in profiles
            if token.get("chainId") == "solana"
        ]

        results = []
        print(f"\nFound {len(tokens)} recent Solana profiles.\n")

        for token in tokens[:10]:
            address = token.get("tokenAddress")

            try:
                response = requests.get(
                    PAIR_URL.format(address), timeout=15
                )
                response.raise_for_status()
                pairs = response.json()

                if not pairs:
                    print(f"{address}: No pair data; skipped.")
                    continue

                pair = max(
                    pairs,
                    key=lambda p: float(
                        (p.get("liquidity") or {}).get("usd") or 0
                    ),
                )

                txns = pair.get("txns") or {}
                h24 = txns.get("h24") or {}

                market_data = {
                    "address": address,
                    "liquidity_usd": (pair.get("liquidity") or {}).get("usd", 0),
                    "volume_24h": (pair.get("volume") or {}).get("h24", 0),
                    "buys_24h": h24.get("buys", 0),
                    "sells_24h": h24.get("sells", 0),
                }

                risk = check_rug_risk(market_data)
                opportunity = score_opportunity(market_data)

                # A high opportunity score never overrides the risk gate.
                paper_eligible = (
                    risk["risk_level"] == "LOW"
                    and risk["trade_allowed"]
                    and opportunity["eligible_for_paper_trading"]
                )

                results.append({
                    "address": address,
                    "pair_url": pair.get("url", "N/A"),
                    "risk": risk,
                    "opportunity": opportunity,
                    "paper_eligible": paper_eligible,
                })

            except (requests.RequestException, ValueError, KeyError) as error:
                print(f"Could not analyse {address}: {error}")

        results.sort(
            key=lambda item: item["opportunity"]["opportunity_score"],
            reverse=True,
        )

        print("\n===== RANKED TOKEN RESULTS =====")

        for item in results:
            risk = item["risk"]
            opportunity = item["opportunity"]

            print(f"\nToken: {item['address']}")
            print(f"Risk: {risk['risk_level']} ({risk['risk_score']}/100)")
            print(f"Risk reasons: {risk['risks']}")
            print(f"Opportunity score: {opportunity['opportunity_score']}/100")
            print(f"Opportunity reasons: {opportunity['reasons']}")
            print(f"Paper-trading eligible: {item['paper_eligible']}")
            print(f"Pair: {item['pair_url']}")
            print("-" * 45)

    except (requests.RequestException, ValueError) as error:
        print(f"Scanner failed: {error}")


if __name__ == "__main__":
    scan_tokens()
