"""Fetch OHLC price history from NepseAlpha and save as CSV.

Uses curl_cffi to impersonate Chrome's TLS fingerprint, which is required
to pass Cloudflare's bot protection on nepsealpha.com.

Usage (CLI):
    python scrape_price_history.py SYMBOL --token TOKEN --session SESSION --cf CF

Usage (import):
    from scrape_price_history import fetch_price_history
    df = fetch_price_history("PPCL", token=..., session_cookie=..., cf_clearance=...)
"""

import argparse
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
from curl_cffi import requests as cffi_requests

PRICE_HISTORY_DIR = Path("price_history")

NEPSEALPHA_URL = "https://nepsealpha.com/nepse-data"

DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.8",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://nepsealpha.com",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Brave";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "x-requested-with": "XMLHttpRequest",
}


def fetch_price_history(
    symbol,
    start_date="2021-01-01",
    end_date="2026-02-15",
    token="",
    session_cookie="",
    cf_clearance="",
):
    """Fetch OHLC price history for *symbol* from NepseAlpha.

    Args:
        symbol: Stock ticker (e.g. "PPCL").
        start_date: Start date string "YYYY-MM-DD".
        end_date: End date string "YYYY-MM-DD".
        token: CSRF ``_token`` from NepseAlpha.
        session_cookie: ``nepsealpha_session`` cookie value.
        cf_clearance: ``cf_clearance`` cookie value.

    Returns:
        DataFrame with columns:
            date, open, high, low, close, volume, turnover, percent_change
        Sorted by date ascending.  Also saved to ``price_history/{SYMBOL}.csv``.
    """
    headers = {**DEFAULT_HEADERS, "referer": f"https://nepsealpha.com/search?q={symbol}"}

    # Build cookie header as raw string
    cookie_parts = []
    if session_cookie:
        cookie_parts.append(f"nepsealpha_session={session_cookie}")
    if cf_clearance:
        cookie_parts.append(f"cf_clearance={cf_clearance}")
    if cookie_parts:
        headers["cookie"] = "; ".join(cookie_parts)

    form_data = urlencode({
        "symbol": symbol,
        "specific_date": end_date,
        "start_date": start_date,
        "end_date": end_date,
        "filter_type": "date-range",
        "price_type": "unadjusted",
        "time_frame": "daily",
        "_token": token,
    })

    # Use curl_cffi with Chrome impersonation to bypass Cloudflare
    response = cffi_requests.post(
        NEPSEALPHA_URL,
        headers=headers,
        data=form_data,
        impersonate="chrome",
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    items = payload.get("data", payload) if isinstance(payload, dict) else payload

    if not items:
        return pd.DataFrame(columns=[
            "date", "open", "high", "low", "close", "volume", "turnover", "percent_change",
        ])

    def _float(val, default=0.0):
        """Safely convert to float, returning default for None/empty."""
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    records = []
    for item in items:
        if not item.get("f_date"):
            continue
        records.append({
            "date": item["f_date"],
            "open": _float(item.get("open")),
            "high": _float(item.get("high")),
            "low": _float(item.get("low")),
            "close": _float(item.get("close")),
            "volume": int(_float(item.get("volume"))),
            "turnover": _float(item.get("turnover")),
            "percent_change": _float(item.get("percent_change")),
        })

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Drop today's row if present — EOD data may not be final yet
    from datetime import date as _date

    today = pd.Timestamp(_date.today())
    df = df[df["date"] != today].reset_index(drop=True)

    # Save to CSV
    PRICE_HISTORY_DIR.mkdir(exist_ok=True)
    csv_path = PRICE_HISTORY_DIR / f"{symbol}.csv"
    df.to_csv(csv_path, index=False)

    return df


def main():
    parser = argparse.ArgumentParser(description="Fetch price history from NepseAlpha")
    parser.add_argument("symbol", help="Stock symbol (e.g. PPCL)")
    parser.add_argument("--token", required=True, help="CSRF _token")
    parser.add_argument("--session", required=True, help="nepsealpha_session cookie")
    parser.add_argument("--cf", default="", help="cf_clearance cookie")
    parser.add_argument("--start", default="2021-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-02-15", help="End date YYYY-MM-DD")
    args = parser.parse_args()

    print(f"Fetching price history for {args.symbol}...")
    df = fetch_price_history(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        token=args.token,
        session_cookie=args.session,
        cf_clearance=args.cf,
    )
    print(f"Done! {len(df)} records saved to price_history/{args.symbol}.csv")


if __name__ == "__main__":
    main()
