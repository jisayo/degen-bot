import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "results" / "launch_data" / "onchain_events.jsonl"
ENV_FILE = ROOT / ".env"

PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump_fun",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "raydium_cpmm",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "raydium_clmm",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium_amm_v4",
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "raydium_launchlab",
}


def load_api_key():
    # Prefer an environment variable; otherwise read the local .env.
    key = os.environ.get("HELIUS_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("HELIUS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise RuntimeError("HELIUS_API_KEY missing from environment and .env")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def append_event(event):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, separators=(",", ":")) + "\n")


async def listen_once(key):
    url = f"wss://mainnet.helius-rpc.com/?api-key={key}"
    subscriptions = {}

    async with websockets.connect(
        url,
        open_timeout=15,
        ping_interval=20,
        ping_timeout=60,
        close_timeout=5,
        max_size=4 * 1024 * 1024,
    ) as ws:
        # Send all subscriptions before waiting for acknowledgements.
        requests = {}
        for request_id, (program_id, label) in enumerate(PROGRAMS.items(), 1):
            requests[request_id] = {
                "program_id": program_id,
                "venue": label,
            }
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [program_id]},
                    {"commitment": "processed"},
                ],
            }))

        # Process acknowledgements as they arrive.
        while len(subscriptions) < len(PROGRAMS):
            message = json.loads(await asyncio.wait_for(ws.recv(), 30))

            if message.get("id") in requests:
                request_id = message["id"]
                details = requests[request_id]

                if "error" in message:
                    raise RuntimeError(
                        f"Subscription rejected for {details['venue']}: "
                        f"{message['error']}"
                    )

                sub_id = message.get("result")
                if not isinstance(sub_id, int):
                    raise RuntimeError(
                        f"Unexpected subscription response for "
                        f"{details['venue']}"
                    )

                subscriptions[sub_id] = details
                print(f"Subscribed: {details['venue']}")

            elif message.get("method") == "logsNotification":
                await save_notification(message, subscriptions)

        print(f"Listening to {len(subscriptions)} program subscriptions.")
        async for raw_message in ws:
            try:
                message = json.loads(raw_message)
                if message.get("method") == "logsNotification":
                    await save_notification(message, subscriptions)
            except (json.JSONDecodeError, TypeError) as exc:
                print(f"Skipping malformed WebSocket message: {exc}")


async def save_notification(message, subscriptions):
    params = message.get("params", {})
    sub_id = params.get("subscription")
    details = subscriptions.get(sub_id)

    # Ignore notifications that cannot be mapped to a known subscription.
    if not details:
        return

    result = params.get("result", {})
    context = result.get("context", {})
    value = result.get("value", {})

    event = {
        "observed_at_utc": utc_now(),
        "event_type": "raw_program_log",
        "venue": details["venue"],
        "program_id": details["program_id"],
        "slot": context.get("slot"),
        "signature": value.get("signature"),
        "err": value.get("err"),
        "logs": value.get("logs", []),
    }
    await asyncio.to_thread(append_event, event)
    # Event collection is monitored through file growth.


async def main():
    key = load_api_key()
    delay = 2

    while True:
        try:
            await listen_once(key)
            delay = 2
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never print the WebSocket URL or API key.
            print(f"Listener disconnected/error: {type(exc).__name__}: {exc}")
            print(f"Reconnecting in {delay}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nListener stopped.")
