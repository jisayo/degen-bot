import requests
from rug_detector import check_rug_risk

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

        print(f"\nFound {len(tokens)} recent Solana token profiles.\n")

        for token in tokens[:10]:
            address = token.get("tokenAddress")

            try:
                response = requests.get(
                    PAIR_URL.format(address), timeout=15
                )
                response.raise_for_status()
                pairs = response.json()

                if not pairs:
                    print(f"{address}: No pair data; trading blocked.")
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

                result = check_rug_risk(market_data)

                print(f"\nToken: {address}")
                print(f"Price USD: {pair.get('priceUsd', 'N/A')}")
                print(f"Liquidity: ${market_data['liquidity_usd'] or 0}")
                print(f"24h volume: ${market_data['volume_24h'] or 0}")
                print(f"24h buys/sells: {market_data['buys_24h']}/{market_data['sells_24h']}")
                print(f"Risk: {result['risk_level']} ({result['risk_score']}/100)")
                print(f"Reasons: {result['risks']}")
                print(f"Passes filter: {result['trade_allowed']}")
                print(f"Pair: {pair.get('url', 'N/A')}")
                print("-" * 45)

            except (requests.RequestException, ValueError) as error:
                print(f"Could not analyse {address}: {error}")

    except (requests.RequestException, ValueError) as error:
        print(f"Scanner failed: {error}")


if __name__ == "__main__":
    scan_tokens()
