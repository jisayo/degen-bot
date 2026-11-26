import time
import requests

from rug_detector import check_rug_risk
from opportunity_scorer import score_opportunity

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
BOOSTS_TOP_URL = "https://api.dexscreener.com/token-boosts/top/v1"
GECKOTERMINAL_TRENDING_URL = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
GECKOTERMINAL_NEW_POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"

TIMEOUT = 15
MAX_TOKENS = 50

# Base/quote infrastructure mints to ignore if returned as a pool base token
IGNORED_SOLANA_MINTS = {
    "So11111111111111111111111111111111111111112",  # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}

MIN_LIQUIDITY_USD = 20000.0
MIN_MARKET_CAP_USD = 75000.0
MIN_LIQUIDITY_TO_MC_RATIO = 0.15
MIN_TOKEN_AGE_MINUTES = 3
MAX_TOKEN_AGE_MINUTES = 1440  # 24 hours so trending multi-DEX pools are evaluated


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


def to_signed_float(value):
    """Convert a value to a finite float, preserving negative values."""
    try:
        number = float(value)
        if number != number or number == float("inf") or number == float("-inf"):
            return None
        return number
    except (TypeError, ValueError, OverflowError):
        return None


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


def fetch_extra_discovery_tokens():
    """Fetch additional Solana token dicts from GeckoTerminal (trending + new pools) and DexScreener top boosts."""
    extra_tokens = []

    # 1. GeckoTerminal Trending & New Solana Pools (covers Raydium, PumpSwap, Meteora, Orca)
    for url, source_name in (
        (GECKOTERMINAL_TRENDING_URL, "geckoterminal_trending"),
        (GECKOTERMINAL_NEW_POOLS_URL, "geckoterminal_new_pools"),
    ):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            for pool in (payload.get("data") or []) if isinstance(payload, dict) else []:
                rels = pool.get("relationships") or {}
                base_id = ((rels.get("base_token") or {}).get("data") or {}).get("id", "")
                if isinstance(base_id, str) and base_id.startswith("solana_"):
                    addr = base_id[len("solana_"):]
                    if addr and addr not in IGNORED_SOLANA_MINTS:
                        extra_tokens.append({"chainId": "solana", "tokenAddress": addr, "source": source_name})
        except (requests.RequestException, ValueError, TypeError) as error:
            print(f"GeckoTerminal discovery warning ({source_name}): {error}")

    # 2. DexScreener Top Boosted Tokens
    try:
        resp = requests.get(BOOSTS_TOP_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        boosts = resp.json()
        if isinstance(boosts, list):
            for item in boosts:
                if (
                    isinstance(item, dict)
                    and item.get("chainId") == "solana"
                    and item.get("tokenAddress")
                    and item["tokenAddress"] not in IGNORED_SOLANA_MINTS
                ):
                    extra_tokens.append({"chainId": "solana", "tokenAddress": item["tokenAddress"], "source": "dexscreener_boosts"})
    except (requests.RequestException, ValueError, TypeError) as error:
        print(f"DexScreener boosts discovery warning: {error}")

    return extra_tokens


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
            and token["tokenAddress"] not in IGNORED_SOLANA_MINTS
        ]

        # Merge multi-DEX trending/boosted feeds and deduplicate preserving order
        extra_tokens = fetch_extra_discovery_tokens()
        deduped = []
        seen_discovery = set()
        for token in tokens + extra_tokens:
            addr = token["tokenAddress"]
            if addr not in seen_discovery:
                seen_discovery.add(addr)
                deduped.append(token)
        tokens = deduped

        print(f"\nFound {len(tokens)} unique Solana candidates across discovery feeds (scanning up to {MAX_TOKENS}).\n")

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
                        f"outside the {MIN_TOKEN_AGE_MINUTES}–{MAX_TOKEN_AGE_MINUTES} minute window; skipped."
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
                volume_5m = (
                    to_float(volume_data.get("m5"))
                    if volume_data.get("m5") is not None
                    else None
                )

                price_change = pair.get("priceChange") or {}
                price_change_h1 = to_signed_float(price_change.get("h1")) if price_change.get("h1") is not None else None
                price_change_m5 = to_signed_float(price_change.get("m5")) if price_change.get("m5") is not None else None

                m5 = transactions.get("m5") or {}
                buys_m5 = to_int(m5.get("buys")) if isinstance(m5, dict) else None
                sells_m5 = to_int(m5.get("sells")) if isinstance(m5, dict) else None

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
                    "volume_1h": volume_1h,
                    "volume_5m": volume_5m,
                    "buys_1h": buys_h1,
                    "sells_1h": sells_h1,

                    # Momentum and short-term flow indicators
                    "volume_5m": volume_5m,
                    "price_change_1h": price_change_h1,
                    "price_change_m5": price_change_m5,
                    "buys_5m": buys_m5,
                    "sells_5m": sells_m5,
                }

                risk = check_rug_risk(market_data)
                opportunity = score_opportunity(market_data)

                paper_eligible = (
                    risk.get("risk_level") == "LOW"
                    and risk.get("trade_allowed") is True
                    and opportunity.get(
                        "eligible_for_paper_trading"
                    ) is True
                    and liquidity >= MIN_LIQUIDITY_USD
                    and market_cap >= MIN_MARKET_CAP_USD
                    and liquidity_mc_ratio is not None
                    and liquidity_mc_ratio >= MIN_LIQUIDITY_TO_MC_RATIO
                )

                base_token = pair.get("baseToken", {}) if isinstance(pair.get("baseToken"), dict) else {}
                token_symbol = base_token.get("symbol", "UNKNOWN")
                token_name = base_token.get("name", "Unknown")

                results.append({
                    "address": address,
                    "symbol": token_symbol,
                    "name": token_name,
                    "price_usd": price,
                    "liquidity_usd": liquidity,
                    "market_cap_usd": market_cap,
                    "liquidity_mc_ratio": liquidity_mc_ratio,
                    "volume_1h": volume_1h,
                    "volume_5m": volume_5m,
                    "buys_1h": buys_h1,
                    "sells_1h": sells_h1,
                    "buys_5m": buys_m5,
                    "sells_5m": sells_m5,
                    "price_change_1h": price_change_h1,
                    "price_change_m5": price_change_m5,
                    "token_age_minutes": age_minutes,
                    "pair_url": pair.get("url", "N/A"),
                    "risk": risk,
                    "rugcheck_report": risk.get("report"),
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