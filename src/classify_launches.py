
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "results/launch_data/onchain_events.jsonl"
OUTPUT = Path(os.environ.get("CLASSIFIED_LAUNCHES_OUTPUT", str(ROOT / "results/launch_data/classified_launches.jsonl")))
ENV = ROOT / ".env"

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def is_create_instruction(log):
    return log.strip() in {
        "Program log: Instruction: Create",
        "Program log: Instruction: CreateV2",
    }


def get_key():
    key = os.environ.get("HELIUS_API_KEY")
    if not key and ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith("HELIUS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
                break
    if not key:
        raise RuntimeError("HELIUS_API_KEY missing")
    return key


def classify(tx):
    if not tx:
        return {"status": "unverified", "mint": None}

    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        return {"status": "not_launch", "mint": None}

    message = tx["transaction"]["message"]
    instructions = message.get("instructions", [])
    groups = {g["index"]: g.get("instructions", [])
              for g in meta.get("innerInstructions") or []}
    logs = meta.get("logMessages") or []

    for index, ix in enumerate(instructions):
        if ix.get("programId") != PUMP:
            continue

        accounts = ix.get("accounts", [])
        if not accounts:
            continue

        # A Create log alone is insufficient. Require mint initialization
        # inside this Pump.fun instruction and a matching mint account.
        inner = groups.get(index, [])
        initialized = set()

        for child in inner:
            parsed = child.get("parsed") or {}
            if parsed.get("type", "").lower() in (
                "initializemint", "initializemint2"
            ):
                mint = (parsed.get("info") or {}).get("mint")
                if mint:
                    initialized.add(mint)

        mint = accounts[0]
        if mint in initialized and any(
            is_create_instruction(log) for log in logs
        ):
            return {"status": "confirmed_launch", "mint": mint}

    if any(is_create_instruction(log) for log in logs):
        return {"status": "unverified", "mint": None}

    return {"status": "not_launch", "mint": None}


def main():
    key = get_key()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    processed = set()
    if OUTPUT.exists():
        for line in OUTPUT.read_text().splitlines():
            try:
                processed.add(json.loads(line)["signature"])
            except (ValueError, KeyError):
                pass

    candidates = {}
    with EVENTS.open() as file:
        for line in file:
            try:
                event = json.loads(line)
            except ValueError:
                continue

            if event.get("venue") != "pump_fun":
                continue
            if event.get("err") is not None:
                continue
            if not any(is_create_instruction(log)
                       for log in event.get("logs", [])):
                continue

            sig = event.get("signature")
            if sig and sig not in processed:
                candidates[sig] = event

    counts = {"confirmed_launch": 0, "not_launch": 0, "unverified": 0}
    url = "https://mainnet.helius-rpc.com/"

    with OUTPUT.open("a", encoding="utf-8") as out:
        for sig, event in candidates.items():
            result = {"status": "unverified", "mint": None}
            try:
                response = requests.post(
                    url,
                    params={"api-key": key},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [sig, {
                            "encoding": "jsonParsed",
                            "maxSupportedTransactionVersion": 1
                        }]
                    },
                    timeout=15,
                )
                response.raise_for_status()
                body = response.json()

                if body.get("error"):
                    raise RuntimeError(body["error"])

                result = classify(body.get("result"))
            except Exception as exc:
                print(f"Unverified {sig[:12]}: {type(exc).__name__}")
                # Don't mark temporary RPC failures as processed.
                continue

            record = {
                "signature": sig,
                "slot": event.get("slot"),
                **result,
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            processed.add(sig)
            counts[result["status"]] += 1
            print(result["status"], result.get("mint") or sig[:12])
            time.sleep(0.1)

    print("New candidates:", len(candidates))
    print("Classified:", counts)
    print("Output:", OUTPUT)


if __name__ == "__main__":
    main()
