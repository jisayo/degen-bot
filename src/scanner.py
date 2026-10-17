import time
import requests

from rug_detector import check_rug_risk
from opportunity_scorer import score_opportunity

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"
TIMEOUT = 15
MAX_TOKENS = 10
MIN_LIQUIDITY_TO_MC_RATIO = 0.50
MIN_TOKEN_AGE_MINUTES = 5
MAX_TOKEN_AGE_MINUTES = 60


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


def get_token_age_minutes(pair, now_ms=None):
    created_at = pair.get("pairCreatedAt")
    try:
        created_at = float(created_at)
        if created_at <= 0:
            return None
        current_ms = now_ms if now_ms is not None else time.time() * 1000
        age = (current_ms - created_at) / 60000
        return age if age >= 0 else None
    except (TypeError, ValueError):
        return None


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

                age_minutes = get_token_age_minutes(pair)
                if age_minutes is None:
                    print(f"{address}: Missing/invalid pair creation time; skipped.")
                    continue
                if not MIN_TOKEN_AGE_MINUTES <= age_minutes <= MAX_TOKEN_AGE_MINUTES:
                    print(f"{address}: Age {age_minutes:.1f} minutes outside 5–60 minute window; skipped.")
                    continue

                txns = pair.get("txns") or {}
                h24 = txns.get("h24") or {}
                liquidity = to_float(
                    (pair.get("liquidity") or {}).get("usd")
                )
                price = to_float(pair.get("priceUsd"))
                market_cap = to_float(pair.get("marketCap"))
                liquidity_mc_ratio = (
                    liquidity / market_cap if market_cap > 0 else None
                )

                market_data = {
                    "address": address,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "market_cap_usd": market_cap,
                    "liquidity_mc_ratio": liquidity_mc_ratio,
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
                    and liquidity_mc_ratio is not None
                    and liquidity_mc_ratio >= MIN_LIQUIDITY_TO_MC_RATIO
                )

                results.append({
                    "address": address,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "market_cap_usd": market_cap,
                    "liquidity_mc_ratio": liquidity_mc_ratio,
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
        print(f"Market cap: ${item.get('market_cap_usd', 0):,.2f}")
        ratio = item.get("liquidity_mc_ratio")
        print(f"Liquidity/MC: {ratio:.1%}" if ratio is not None else "Liquidity/MC: unavailable")
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
