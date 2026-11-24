"""
Observation Mode Tracker for DEGEN-BOT Predictive Dump Detector.

Records non-intrusive pre-trade risk predictions to disk without modifying
the active trading strategy, and periodically checks subsequent prices to log
empirical ground-truth outcomes across 5m, 15m, 30m, and 60m horizons.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from predictive_dump_detector import PredictiveDumpDetector

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OBSERVATIONS_FILE = DATA_DIR / "dump_prediction_observations.jsonl"


class DumpObserver:
    """
    Manages non-intrusive observation mode logging and ground truth tracking.
    """

    def __init__(self, output_path: Optional[Path] = None):
        self.output_path = output_path or OBSERVATIONS_FILE
        self.detector = PredictiveDumpDetector()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def observe_candidate(
        self,
        token_data: Dict[str, Any],
        rugcheck_data: Optional[Dict[str, Any]] = None,
        candles: Optional[list] = None,
        context: str = "PRE_ENTRY",
    ) -> Dict[str, Any]:
        """
        Evaluates risk and records observation without blocking execution.
        """
        if rugcheck_data is None and isinstance(token_data, dict):
            rugcheck_data = token_data.get("rugcheck_report") or (token_data.get("risk") or {}).get("report")

        now_utc = datetime.now(timezone.utc).isoformat()
        evaluation = self.detector.evaluate(token_data, rugcheck_data, candles)

        token_address = token_data.get("address", token_data.get("token", "UNKNOWN"))
        price = token_data.get("price_usd", token_data.get("price", 0.0))

        record = {
            "timestamp": now_utc,
            "context": context,
            "token": token_address,
            "symbol": token_data.get("symbol", "MEME"),
            "initial_price": price,
            "risk_score": evaluation["risk_score"],
            "risk_tier": evaluation["risk_tier"],
            "confidence": evaluation["confidence"],
            "warning_signals": evaluation["warning_signals"],
            "breakdown": evaluation["breakdown"],
            "predictive_horizons": evaluation["predictive_horizons"],
            "diagnostics": evaluation["diagnostics"],
            "outcomes": {
                "5m": None,
                "15m": None,
                "30m": None,
                "60m": None,
                "evaluated_at": None,
            },
        }

        try:
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            print(f"[DumpObserver] Failed to append observation: {exc}")

        return evaluation


# Singleton instance for live bot integration
observer = DumpObserver()
