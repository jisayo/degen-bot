# DEGEN-BOT

A Solana meme-coin research, token-scanning, and paper-trading system.

DEGEN-BOT evaluates newly surfaced Solana tokens using market activity, liquidity metrics, opportunity scoring, and RugCheck risk reports. It also includes paper-trading simulations, historical backtesting, and launch-data collection tools.

> **Research and paper trading only. No live trades are executed.**
>
> This project is experimental software, not financial advice. Scores and risk checks do not guarantee that a token is safe or profitable.

## Features

- **Solana token scanner:** discovers recent Solana token profiles through DexScreener and retrieves their pair data.
- **Token-age filtering:** evaluates pairs within a configurable 1–5 minute age window.
- **Liquidity and activity checks:** uses liquidity, market capitalisation, one-hour volume, and one-hour buy/sell activity.
- **Rug-risk detection:** combines market-data validation with read-only RugCheck reports.
- **Opportunity scoring:** ranks candidates and determines paper-trading eligibility.
- **Paper trading:** simulates entries, exits, fees, slippage, and position management.
- **Historical backtesting:** evaluates strategies against stored candle data.
- **Staged exits:** supports partial profit-taking and trailing-stop logic.
- **Launch research:** collects pool observations and on-chain launch events.
- **Dataset auditing:** provides tools for inspecting and validating collected research data.

## Architecture

The main scanning and paper-trading flow is:

1. `scanner.py` retrieves recent Solana token profiles.
2. Pair data is retrieved and checked for valid age, price, liquidity, and one-hour activity.
3. `rug_detector.py` evaluates market-data warnings and requests a RugCheck report.
4. `opportunity_scorer.py` calculates an opportunity score and eligibility result.
5. A token must pass both risk and opportunity checks to become paper-trading eligible.
6. `main.py` manages simulated positions through `paper_trader.py`.

The research pipeline is separate from the main paper-trading loop. It collects launch, pool, and candle data for later analysis and backtesting.

## Project structure

```text
degen-bot/
├── src/
│   ├── main.py
│   ├── scanner.py
│   ├── opportunity_scorer.py
│   ├── rug_detector.py
│   ├── rugcheck_api.py
│   ├── paper_trader.py
│   ├── backtest_engine.py
│   ├── staged_backtest.py
│   ├── launch_listener.py
│   ├── classify_launches.py
│   ├── collect_launch_data.py
│   ├── discover_historical_pools.py
│   ├── download_backtest_candles.py
│   ├── download_november_pools.py
│   ├── download_november_candles.py
│   ├── coingecko_collector.py
│   ├── download_coingecko_november.py
│   ├── audit_dataset.py
│   └── test_*.py
├── results/
│   ├── backtest/
│   ├── historical_data/
│   └── launch_data/
├── data/                  # Local paper-trading state and logs
├── .env                   # Local API keys; do not commit
└── README.md
```

Some research files and generated datasets may be created locally when collection scripts run.

## Requirements

- Python 3.10 or newer
- pip
- Internet connection
- API keys for the data providers used by the relevant scripts

## Installation

Clone the repository:

```bash
git clone https://github.com/jisayo/degen-bot.git
cd degen-bot
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python3 -m pip install requests python-dotenv websockets pytest
```

## API configuration

Create a `.env` file in the repository root.

```env
HELIUS_API_KEY=your_helius_api_key
DEXPAPRIKA_API_KEY=your_dexpaprika_api_key
COINGECKO_DEMO_API_KEY=your_coingecko_demo_api_key
```

Only the scripts that use a particular provider require that provider's key:

| Provider | Purpose |
|---|---|
| Helius | Solana on-chain launch event listener |
| DexPaprika | Historical pool and candle collection |
| CoinGecko | Historical OHLCV collection |
| DexScreener | Token profiles, pair information, and price data |
| RugCheck | Token risk reports |

DexScreener and RugCheck are accessed through their public API endpoints in the current implementation.

**Keep API keys private.** Never commit `.env` or paste secret keys into issues, logs, or public messages. If a key is exposed, rotate it with the provider.

## Running the paper-trading bot

From the repository root, with the virtual environment activated:

```bash
python3 src/main.py
```

The bot initialises its local paper-trading state, scans for candidates, and manages simulated positions. It runs continuously until interrupted with `Ctrl+C`.

The main loop reports that live trading is disabled.

### Current scanner filters

The scanner currently applies these checks:

| Filter | Current setting |
|---|---:|
| Minimum token age | 1 minute |
| Maximum token age | 5 minutes |
| Maximum profiles processed per scan | 10 |
| Minimum liquidity / market-cap ratio | 0.50 |
| Activity window | 1 hour |
| Missing one-hour activity | Reject candidate |

The scanner selects the valid Solana pair with the highest reported USD liquidity for each candidate token.

### Opportunity scoring

The opportunity scorer currently uses:

| Rule | Current setting |
|---|---:|
| Minimum opportunity score | 50 |
| Minimum liquidity / market-cap ratio | 0.50 |
| Minimum combined buys and sells | 20 |
| Maximum volume / liquidity ratio | 10x |

Liquidity, volume, trading activity, and buy/sell balance contribute to the score. Extreme reported volume relative to liquidity is blocked for review.

### Risk checks

A candidate must pass the risk detector as well as the opportunity scorer.

The risk detector:
- Checks market-data validity and liquidity.
- Evaluates trading activity.
- Retrieves a RugCheck report.
- Rejects invalid or unavailable risk reports.
- Blocks rugged tokens and tokens whose final risk level is not LOW.

A failed RugCheck request does not silently approve a token.

## Paper-trading strategy

The paper trader simulates trades using a starting balance and configurable position sizing, fees, and slippage.

Current baseline settings include:

| Setting | Value |
|---|---:|
| Starting balance | $50 |
| Position size | 20% of available balance |
| Simulated fee | 1% |
| Simulated slippage | 1% |
| Stop loss | 15% |

The staged exit approach is:

1. At +50%, sell 50% of the original position.
2. At +100%, sell 25% of the original position.
3. Keep the remaining 25% subject to a 15% trailing stop.

These are simulation settings, not evidence of a profitable live strategy.

Paper-trading state and logs are stored under `data/`.

## Historical backtesting

The backtesting engine reads stored historical candle data and simulates strategy outcomes.

Relevant scripts:

```bash
python3 src/backtest_engine.py
python3 src/staged_backtest.py
```

Historical candle data is stored under:

```text
results/historical_data/candles/
```

Backtest outputs are stored under:

```text
results/backtest/
```

The engine validates candle data, removes duplicate timestamps, and processes candles chronologically. When a stop and target are both touched in the same candle, the simulation uses the conservative assumption that the stop is hit first.

Backtest results depend on the quality and coverage of the underlying historical data. They should not be treated as predictions of future performance.

## Launch-data research

### GeckoTerminal new-pool collection

Run:

```bash
python3 src/collect_launch_data.py
```

This continuously collects new Solana pool records and repeat observations.

Output:

```text
results/launch_data/pools.jsonl
results/launch_data/observations.jsonl
```

Stop the collector with `Ctrl+C`.

### On-chain launch listener

Set `HELIUS_API_KEY` in `.env`, then run:

```bash
python3 src/launch_listener.py
```

The listener subscribes to supported Solana program logs and records launch-related events.

Output:

```text
results/launch_data/onchain_events.jsonl
```

WebSocket connectivity depends on network stability and provider availability.

### Historical November pool collection

Set `DEXPAPRIKA_API_KEY`, then run:

```bash
python3 src/download_november_pools.py
```

This collector is configured for its November 2026 historical window and divides collection into three-hour batches.

### CoinGecko authentication and sample collection

Set `COINGECKO_DEMO_API_KEY`, then test authentication:

```bash
python3 src/coingecko_collector.py --test-auth
```

To collect a sample:

```bash
python3 src/coingecko_collector.py --sample 20
```

### CoinGecko November candle collection

Run one batch:

```bash
python3 src/download_coingecko_november.py --batch 1
```

Run all configured batches:

```bash
python3 src/download_coingecko_november.py
```

Optional arguments:

```text
--batch   Select a batch from 1 to 24
--limit   Limit the number of pools processed in a batch
--delay   Delay between requests in seconds
```

The downloader validates results and records successful, empty, unavailable, and failed requests separately.

## Tests

Run the test suite from the repository root:

```bash
pytest -q
```

The tests cover scanner behaviour, token-age validation, opportunity scoring, RugCheck handling, paper-trading logic, launch detection, and staged exits.

## Research principles

The project aims to preserve reliable historical research:

- Keep both passing and failing token observations where possible.
- Preserve original collection records and source information.
- Avoid silently substituting one time window for another.
- Validate timestamps, candle structure, and duplicate records.
- Distinguish missing data from a valid empty result.
- Avoid look-ahead bias when constructing historical tests.
- Avoid survivorship bias by retaining failed and unavailable observations.
- Keep data-provider datasets separate when comparing sources.

Do not delete or overwrite research datasets without first checking their provenance and whether they are needed for reproducibility.

## Current project status

DEGEN-BOT is a research and paper-trading project. Scanner, risk checks, opportunity scoring, simulated position management, historical backtesting, and launch-data collection are implemented.

Strategy performance still requires further validation against sufficiently broad, clean, and independently audited historical datasets.

## Disclaimer

Solana meme coins are highly speculative and can lose most or all of their value. Liquidity, volume, token age, and automated risk reports can be incomplete, manipulated, or delayed.

This project is intended for software development, market research, and paper-trading experimentation. It does not guarantee safety, returns, or execution quality.
