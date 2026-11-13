import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classify_launches import classify, is_create_instruction
import launch_listener


PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
MINT = "TestMint123"


def make_tx(logs=None, err=None, initialized=True):
    inner = []
    if initialized:
        inner.append({
            "parsed": {
                "type": "initializeMint",
                "info": {"mint": MINT},
            }
        })

    return {
        "transaction": {
            "message": {
                "instructions": [{
                    "programId": PUMP,
                    "accounts": [MINT],
                }]
            }
        },
        "meta": {
            "err": err,
            "innerInstructions": [{
                "index": 0,
                "instructions": inner,
            }],
            "logMessages": logs or [],
        },
    }


def test_matching_mint_and_create_log_confirm_launch():
    result = classify(make_tx(["Program log: Instruction: Create"]))
    assert result == {"status": "confirmed_launch", "mint": MINT}


def test_failed_transaction_is_not_launch():
    result = classify(
        make_tx(["Program log: Instruction: Create"], err={"error": True})
    )
    assert result["status"] == "not_launch"


def test_create_log_without_mint_initialization_is_unverified():
    result = classify(
        make_tx(["Program log: Instruction: Create"], initialized=False)
    )
    assert result == {"status": "unverified", "mint": None}


def test_transaction_without_create_log_is_not_launch():
    result = classify(make_tx(["Program log: something else"]))
    assert result["status"] == "not_launch"


def test_missing_transaction_is_unverified():
    assert classify(None) == {"status": "unverified", "mint": None}


def test_unknown_subscription_is_ignored(tmp_path):
    output = tmp_path / "events.jsonl"
    with patch.object(launch_listener, "OUTPUT", output):
        asyncio.run(launch_listener.save_notification(
            {"params": {"subscription": 999, "result": {}}}, {}
        ))
    assert not output.exists()


def test_known_subscription_writes_event(tmp_path):
    output = tmp_path / "events.jsonl"
    subscriptions = {
        123: {"program_id": PUMP, "venue": "pump_fun"}
    }
    message = {
        "params": {
            "subscription": 123,
            "result": {
                "context": {"slot": 456},
                "value": {
                    "signature": "test-signature",
                    "err": None,
                    "logs": ["test log"],
                },
            },
        }
    }

    with patch.object(launch_listener, "OUTPUT", output):
        asyncio.run(launch_listener.save_notification(message, subscriptions))

    event = json.loads(output.read_text().strip())
    assert event["signature"] == "test-signature"
    assert event["venue"] == "pump_fun"
    assert event["slot"] == 456
    assert event["logs"] == ["test log"]


def test_create_v2_confirms_launch():
    result = classify(make_tx(["Program log: Instruction: CreateV2"]))
    assert result == {"status": "confirmed_launch", "mint": MINT}


def test_create_idempotent_is_not_launch_instruction():
    log = "Program log: Instruction: CreateIdempotentAssociatedTokenAccount"
    assert not is_create_instruction(log)
    result = classify(make_tx([log]))
    assert result == {"status": "not_launch", "mint": None}


def test_create_fee_sharing_config_is_not_launch_instruction():
    log = "Program log: Instruction: CreateFeeSharingConfig"
    assert not is_create_instruction(log)
    result = classify(make_tx([log]))
    assert result == {"status": "not_launch", "mint": None}


def test_generic_create_log_is_not_launch_instruction():
    assert not is_create_instruction("Program log: Create")
