import requests

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
                pair_response = requests.get(
                    PAIR_URL.format(address), timeout=15
                )
                pair_response.raise_for_status()
                pairs = pair_response.json()

                if not pairs:
                    print(f"Token: {address}")
                    print("No trading pair data available yet.\n")
                    continue

                pair = max(
                    pairs,
                    key=lambda item: float(
                        (item.get("liquidity") or {}).get("usd") or 0
                    ),
                )

                liquidity = (pair.get("liquidity") or {}).get("usd", 0)
                volume = (pair.get("volume") or {}).get("h24", 0)
                transactions = pair.get("txns") or {}
                buys = (transactions.get("h24") or {}).get("buys", 0)
                sells = (transactions.get("h24") or {}).get("sells", 0)

                print(f"Token: {address}")
                print(f"Price USD: {pair.get('priceUsd', 'N/A')}")
                print(f"Liquidity USD: ${liquidity or 0}")
                print(f"24h Volume: ${volume or 0}")
                print(f"24h Buys: {buys} | Sells: {sells}")
                print(f"Market Cap: {pair.get('marketCap', 'N/A')}")
                print(f"DEX: {pair.get('dexId', 'N/A')}")
                print(f"URL: {pair.get('url', 'N/A')}")
                print("-" * 45)

            except (requests.RequestException, ValueError) as error:
                print(f"Could not analyse {address}: {error}")

    except (requests.RequestException, ValueError) as error:
        print(f"Scanner failed: {error}")


if __name__ == "__main__":
    scan_tokens()
