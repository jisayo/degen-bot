import requests

BASE_URL = "https://api.rugcheck.xyz/v1/tokens"


def get_rugcheck_report(mint_address: str) -> dict:
    """Fetch a read-only RugCheck report for a Solana token."""

    if not mint_address or not 32 <= len(mint_address) <= 44:
        raise ValueError("Invalid-looking Solana mint address")

    url = f"{BASE_URL}/{mint_address}/report"

    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=15,
    )
    response.raise_for_status()

    report = response.json()

    if not isinstance(report, dict):
        raise ValueError("Unexpected RugCheck response")

    return report


def summarise_risk(report: dict) -> dict:
    """Extract available risk information without assuming fields exist."""

    token = report.get("token") or {}
    risks = report.get("risks") or []

    return {
        "token_name": token.get("name"),
        "risk_score": report.get("score_normalised"),
        "risks": [
            {
                "name": risk.get("name", "Unknown"),
                "level": risk.get("level", "unknown"),
                "description": risk.get("description", ""),
            }
            for risk in risks
            if isinstance(risk, dict)
        ],
        "mint_authority": token.get("mintAuthority"),
        "freeze_authority": token.get("freezeAuthority"),
    }
