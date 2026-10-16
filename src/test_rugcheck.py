import unittest
from unittest.mock import Mock, patch

import requests

from rugcheck_api import get_rugcheck_report, summarise_risk


MINT = "So11111111111111111111111111111111111111112"


class TestRugCheckAPI(unittest.TestCase):

    @patch("rugcheck_api.requests.get")
    def test_fetches_report(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "score": 1,
            "score_normalised": 1,
            "risks": [],
        }
        mock_get.return_value = mock_response

        report = get_rugcheck_report(MINT)

        self.assertEqual(report["score_normalised"], 1)
        mock_response.raise_for_status.assert_called_once()

    @patch("rugcheck_api.requests.get")
    def test_http_error_propagates(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = (
            requests.HTTPError("Server error")
        )
        mock_get.return_value = mock_response

        with self.assertRaises(requests.HTTPError):
            get_rugcheck_report(MINT)

    def test_invalid_address_rejected(self):
        with self.assertRaises(ValueError):
            get_rugcheck_report("invalid")

    def test_summarises_risk(self):
        report = {
            "score_normalised": 58,
            "risks": [
                {
                    "name": "High ownership",
                    "level": "danger",
                    "description": "Concentrated supply",
                }
            ],
        }

        summary = summarise_risk(report)

        self.assertEqual(summary["risk_score"], 58)
        self.assertEqual(len(summary["risks"]), 1)
        self.assertEqual(summary["risks"][0]["level"], "danger")


if __name__ == "__main__":
    unittest.main()
