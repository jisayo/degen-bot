import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
import requests

from rug_detector import check_rug_risk
from opportunity_scorer import (
    score_opportunity,
    MIN_LIQUIDITY_MC_RATIO_MIDCAP,
    MIDCAP_THRESHOLD_USD,
)

API_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
BOOSTS_TOP_URL = "https://api.dexscreener.com/token-boosts/top/v1"
GECKOTERMINAL_TRENDING_URL = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
GECKOTERMINAL_NEW_POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
PAIR_URL = "https://api.dexscreener.com/token-pairs/v1/solana/{}"

TIMEOUT = 15
MAX_TOKENS = int(os.getenv("SCAN_MAX_TOKENS", "60"))

# Priority order for round-robin candidate selection:
# genuinely new pools and fresh profiles first, then active boosts and trending pools.
FEED_PRIORITY_ORDER = (
    "gecko_new_pools",
    "ds_profiles",
    "ds_boosts",
    "gecko_trending",
)

SCAN_ANALYTICS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scan_analytics.jsonl",
)

LAST_SCAN_METRICS = {}

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


def get_last_scan_metrics():
    """Return a copy of the most recent scan cycle's discovery and rejection metrics."""
    return dict(LAST_SCAN_METRICS)


def _record_scan_analytics(metrics):
    """Append compact scan cycle metrics to data/scan_analytics.jsonl."""
    try:
        os.makedirs(os.path.dirname(SCAN_ANALYTICS_PATH), exist_ok=True)
        with open(SCAN_ANALYTICS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(metrics) + "\n")
    except OSError:
        pass


def select_balanced_candidates(ds_profiles, extra_tokens, max_tokens=MAX_TOKENS):
    """
    Deduplicate candidates across all discovery feeds while preserving source metadata,
    then select up to `max_tokens` fairly using multi-source priority + round-robin.

    Returns (selected_tokens, discovery_stats).
    """
    feed_buckets = {name: [] for name in FEED_PRIORITY_ORDER}
    sources_by_addr = {}
    token_obj_by_addr = {}
    raw_counts = Counter()

    tagged_profiles = [
        {**t, "source": t.get("source") or "ds_profiles"}
        for t in (ds_profiles or [])
        if isinstance(t, dict) and t.get("tokenAddress")
    ]
    all_tagged = tagged_profiles + [
        t for t in (extra_tokens or [])
        if isinstance(t, dict) and t.get("tokenAddress")
    ]

    for item in all_tagged:
        addr = item["tokenAddress"]
        if addr in IGNORED_SOLANA_MINTS:
            continue
        source = item.get("source") or "unknown"
        raw_counts[source] += 1

        if addr not in sources_by_addr:
            sources_by_addr[addr] = []
            token_obj_by_addr[addr] = dict(item)
        if source not in sources_by_addr[addr]:
            sources_by_addr[addr].append(source)
            if source in feed_buckets:
                feed_buckets[source].append(addr)
            else:
                feed_buckets.setdefault(source, []).append(addr)

    unique_count = len(sources_by_addr)
    overlap_addrs = [
        addr for addr, srcs in sources_by_addr.items()
        if len(srcs) >= 2
    ]
    # Sort multi-source tokens by number of feeds desc, then highest-priority feed
    def _first_feed_rank(addr):
        for idx, feed_name in enumerate(FEED_PRIORITY_ORDER):
            if feed_name in sources_by_addr[addr]:
                return idx
        return len(FEED_PRIORITY_ORDER)

    overlap_addrs.sort(key=lambda a: (-len(sources_by_addr[a]), _first_feed_rank(a)))

    selected_addrs = []
    selected_set = set()

    # 1. Prioritize tokens appearing across >= 2 independent discovery feeds
    for addr in overlap_addrs:
        if len(selected_addrs) >= max_tokens:
            break
        selected_addrs.append(addr)
        selected_set.add(addr)

    # 2. Fair round-robin across feeds so no single feed crowds out the others
    feed_iters = {
        feed_name: iter(addrs)
        for feed_name, addrs in feed_buckets.items()
    }
    active_feeds = [f for f in FEED_PRIORITY_ORDER if f in feed_iters] + [
        f for f in feed_buckets if f not in FEED_PRIORITY_ORDER
    ]

    while len(selected_addrs) < max_tokens and active_feeds:
        next_active = []
        for feed_name in active_feeds:
            if len(selected_addrs) >= max_tokens:
                break
            it = feed_iters[feed_name]
            picked = False
            for addr in it:
                if addr not in selected_set:
                    selected_set.add(addr)
                    selected_addrs.append(addr)
                    picked = True
                    next_active.append(feed_name)
                    break
            if not picked:
                continue
        active_feeds = next_active

    selected_tokens = []
    selected_per_feed = Counter()
    for addr in selected_addrs:
        tok = dict(token_obj_by_addr[addr])
        srcs = list(sources_by_addr[addr])
        tok["sources"] = srcs
        tok["source_count"] = len(srcs)
        tok["primary_source"] = srcs[0]
        selected_per_feed[srcs[0]] += 1
        selected_tokens.append(tok)

    stats = {
        "candidates_per_feed": dict(raw_counts),
        "unique_candidates": unique_count,
        "feed_overlap": len(overlap_addrs),
        "selected_for_scan": len(selected_tokens),
        "selected_per_feed": dict(selected_per_feed),
    }
    return selected_tokens, stats


def scan_tokens(max_tokens=None):
    global LAST_SCAN_METRICS
    scan_start = time.time()
    limit = MAX_TOKENS if max_tokens is None else max_tokens
    results = []
    rejection_counts = Counter()
    api_failures = 0
    tokens_evaluated = 0

    try:
        response = requests.get(API_URL, timeout=TIMEOUT)
        response.raise_for_status()
        profiles = response.json()

        if not isinstance(profiles, list):
            print("Scanner error: unexpected profiles response.")
            return results

        ds_profiles = [
            {**token, "source": "ds_profiles"}
            for token in profiles
            if isinstance(token, dict)
            and token.get("chainId") == "solana"
            and token.get("tokenAddress")
            and token["tokenAddress"] not in IGNORED_SOLANA_MINTS
        ]

        extra_tokens = fetch_extra_discovery_tokens()
        tokens, discovery_stats = select_balanced_candidates(
            ds_profiles, extra_tokens, max_tokens=limit
        )

        print(
            f"\nFound {discovery_stats['unique_candidates']} unique Solana candidates "
            f"(overlap={discovery_stats['feed_overlap']}, feeds={discovery_stats['candidates_per_feed']}); "
            f"scanning {len(tokens)} (cap={limit}).\n"
        )

        seen = set()

        for token in tokens:
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
                    rejection_counts["no_pair_data"] += 1
                    continue

                valid_pairs = [
                    pair
                    for pair in pairs
                    if isinstance(pair, dict)
                    and pair.get("chainId") == "solana"
                ]

                if not valid_pairs:
                    print(f"{address}: No valid Solana pair; skipped.")
                    rejection_counts["no_valid_solana_pair"] += 1
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
                    rejection_counts["missing_creation_time"] += 1
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
                    rejection_counts["age_window"] += 1
                    continue

                price = to_float(pair.get("priceUsd"))
                liquidity = to_float(
                    (pair.get("liquidity") or {}).get("usd")
                )
                market_cap = to_float(pair.get("marketCap"))

                if price <= 0:
                    print(f"{address}: Missing or invalid price; skipped.")
                    rejection_counts["invalid_price"] += 1
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
                    rejection_counts["missing_h1_activity"] += 1
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
                    "price_change_1h": price_change_h1,
                    "price_change_m5": price_change_m5,
                    "buys_5m": buys_m5,
                    "sells_5m": sells_m5,

                    # Multi-source discovery metadata
                    "sources": token.get("sources", []),
                    "source_count": token.get("source_count", 1),
                }

                tokens_evaluated += 1
                risk = check_rug_risk(market_data)
                opportunity = score_opportunity(market_data)

                required_liq_mc = (
                    MIN_LIQUIDITY_MC_RATIO_MIDCAP
                    if market_cap >= MIDCAP_THRESHOLD_USD
                    else MIN_LIQUIDITY_TO_MC_RATIO
                )

                paper_eligible = (
                    risk.get("risk_level") == "LOW"
                    and risk.get("trade_allowed") is True
                    and opportunity.get(
                        "eligible_for_paper_trading"
                    ) is True
                    and liquidity >= MIN_LIQUIDITY_USD
                    and market_cap >= MIN_MARKET_CAP_USD
                    and liquidity_mc_ratio is not None
                    and liquidity_mc_ratio >= required_liq_mc
                )

                if not paper_eligible:
                    if risk.get("risk_level") != "LOW" or risk.get("trade_allowed") is not True:
                        rejection_counts["rug_risk"] += 1
                    for reason in opportunity.get("reasons", []):
                        low = reason.lower()
                        if "below minimum of $20,000" in low:
                            rejection_counts["low_liquidity"] += 1
                        elif "market cap" in low and "below minimum" in low:
                            rejection_counts["low_market_cap"] += 1
                        elif "market cap" in low and "of market cap" in low:
                            rejection_counts["low_liq_mc_ratio"] += 1
                        elif "buy/sell ratio" in low:
                            rejection_counts["low_buy_ratio"] += 1
                        elif "down-trending" in low:
                            rejection_counts["negative_1h"] += 1
                        elif "buying the top" in low:
                            rejection_counts["extended_pump_1h"] += 1
                        elif "5-minute candle is red" in low:
                            rejection_counts["red_5m"] += 1
                        elif "sell-dominated" in low:
                            rejection_counts["sell_dominated_5m"] += 1
                        elif "buys in the last 5 minutes" in low:
                            rejection_counts["low_buys_5m"] += 1
                        elif "5-min usd volume" in low:
                            rejection_counts["low_vol_5m"] += 1
                        elif "5-min volume fading" in low:
                            rejection_counts["fading_pace_5m"] += 1
                        elif "volume/liquidity ratio exceeds" in low:
                            rejection_counts["extreme_vol_liq"] += 1
                        elif "opportunity score below" in low:
                            rejection_counts["low_opp_score"] += 1

                base_token = pair.get("baseToken", {}) if isinstance(pair.get("baseToken"), dict) else {}
                token_symbol = base_token.get("symbol", "UNKNOWN")
                token_name = base_token.get("name", "Unknown")

                results.append({
                    "address": address,
                    "symbol": token_symbol,
                    "name": token_name,
                    "sources": token.get("sources", []),
                    "source_count": token.get("source_count", 1),
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
                api_failures += 1
                rejection_counts["api_error"] += 1
                print(f"Could not analyse {address}: {error}")

    except (requests.RequestException, ValueError) as error:
        api_failures += 1
        print(f"Scanner failed: {error}")
        LAST_SCAN_METRICS = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_failures": api_failures,
            "scan_duration_sec": round(time.time() - scan_start, 2),
        }
        return results

    results.sort(
        key=lambda item: item["opportunity"]["opportunity_score"],
        reverse=True,
    )

    eligible_count = sum(1 for item in results if item.get("paper_eligible"))
    scan_duration = round(time.time() - scan_start, 2)
    LAST_SCAN_METRICS = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **discovery_stats,
        "tokens_evaluated": tokens_evaluated,
        "eligible_opportunities": eligible_count,
        "rejection_counts": dict(rejection_counts),
        "api_failures": api_failures,
        "scan_duration_sec": scan_duration,
    }
    _record_scan_analytics(LAST_SCAN_METRICS)

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

    print(
        f"[ScanMetrics] unique={discovery_stats['unique_candidates']} "
        f"overlap={discovery_stats['feed_overlap']} "
        f"selected={discovery_stats['selected_for_scan']} "
        f"evaluated={tokens_evaluated} eligible={eligible_count} "
        f"api_failures={api_failures} duration={scan_duration}s "
        f"selected_per_feed={discovery_stats['selected_per_feed']}"
    )

    return results


if __name__ == "__main__":
    scan_tokens()