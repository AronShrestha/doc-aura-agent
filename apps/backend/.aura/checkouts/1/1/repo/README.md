# NEPSE Analysis Dashboard

A toolkit for scraping, analyzing, and visualizing Nepal Stock Exchange (NEPSE) data — floorsheet transactions, company fundamentals, price history, and broker activity.

## Features

- **Floorsheet Scraping** — Fetches daily floorsheet data (buyer/seller broker, quantity, rate) from NepseAlpha
- **Company Scraping** — Pulls fundamental data (EPS, P/E, Book Value, Market Cap, etc.) from MeroLagani
- **Price History** — Downloads OHLC + volume data from NepseAlpha
- **Broker Analysis** — Net holdings, cumulative positions, daily volume, and smart-money detection per broker
- **Valuation Tool** — Z-score normalization across sectors, composite scoring, and peer comparison
- **LLM Prompt Builder** — Auto-generates detailed stock analysis prompts with all available data baked in
- **Interactive Dashboard** — Streamlit app with charts (Plotly), scrape controls, and per-stock deep dives

## Setup

```bash
pip install -r requirements.txt
```

> `scrape_price_history.py` also requires `curl_cffi` — install it separately if needed:
> ```bash
> pip install curl_cffi
> ```

## Running the Dashboard

```bash
streamlit run dashboard.py
```

This starts the Streamlit app at `http://localhost:8501`.

## Running Scrapers Standalone

```bash
# Scrape floorsheet data for a symbol
python scrape_floorsheet.py

# Scrape company fundamentals
python scrape_company.py

# Fetch price history
python scrape_price_history.py SYMBOL --token TOKEN --session SESSION --cf CF
```

## Project Structure

```
dashboard.py             # Streamlit web app
analysis.py              # Core analysis functions
valuation.py             # Sector-normalized valuation scoring
scrape_floorsheet.py     # Floorsheet scraper (NepseAlpha)
scrape_company.py        # Company details scraper (MeroLagani)
scrape_price_history.py  # OHLC price history fetcher
analyze_stocks.py        # Matplotlib-based stock analysis
floorsheets/             # Scraped floorsheet CSVs (per symbol/date)
price_history/           # Scraped OHLC CSVs (per symbol)
```
