"""Scrape company details from merolagani.com.

Refactored from the original 'scrape company.py' into importable functions.

Usage (CLI):
    python scrape_company.py

Usage (import):
    from scrape_company import scrape_all_companies
    df = scrape_all_companies(progress_callback=my_cb)
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import pandas as pd
import threading
import re

HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "priority": "u=1, i",
    "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
    "cookie": "ASP.NET_SessionId=ktyzuodwdumjk4fnkt5sfugt",
    "Referer": "https://merolagani.com/LatestMarket.aspx",
}

# Columns we attempt to convert to float after cleaning
NUMERIC_COLUMNS = [
    "Market Price", "% Change", "180 Day Average", "120 Day Average",
    "EPS", "P/E Ratio", "Book Value", "PBV",
    "30-Day Avg Volume", "Market Capitalization", "Shares Outstanding",
]


def _clean_value(val):
    """Strip HTML cruft, whitespace, and common formatting from a scraped value."""
    if not isinstance(val, str):
        return val
    # Remove \r\n and everything after (fiscal year annotations etc.)
    val = re.split(r"[\r\n]", val)[0].strip()
    # Remove % suffix for Change column
    val = val.rstrip("%").strip()
    # Remove commas from numbers
    val = val.replace(",", "")
    return val


def _clean_dataframe(df):
    """Clean a raw company-details DataFrame: strip values, convert numerics."""
    df = df.copy()
    # Clean all string columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(_clean_value)

    # Convert numeric columns
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def fetch_company_list():
    """Fetch the list of company codes and names from merolagani.

    Returns:
        list[dict] – each dict has keys ``code`` and ``name``.
        Example: [{"code": "ADBL", "name": "Agriculture Development Bank Limited"}, ...]
    """
    data = {"value": "", "sector": "0"}
    response = requests.post(
        "https://merolagani.com/handlers/AutoSuggestHandler.ashx?type=Company",
        headers=HEADERS,
        data=data,
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()

    companies = []
    items = result if isinstance(result, list) else result.get("d", [])
    for item in items:
        if isinstance(item, dict):
            code = item.get("d", "")
            label = item.get("l", "")
            # label format: "CODE (Full Name)" – extract the name
            name = label.split("(", 1)[1].rstrip(")").strip() if "(" in label else ""
            companies.append({"code": code, "name": name})
        else:
            # Fallback: item is just a string code
            companies.append({"code": str(item), "name": ""})
    return companies


def scrape_company(code):
    """Scrape details for a single company.

    Returns:
        dict with company details, or None on failure.
    """
    try:
        r = requests.get(
            f"https://merolagani.com/CompanyDetail.aspx?symbol={code}",
            timeout=15,
        )

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", {"id": "accordion"})

        if not table:
            return None

        company_detail = {"code": code}

        for row in table.find_all("tr"):
            header = row.find("th")
            if not header:
                continue

            header = header.text.strip()

            if value := row.find("td"):
                value = value.text.strip()

            if not value:
                continue

            company_detail[header] = value

        return company_detail

    except Exception:
        return None


def scrape_all_companies(max_workers=20, progress_callback=None):
    """Scrape details for all listed companies.

    Args:
        max_workers: Number of concurrent threads.
        progress_callback: Optional callable(completed, total) called after
            each company finishes.

    Returns:
        Cleaned pandas DataFrame with company details.
        Also saves to 'company_details.csv'.
    """
    companies = fetch_company_list()
    total = len(companies)

    # Build a code -> name lookup
    name_map = {c["code"]: c["name"] for c in companies}
    codes = [c["code"] for c in companies]

    results = []
    lock = threading.Lock()
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(scrape_company, code): code
            for code in codes
        }

        for future in as_completed(future_to_code):
            result = future.result()
            with lock:
                if result:
                    # Inject the company name from the API
                    result["Company Name"] = name_map.get(result["code"], "")
                    results.append(result)
                completed += 1

            if progress_callback:
                progress_callback(completed, total)

    df = pd.DataFrame(results)
    df = _clean_dataframe(df)

    # Put Company Name right after code
    if "Company Name" in df.columns:
        cols = ["code", "Company Name"] + [c for c in df.columns if c not in ("code", "Company Name")]
        df = df[cols]

    # Filter out rows without Shares Outstanding, zero Market Cap, or zero 30-Day Avg Volume
    df = df[
        df["Shares Outstanding"].notna()
        & (df["Market Capitalization"].fillna(0) > 0)
        & (df["30-Day Avg Volume"].fillna(0) > 0)
    ].reset_index(drop=True)

    df.to_csv("company_details.csv", index=False)
    return df


def main():
    print("Fetching company list...")
    companies = fetch_company_list()
    print(f"Total companies: {len(companies)}")

    print("Scraping company details with 20 threads...")

    def print_progress(completed, total):
        if completed % 10 == 0 or completed == total:
            print(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")

    df = scrape_all_companies(max_workers=20, progress_callback=print_progress)

    print(f"\nDone! {len(df)} companies saved to company_details.csv")


if __name__ == "__main__":
    main()
