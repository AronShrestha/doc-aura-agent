import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Defaults for CLI usage
DEFAULT_MAX_WORKERS = 8
DEFAULT_SLEEP_TIME = 2  # secs
DEFAULT_SYMBOL = "BHPL"
DEFAULT_START_DATE = datetime(2023, 2, 14)
DEFAULT_END_DATE = datetime(2026, 2, 12)

FSK = "GPvhNaI3jPIN40Ci"

COLUMNS = ["Contract Number", "Buyer Broker", "Seller Broker", "Quantity", "Rate", "Amount"]


def _make_headers(symbol):
    return {
        "sec-ch-ua-platform": '"macOS"',
        "Referer": f"https://nepsealpha.com/search?q={symbol}",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
        "sec-ch-ua-mobile": "?0",
    }


def _save_empty_csv(date_str, output_dir):
    """Save a CSV with only headers so we don't re-fetch this date.

    Skips saving if *date_str* is today — EOD data may not be available yet.
    """
    from datetime import date as _date

    if date_str == _date.today().isoformat():
        return
    csv_path = os.path.join(output_dir, f"{date_str}.csv")
    pd.DataFrame(columns=COLUMNS).to_csv(csv_path, index=False)


def fetch_floorsheet(date_str, symbol, sleep_time, output_dir):
    """Fetch and parse floorsheet for a single date.

    Returns:
        (date_str, status_string) tuple
    """
    base_url = f"https://nepsealpha.com/floorsheet_ajx/{symbol}/index"
    headers = _make_headers(symbol)

    try:
        params = {
            "fsk": FSK,
            "date": date_str,
            "fromInfo": "1",
        }
        import random

        time.sleep(random.randint(1, sleep_time))

        response = requests.get(base_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        html = data.get("html", "")

        if not html:
            _save_empty_csv(date_str, output_dir)
            return date_str, "skipped"

        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "overall-floorsheet-table"})

        if not table:
            _save_empty_csv(date_str, output_dir)
            return date_str, "skipped"

        tbody = table.find("tbody")
        if not tbody:
            _save_empty_csv(date_str, output_dir)
            return date_str, "skipped"

        rows = tbody.find_all("tr")
        if not rows:
            _save_empty_csv(date_str, output_dir)
            return date_str, "skipped"

        all_rows = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 6:
                rate = cols[4].text.strip().replace("NPR ", "").replace(",", "")
                amount = cols[5].text.strip().replace("NPR ", "").replace(",", "")
                all_rows.append({
                    "Contract Number": cols[0].text.strip(),
                    "Buyer Broker": cols[1].text.strip(),
                    "Seller Broker": cols[2].text.strip(),
                    "Quantity": cols[3].text.strip(),
                    "Rate": rate,
                    "Amount": amount,
                })

        if not all_rows:
            _save_empty_csv(date_str, output_dir)
            return date_str, "skipped"

        df = pd.DataFrame(all_rows)
        csv_path = os.path.join(output_dir, f"{date_str}.csv")
        df.to_csv(csv_path, index=False)

        return date_str, f"saved ({len(all_rows)} rows)"

    except Exception as e:
        return date_str, f"error: {e}"


def generate_dates(start, end):
    """Generate all dates between start and end (inclusive), skipping weekends."""
    dates = []
    current = start
    while current <= end:
        # Skip Saturday (5) and Sunday (6)
        if current.weekday() < 5:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def run_scrape(symbol, max_workers=DEFAULT_MAX_WORKERS, sleep_time=DEFAULT_SLEEP_TIME,
               start_date=None, end_date=None, progress_callback=None):
    """Run the full scrape for a symbol.

    Args:
        symbol: Stock symbol to scrape (e.g. "BHPL")
        max_workers: Number of concurrent threads
        sleep_time: Seconds to sleep between requests
        start_date: Start date (datetime). Defaults to 2023-02-14.
        end_date: End date (datetime). Defaults to today.
        progress_callback: Optional callable(completed, total, stats_dict)
            called after each date finishes. stats_dict has keys:
            "saved", "skipped", "errors", "error_dates".

    Returns:
        dict with keys: "saved", "skipped", "errors", "error_dates"
    """
    if start_date is None:
        start_date = DEFAULT_START_DATE
    if end_date is None:
        end_date = datetime.now()

    output_dir = f"floorsheets/{symbol}"
    os.makedirs(output_dir, exist_ok=True)

    dates = generate_dates(start_date, end_date)

    # Skip dates that already have CSV files
    existing = set()
    if os.path.isdir(output_dir):
        for f in os.listdir(output_dir):
            if f.endswith(".csv"):
                existing.add(f.replace(".csv", ""))

    dates_to_fetch = [d for d in dates if d not in existing]

    if not dates_to_fetch:
        return {"saved": 0, "skipped": 0, "errors": 0, "error_dates": [],
                "total": 0, "already_existed": len(existing)}

    lock = threading.Lock()
    stats = {"saved": 0, "skipped": 0, "errors": 0, "error_dates": []}
    completed = 0
    total = len(dates_to_fetch)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_date = {
            executor.submit(fetch_floorsheet, date, symbol, sleep_time, output_dir): date
            for date in dates_to_fetch
        }

        for future in as_completed(future_to_date):
            date_str, result = future.result()

            with lock:
                if result.startswith("saved"):
                    stats["saved"] += 1
                elif result.startswith("skipped"):
                    stats["skipped"] += 1
                elif result.startswith("error"):
                    stats["errors"] += 1
                    stats["error_dates"].append(date_str)

                completed += 1
                current_stats = dict(stats)

            if progress_callback:
                progress_callback(completed, total, current_stats)

    stats["total"] = total
    stats["already_existed"] = len(existing)
    return stats


def main():
    symbol = DEFAULT_SYMBOL
    start_date = DEFAULT_START_DATE
    end_date = DEFAULT_END_DATE
    max_workers = DEFAULT_MAX_WORKERS
    sleep_time = DEFAULT_SLEEP_TIME

    output_dir = f"floorsheets/{symbol}"
    dates = generate_dates(start_date, end_date)
    total = len(dates)
    print(f"Fetching floorsheet data for {symbol}")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Total weekdays to fetch: {total}")
    print(f"Output directory: {output_dir}/")
    print("-" * 60)

    def print_progress(completed, total, stats):
        if completed % 20 == 0 or completed == total:
            print(
                f"[{completed}/{total}] "
                f"Saved: {stats['saved']} | "
                f"Skipped (no data): {stats['skipped']} | "
                f"Errors: {stats['errors']}"
            )

    result = run_scrape(symbol, max_workers, sleep_time, start_date, end_date,
                        progress_callback=print_progress)

    print()
    print("=" * 60)
    print(f"DONE! Saved: {result['saved']} | Skipped: {result['skipped']} | Errors: {result['errors']}")
    print(f"CSV files saved to: {output_dir}/")


if __name__ == "__main__":
    main()
