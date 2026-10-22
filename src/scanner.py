import time
import requests

from rug_detector import check_rug_risk
from opportunity_scorer import score_opportunity

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"

TIMEOUT = 15
MAX_TOKENS = 10

MIN_LIQUIDITY_TO_MC_RATIO = 0.50
MIN_TOKEN_AGE_MINUTES = 1
MAX_TOKEN_AGE_MINUTES = 5


def to_float(value):
    """Convert a value to a finite, non-negative float."""
    try:
        number = float(value)
        if number < 0 or number != number or number == float("inf"):
            return 0.0
        if number == float("-inf"):
            return 0.0
        return number
    except (TypeError, ValueError, OverflowError):
        return 0.0


def to_int(value):
    """Convert a value to a non-negative integer."""
    try:
        number = float(value)
        if number < 0 or not number.is_integer():
            return 0
        return int(number)
    except (TypeError, ValueError, OverflowError):
        return 0


def get_token_age_minutes(pair, now_ms=None):
    """Return the pair's age in minutes, or None if invalid."""
    created_at = pair.get("pairCreatedAt")

    try:
        created_at = float(created_at)

        if created_at <= 0:
            return None

        current_ms = (
            now_ms if now_ms is not None else time.time() * 1000
        )
        age = (current_ms - created_at) / 60000

        return age if age >= 0 else None

    except (TypeError, ValueError, OverflowError):
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
                    pair
                    for pair in pairs
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
                    print(
                        f"{address}: Missing or invalid creation time; skipped."
                    )
                    continue

                if not (
                    MIN_TOKEN_AGE_MINUTES
                    <= age_minutes
                    <= MAX_TOKEN_AGE_MINUTES
                ):
                    print(
                        f"{address}: Age {age_minutes:.1f} minutes "
                        "outside the 1–5 minute window; skipped."
                    )
                    continue

                price = to_float(pair.get("priceUsd"))
                liquidity = to_float(
                    (pair.get("liquidity") or {}).get("usd")
                )
                market_cap = to_float(pair.get("marketCap"))

                if price <= 0:
                    print(f"{address}: Missing or invalid price; skipped.")
                    continue

                # Use one-hour activity for newly launched tokens.
                # Never silently substitute 24-hour totals.
                volume_data = pair.get("volume") or {}
                transactions = pair.get("txns") or {}
                h1 = transactions.get("h1")
                volume_h1 = volume_data.get("h1")

                if not isinstance(h1, dict) or volume_h1 is None:
                    print(
                        f"{address}: Missing one-hour activity data; skipped."
                    )
                    continue

                buys_h1 = to_int(h1.get("buys"))
                sells_h1 = to_int(h1.get("sells"))
                volume_1h = to_float(volume_h1)

                liquidity_mc_ratio = (
                    liquidity / market_cap if market_cap > 0 else None
                )

                market_data = {
                    "address": address,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "market_cap_usd": market_cap,

                    # The scorer currently uses these field names,
                    # but their values here represent the 1-hour window.
                    "volume_24h": volume_1h,
                    "buys_24h": buys_h1,
                    "sells_24h": sells_h1,
                }

                risk = check_rug_risk(market_data)
                opportunity = score_opportunity(market_data)

                paper_eligible = (
                    risk.get("risk_level") == "LOW"
                    and risk.get("trade_allowed") is True
                    and opportunity.get(
                        "eligible_for_paper_trading"
                    ) is True
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
                    "volume_1h": volume_1h,
                    "buys_1h": buys_h1,
                    "sells_1h": sells_h1,
                    "token_age_minutes": age_minutes,
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
        print(f"Age: {item['token_age_minutes']:.1f} minutes")
        print(f"Price: ${item['price_usd']:.12g}")
        print(f"Liquidity: ${item['liquidity_usd']:,.2f}")
        print(f"Market cap: ${item['market_cap_usd']:,.2f}")

        ratio = item["liquidity_mc_ratio"]
        if ratio is not None:
            print(f"Liquidity/MC: {ratio:.1%}")
        else:
            print("Liquidity/MC: unavailable")

        print(f"Volume (1h): ${item['volume_1h']:,.2f}")
        print(f"Buys (1h): {item['buys_1h']}")
        print(f"Sells (1h): {item['sells_1h']}")

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