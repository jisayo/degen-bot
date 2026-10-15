from rugcheck_api import get_rugcheck_report, summarise_risk

# Solana's wrapped SOL mint, used to test the API connection.
MINT = "So11111111111111111111111111111111111111112"

try:
    report = get_rugcheck_report(MINT)
    summary = summarise_risk(report)

    print("RugCheck API connected!")
    print("Risk score:", summary["risk_score"])
    print("Risks:", summary["risks"])

except Exception as error:
    print("Test failed:", error)
