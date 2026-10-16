import requests

from rug_detector import check_rug_risk
from opportunity_scorer import score_opportunity

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"
TIMEOUT = 15
MAX_TOKENS = 10


def to_float(value):
    try:
        number = float(value)
        return number if number >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def to_int(value):
    try:
        number = int(value)
        return max(number, 0)
    except (TypeError, ValueError):
        return 0


def scan_tokens():
    results = []

    try:
        response = requests.get(API_URL, timeout=TIMEOUT)
        response.raise_for_status()
        profiles = response.json()

        if not isinstance(profiles, list):
            print("Scanner error: unexpected profiles response.")
            return results

        tokens = [
            token
            for token in profiles
            if isinstance(token, dict)
            and token.get("chainId") == "solana"
            and token.get("tokenAddress")
        ]

        print(f"\nFound {len(tokens)} recent Solana profiles.\n")

        seen = set()

        for token in tokens[:MAX_TOKENS]:
            address = token["tokenAddress"]

            if address in seen:
                continue
            seen.add(address)

            try:
                response = requests.get(
                    PAIR_URL.format(address),
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
                pairs = response.json()

                if not isinstance(pairs, list) or not pairs:
                    print(f"{address}: No pair data; skipped.")
                    continue

                valid_pairs = [
                    pair for pair in pairs
                    if isinstance(pair, dict)
                    and pair.get("chainId") == "solana"
                ]

                if not valid_pairs:
                    print(f"{address}: No valid Solana pair; skipped.")
                    continue

                # Select the pair with the highest reported USD liquidity.
                pair = max(
                    valid_pairs,
                    key=lambda item: to_float(
                        (item.get("liquidity") or {}).get("usd")
                    ),
                )

                txns = pair.get("txns") or {}
                h24 = txns.get("h24") or {}
                liquidity = to_float(
                    (pair.get("liquidity") or {}).get("usd")
                )
                price = to_float(pair.get("priceUsd"))

                market_data = {
                    "address": address,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "volume_24h": to_float(
                        (pair.get("volume") or {}).get("h24")
                    ),
                    "buys_24h": to_int(h24.get("buys")),
                    "sells_24h": to_int(h24.get("sells")),
                }

                # Never evaluate a token for paper trading without a price.
                if price <= 0:
                    print(f"{address}: Missing/invalid price; skipped.")
                    continue

                risk = check_rug_risk(market_data)
                opportunity = score_opportunity(market_data)

                # Both gates must pass. Scores do not guarantee safety.
                paper_eligible = (
                    risk.get("risk_level") == "LOW"
                    and risk.get("trade_allowed") is True
                    and opportunity.get("eligible_for_paper_trading") is True
                    and liquidity > 0
                )

                results.append({
                    "address": address,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "pair_url": pair.get("url", "N/A"),
                    "risk": risk,
                    "opportunity": opportunity,
                    "paper_eligible": paper_eligible,
                })

            except (
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
            ) as error:
                print(f"Could not analyse {address}: {error}")

    except (requests.RequestException, ValueError) as error:
        print(f"Scanner failed: {error}")
        return results

    results.sort(
        key=lambda item: item["opportunity"]["opportunity_score"],
        reverse=True,
    )

    print("\n===== RANKED TOKEN RESULTS =====")

    for item in results:
        risk = item["risk"]
        opportunity = item["opportunity"]

        print(f"\nToken: {item['address']}")
        print(f"Price: ${item['price_usd']:.12g}")
        print(f"Liquidity: ${item['liquidity_usd']:,.2f}")
        print(
            f"Risk: {risk.get('risk_level', 'UNKNOWN')} "
            f"({risk.get('risk_score', 'N/A')}/100)"
        )
        print(f"Risk reasons: {risk.get('risks', [])}")
        print(
            f"Opportunity score: "
            f"{opportunity.get('opportunity_score', 0)}/100"
        )
        print(f"Opportunity reasons: {opportunity.get('reasons', [])}")
        print(f"Paper-trading eligible: {item['paper_eligible']}")
        print(f"Pair: {item['pair_url']}")
        print("-" * 45)

    return results


if __name__ == "__main__":
    scan_tokens()
