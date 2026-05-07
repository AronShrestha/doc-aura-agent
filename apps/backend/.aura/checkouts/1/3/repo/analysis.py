"""Reusable analysis functions for NEPSE floorsheet data.

Extracted from analyze_floorsheet.ipynb so the Streamlit dashboard (and any
other consumer) can import them without duplicating logic.
"""

import pandas as pd
from pathlib import Path


FLOORSHEET_BASE_DIR = Path("floorsheets")


def load_floorsheet_data(symbol):
    """Load all per-date CSVs for *symbol* and build buying / selling DataFrames.

    Returns:
        dict with keys:
            "buying_df"      – DataFrame (Date, Broker, Total_Quantity, Avg_Price, Total_Amount)
            "selling_df"     – same schema
            "total_csvs"     – int, number of CSV files found
            "dates_with_data"– int
            "dates_skipped"  – int
    """
    floorsheet_dir = FLOORSHEET_BASE_DIR / symbol
    csv_files = sorted(floorsheet_dir.glob("*.csv"))

    buying_records = []
    selling_records = []
    skipped = 0

    for csv_file in csv_files:
        date_str = csv_file.stem  # e.g. '2023-02-14'
        df = pd.read_csv(csv_file)

        if df.empty:
            skipped += 1
            continue

        # --- Buying side ---
        buy_group = df.groupby("Buyer Broker").agg(
            Total_Quantity=("Quantity", "sum"),
            Total_Amount=("Amount", "sum"),
        ).reset_index()
        buy_group["Avg_Price"] = buy_group["Total_Amount"] / buy_group["Total_Quantity"]
        buy_group["Date"] = date_str
        buy_group.rename(columns={"Buyer Broker": "Broker"}, inplace=True)
        buying_records.append(buy_group)

        # --- Selling side ---
        sell_group = df.groupby("Seller Broker").agg(
            Total_Quantity=("Quantity", "sum"),
            Total_Amount=("Amount", "sum"),
        ).reset_index()
        sell_group["Avg_Price"] = sell_group["Total_Amount"] / sell_group["Total_Quantity"]
        sell_group["Date"] = date_str
        sell_group.rename(columns={"Seller Broker": "Broker"}, inplace=True)
        selling_records.append(sell_group)

    if not buying_records:
        empty = pd.DataFrame(columns=["Date", "Broker", "Total_Quantity", "Avg_Price", "Total_Amount"])
        return {
            "buying_df": empty,
            "selling_df": empty,
            "total_csvs": len(csv_files),
            "dates_with_data": 0,
            "dates_skipped": skipped,
        }

    buying_df = pd.concat(buying_records, ignore_index=True)
    selling_df = pd.concat(selling_records, ignore_index=True)

    col_order = ["Date", "Broker", "Total_Quantity", "Avg_Price", "Total_Amount"]
    buying_df = buying_df[col_order]
    selling_df = selling_df[col_order]

    return {
        "buying_df": buying_df,
        "selling_df": selling_df,
        "total_csvs": len(csv_files),
        "dates_with_data": len(csv_files) - skipped,
        "dates_skipped": skipped,
    }


def compute_net_holdings(buying_df, selling_df):
    """Compute net holdings per broker (bought - sold) across all dates.

    Returns:
        DataFrame with columns:
            Broker, Net_Quantity, Total_Bought, Avg_Buy_Price,
            Total_Sold, Avg_Sell_Price
        Sorted by Net_Quantity descending.
    """
    buy_agg = buying_df.groupby("Broker").agg(
        Total_Bought=("Total_Quantity", "sum"),
        Buy_Amount=("Total_Amount", "sum"),
    )
    sell_agg = selling_df.groupby("Broker").agg(
        Total_Sold=("Total_Quantity", "sum"),
        Sell_Amount=("Total_Amount", "sum"),
    )

    all_brokers = sorted(set(buy_agg.index) | set(sell_agg.index))
    rows = []
    for b in all_brokers:
        bought = buy_agg.loc[b, "Total_Bought"] if b in buy_agg.index else 0
        buy_amt = buy_agg.loc[b, "Buy_Amount"] if b in buy_agg.index else 0
        sold = sell_agg.loc[b, "Total_Sold"] if b in sell_agg.index else 0
        sell_amt = sell_agg.loc[b, "Sell_Amount"] if b in sell_agg.index else 0
        rows.append({
            "Broker": b,
            "Net_Quantity": bought - sold,
            "Total_Bought": bought,
            "Avg_Buy_Price": buy_amt / bought if bought else 0,
            "Total_Sold": sold,
            "Avg_Sell_Price": sell_amt / sold if sold else 0,
        })

    net_df = pd.DataFrame(rows)
    net_df = net_df.sort_values("Net_Quantity", ascending=False).reset_index(drop=True)
    return net_df


def _build_aligned_pivots(buying_df, selling_df):
    """Internal helper: build buy_pivot and sell_pivot aligned on dates & brokers."""
    bdf = buying_df.copy()
    sdf = selling_df.copy()
    bdf["Date"] = pd.to_datetime(bdf["Date"])
    sdf["Date"] = pd.to_datetime(sdf["Date"])

    buy_pivot = bdf.pivot_table(
        index="Date", columns="Broker", values="Total_Quantity",
        aggfunc="sum", fill_value=0,
    )
    sell_pivot = sdf.pivot_table(
        index="Date", columns="Broker", values="Total_Quantity",
        aggfunc="sum", fill_value=0,
    )

    # Align columns
    all_broker_cols = sorted(set(buy_pivot.columns) | set(sell_pivot.columns))
    buy_pivot = buy_pivot.reindex(columns=all_broker_cols, fill_value=0)
    sell_pivot = sell_pivot.reindex(columns=all_broker_cols, fill_value=0)

    # Align dates
    all_dates = sorted(set(buy_pivot.index) | set(sell_pivot.index))
    buy_pivot = buy_pivot.reindex(all_dates, fill_value=0)
    sell_pivot = sell_pivot.reindex(all_dates, fill_value=0)

    return buy_pivot, sell_pivot


def compute_cumulative_net(buying_df, selling_df):
    """Compute cumulative net quantity per broker over time.

    Returns:
        DataFrame indexed by Date, columns = Broker, values = cumulative net qty.
    """
    buy_pivot, sell_pivot = _build_aligned_pivots(buying_df, selling_df)
    daily_net = buy_pivot - sell_pivot
    return daily_net.cumsum()


def compute_daily_volume(buying_df, selling_df):
    """Compute daily volume (buy + sell) per broker.

    Returns:
        DataFrame indexed by Date, columns = Broker, values = daily volume.
    """
    buy_pivot, sell_pivot = _build_aligned_pivots(buying_df, selling_df)
    return buy_pivot + sell_pivot


def compute_daily_net(buying_df, selling_df):
    """Compute daily (non-cumulative) net quantity per broker.

    Returns:
        DataFrame indexed by Date, columns = Broker, values = daily net qty.
    """
    buy_pivot, sell_pivot = _build_aligned_pivots(buying_df, selling_df)
    return buy_pivot - sell_pivot


def compute_daily_prices(buying_df, selling_df):
    """Build daily avg-price pivots for buy and sell sides.

    Returns:
        (buy_price_pivot, sell_price_pivot) – DataFrames indexed by Date,
        columns = Broker, values = weighted avg price.  NaN where the broker
        had no activity on that date (so the tooltip can show "--").
    """
    bdf = buying_df.copy()
    sdf = selling_df.copy()
    bdf["Date"] = pd.to_datetime(bdf["Date"])
    sdf["Date"] = pd.to_datetime(sdf["Date"])

    buy_price = bdf.pivot_table(
        index="Date", columns="Broker", values="Avg_Price",
        aggfunc="mean",  # already weighted per-day in load_floorsheet_data
    )
    sell_price = sdf.pivot_table(
        index="Date", columns="Broker", values="Avg_Price",
        aggfunc="mean",
    )

    # Align columns
    all_broker_cols = sorted(set(buy_price.columns) | set(sell_price.columns))
    buy_price = buy_price.reindex(columns=all_broker_cols)
    sell_price = sell_price.reindex(columns=all_broker_cols)

    # Align dates
    all_dates = sorted(set(buy_price.index) | set(sell_price.index))
    buy_price = buy_price.reindex(all_dates)
    sell_price = sell_price.reindex(all_dates)

    return buy_price, sell_price


def build_daily_broker_summary(buying_df, selling_df):
    """Per-date, per-broker summary with buy (+) and sell (-) quantities and avg prices.

    Returns:
        DataFrame with columns:
            Date, Broker, Bought_Qty (positive), Bought_Avg_Price,
            Sold_Qty (negative), Sold_Avg_Price, Net_Qty
        Sorted by Date then Broker.
    """
    bdf = buying_df.rename(columns={
        "Total_Quantity": "Bought_Qty",
        "Avg_Price": "Bought_Avg_Price",
        "Total_Amount": "Bought_Amount",
    })
    sdf = selling_df.rename(columns={
        "Total_Quantity": "Sold_Qty",
        "Avg_Price": "Sold_Avg_Price",
        "Total_Amount": "Sold_Amount",
    })

    merged = pd.merge(
        bdf[["Date", "Broker", "Bought_Qty", "Bought_Avg_Price"]],
        sdf[["Date", "Broker", "Sold_Qty", "Sold_Avg_Price"]],
        on=["Date", "Broker"],
        how="outer",
    ).fillna(0)

    # Sign convention: buys positive, sells negative
    merged["Sold_Qty"] = -merged["Sold_Qty"].abs()
    merged["Net_Qty"] = merged["Bought_Qty"] + merged["Sold_Qty"]

    merged["Date"] = pd.to_datetime(merged["Date"])
    return merged.sort_values(["Date", "Broker"]).reset_index(drop=True)


def load_company_data():
    """Load company details from company_details.csv.

    Returns:
        DataFrame with cleaned company data, or None if file doesn't exist.
    """
    csv_path = Path("company_details.csv")
    if not csv_path.is_file():
        return None
    df = pd.read_csv(csv_path)

    # Clean in case the CSV was generated by the old script
    from scrape_company import _clean_dataframe
    df = _clean_dataframe(df)

    # Computed column: Price / Shares Outstanding ratio
    if "Market Price" in df.columns and "Shares Outstanding" in df.columns:
        df["Price/Share Ratio"] = df["Market Price"] / df["Shares Outstanding"]

    return df


def get_company_info(symbol):
    """Get a single company's info from the company_details CSV.

    Returns:
        dict of column->value, or None if not found.
    """
    df = load_company_data()
    if df is None:
        return None
    row = df[df["code"] == symbol]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def build_stock_markdown(symbol):
    """Build a self-contained LLM prompt with all available data for *symbol*.

    Returns:
        str – a markdown/text prompt ready to paste into any LLM.
    """
    import numpy as np

    lines = []

    def _v(val, fmt=None):
        """Format a value for display, returning 'N/A' for missing."""
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "N/A"
        if fmt and isinstance(val, (int, float)):
            return fmt.format(val)
        return str(val)

    # ── ROLE & CONTEXT ─────────────────────────────────────────────────
    lines.append("# ROLE: Expert NEPSE Stock Analyzer\n")
    lines.append(
        "You are analyzing a stock in the Nepal Stock Exchange (NEPSE), a complex "
        "frontier market characterized by high sector concentration (BFII sector "
        "historically >90% of turnover), limited liquidity, and a documented "
        "**unidirectional causal link** from NRB monetary policy to the index. "
        "Psychological momentum and regulatory intervention are the primary movers; "
        "fundamentals set the floor for valuations, technical and microstructure "
        "(floorsheet) analysis set the ceiling for predictive accuracy.\n"
    )

    lines.append("# MISSION\n")
    lines.append(
        "Synthesize the company fundamentals, floorsheet broker data, and sector "
        "comparison below to provide a predictive investment outlook. Be **concise "
        "but detailed and direct**; explain your reasoning when it matters.\n"
    )
    lines.append("---\n")

    # ── SECTION 1: MACRO-POLITICAL & POLICY ─────────────────────────────
    lines.append("# SECTION 1: MACRO-POLITICAL & POLICY ANALYSIS\n")
    lines.append(
        "Consider the following regulatory dynamics (use your external knowledge "
        "if available):\n\n"
        "- **NRB Policy**: The 91-day T-bill rate and interbank rate are lead "
        "indicators for NEPSE. High rates draw liquidity away from equity. Assess "
        "the current interest-rate cycle and liquidity (CD Ratio); if rates are "
        "decreasing, calculate the valuation-expansion potential for this sector.\n"
        "- **Margin Lending Rules (4/12 → 15/20)**: Tightening margin caps (e.g. "
        "4/12 rule: 40M per bank / 120M total) caused the index to fall from 3198 "
        "to 1818. Relaxations historically trigger rallies. Assess if current caps "
        "restrict big-player movement in this stock.\n"
        "- **Minister–Market Matrix**: FM appointments drive multi-month sentiment "
        "(e.g. Paudel = pro-market / bullish; Khatiwada = conservative / bearish). "
        "No technical signal is valid if it contradicts a major NRB policy shift.\n"
    )
    lines.append("---\n")

    # ── SECTION 2: FUNDAMENTAL DEEP-DIVE ────────────────────────────────
    lines.append("# SECTION 2: FUNDAMENTAL DEEP-DIVE (Value Filter)\n")
    lines.append(
        "Analyze the company fundamentals data below using these Nepal-specific "
        "filters:\n\n"
        "- **Banking/Financial**: ~97% of commercial bank MPS variation is explained "
        "by EPS, DPS, and BVPS. EPS and P/E are the most potent predictors. ROE "
        "measures management efficiency. Track NPL trend — if NPL is rising while "
        "price is rising, flag as **Sentiment-Driven Bubble**. Calculate true "
        "dividend capacity (distributable profit after mandatory regulatory reserves).\n"
        "- **Hydropower**: Plant Load Factor (PLF) over installed MW. PPA type and "
        "rates (NEA wet ~4.80/unit vs dry ~8.40/unit). Debt-to-Equity ratio (high "
        "leverage = interest-rate sensitivity). Cost per MW (135M–315M NPR). Flag "
        "founder-share conversion post-lock-in as structural risk.\n"
        "- **General**: P/E in NEPSE can exceed 40 in bull runs, often preceding "
        "sharp corrections. Dividend/bonus expectations are the #1 fundamental "
        "driver, not absolute EPS. 26% of NEPSE companies are loss-making yet trade "
        "at high prices due to manipulation.\n"
    )
    lines.append("---\n")

    # ── SECTION 3: FLOORSHEET BEHAVIORAL FORENSICS ──────────────────────
    lines.append("# SECTION 3: FLOORSHEET BEHAVIORAL FORENSICS (The Broker Game)\n")
    lines.append(
        "Use the floorsheet data below to uncover smart money. This is THE primary "
        "analysis tool — more important than fundamentals or technicals.\n\n"
        "- **Broker Concentration Ratio**: Total Buy Volume of Top 3 Brokers / Total "
        "Volume. If >60%, institutional accumulation is likely.\n"
        "- **The Big 5**: Track Brokers 58, 34, 45, 44, 57 specifically. Are they "
        "performing stealth buying (many small orders) or aggressive sweeping (large "
        "block trades)?\n"
        "- **Operators Pool**: If the same brokers who bought the bottom 1-2 years "
        "ago are accumulating again near a demand zone, this is a high-probability "
        "bullish signal.\n"
        "- **Matching/Circular Trading**: Detect if Broker A is selling to Broker B "
        "repeatedly at the same price — signals manipulation via wash trading.\n"
        "- **Retail vs Smart Money**: Is a known smart-money broker buying from a "
        "retail-heavy broker? This confirms transfer of strength.\n"
        "- **4-Phase Operator Cycle**: (1) ACCUMULATION — silent buying 3-12 months, "
        "low volume; (2) MARKUP — rally 2-6 weeks, volume surging; (3) DISTRIBUTION "
        "— choppy top with extremely high volume but price stalling; (4) MARKDOWN — "
        "decline 40-70%, operators absent.\n"
        "- **Red Flags**: Sudden spikes on low volume; repetitive broker ID matching; "
        "price rising while RSI/MACD falls (hidden distribution); parabolic rallies "
        "(3+ days of 7-10% gains).\n"
    )
    lines.append("---\n")

    # ── Company fundamentals ─────────────────────────────────────────────
    info = get_company_info(symbol)

    lines.append("## COMPANY FUNDAMENTALS\n")
    if info:
        lines.append(f"- Symbol: {info.get('code', symbol)}")
        lines.append(f"- Company Name: {_v(info.get('Company Name'))}")
        lines.append(f"- Sector: {_v(info.get('Sector'))}")
        lines.append(f"- Last Traded On: {_v(info.get('Last Traded On'))}")
        lines.append(f"- Market Price (NPR): {_v(info.get('Market Price'), '{:,.2f}')}")
        lines.append(f"- % Change (Last Day): {_v(info.get('% Change'), '{:.2f}')}")
        lines.append(f"- 52 Week High-Low: {_v(info.get('52 Weeks High - Low'))}")
        lines.append(f"- 180 Day Average Price: {_v(info.get('180 Day Average'), '{:,.2f}')}")
        lines.append(f"- 120 Day Average Price: {_v(info.get('120 Day Average'), '{:,.2f}')}")
        lines.append(f"- 1 Year Yield: {_v(info.get('1 Year Yield'))}")
        lines.append(f"- Earnings Per Share (EPS): {_v(info.get('EPS'), '{:.2f}')}")
        lines.append(f"- Price to Earnings Ratio (P/E): {_v(info.get('P/E Ratio'), '{:.2f}')}")
        lines.append(f"- Book Value Per Share: {_v(info.get('Book Value'), '{:.2f}')}")
        lines.append(f"- Price to Book Value (PBV): {_v(info.get('PBV'), '{:.2f}')}")
        lines.append(f"- Market Capitalization (NPR): {_v(info.get('Market Capitalization'), '{:,.0f}')}")
        lines.append(f"- Total Shares Outstanding: {_v(info.get('Shares Outstanding'), '{:,.0f}')}")
        lines.append(f"- 30-Day Average Volume: {_v(info.get('30-Day Avg Volume'), '{:,.0f}')}")
        lines.append(f"- Dividend (%): {_v(info.get('% Dividend'))}")
        lines.append(f"- Bonus (%): {_v(info.get('% Bonus'))}")
        lines.append(f"- Right Share: {_v(info.get('Right Share'))}")
    else:
        lines.append("No company fundamental data available.\n")
    lines.append("")
    lines.append("---\n")

    # ── Floorsheet data ──────────────────────────────────────────────────
    floorsheet_dir = FLOORSHEET_BASE_DIR / symbol
    has_floorsheet = (
        floorsheet_dir.is_dir()
        and any(floorsheet_dir.glob("*.csv"))
    )

    if not has_floorsheet:
        lines.append("## FLOORSHEET DATA\n")
        lines.append("No floorsheet data available for this stock.\n")
        lines.append("---\n")
        _append_sector_comparison(lines, symbol, info, _v)
        _append_analysis_request(lines)
        return "\n".join(lines)

    data = load_floorsheet_data(symbol)
    buying_df = data["buying_df"]
    selling_df = data["selling_df"]

    if buying_df.empty:
        lines.append("## FLOORSHEET DATA\n")
        lines.append("Floorsheet files exist but contain no transaction data.\n")
        lines.append("---\n")
        _append_sector_comparison(lines, symbol, info, _v)
        _append_analysis_request(lines)
        return "\n".join(lines)

    # Date range
    all_dates = sorted(pd.to_datetime(buying_df["Date"].unique()))
    earliest = all_dates[0].strftime("%Y-%m-%d")
    latest = all_dates[-1].strftime("%Y-%m-%d")

    lines.append("## FLOORSHEET DATA OVERVIEW\n")
    lines.append(f"- Data Period: {earliest} to {latest}")
    lines.append(f"- Total Trading Days with Data: {data['dates_with_data']}")
    lines.append(f"- Total Buying Records: {len(buying_df):,}")
    lines.append(f"- Total Selling Records: {len(selling_df):,}")
    lines.append("")
    lines.append("---\n")

    # ── Net holdings ─────────────────────────────────────────────────────
    net_df = compute_net_holdings(buying_df, selling_df)

    # Top 15 accumulators
    top15 = net_df.head(15)
    lines.append("## ALL-TIME NET HOLDINGS BY BROKER (Top 15 Accumulators)\n")
    lines.append("Shows which brokers have accumulated the most shares over the entire data period.\n")
    lines.append("| Broker | Net Qty | Total Bought | Avg Buy Price | Total Sold | Avg Sell Price |")
    lines.append("|--------|---------|-------------|---------------|------------|----------------|")
    for _, row in top15.iterrows():
        lines.append(
            f"| {int(row['Broker'])} | {row['Net_Quantity']:,.0f} | "
            f"{row['Total_Bought']:,.0f} | {row['Avg_Buy_Price']:.2f} | "
            f"{row['Total_Sold']:,.0f} | {row['Avg_Sell_Price']:.2f} |"
        )
    lines.append("")

    # Top 15 sellers
    bottom15 = net_df.tail(15).iloc[::-1]
    lines.append("## ALL-TIME NET HOLDINGS BY BROKER (Top 15 Sellers)\n")
    lines.append("Shows which brokers have sold the most shares (net negative) over the entire data period.\n")
    lines.append("| Broker | Net Qty | Total Bought | Avg Buy Price | Total Sold | Avg Sell Price |")
    lines.append("|--------|---------|-------------|---------------|------------|----------------|")
    for _, row in bottom15.iterrows():
        lines.append(
            f"| {int(row['Broker'])} | {row['Net_Quantity']:,.0f} | "
            f"{row['Total_Bought']:,.0f} | {row['Avg_Buy_Price']:.2f} | "
            f"{row['Total_Sold']:,.0f} | {row['Avg_Sell_Price']:.2f} |"
        )
    lines.append("")
    lines.append("---\n")

    # ── Daily market summary (last 30 trading days) ──────────────────────
    summary_df = build_daily_broker_summary(buying_df, selling_df)

    # Aggregate per day across all brokers
    daily_agg = summary_df.groupby("Date").agg(
        Total_Bought=("Bought_Qty", "sum"),
        Total_Sold=("Sold_Qty", lambda x: x.abs().sum()),
        Net_Qty=("Net_Qty", "sum"),
    ).reset_index()
    daily_agg = daily_agg.sort_values("Date")

    # Compute weighted avg prices per day
    buy_day = buying_df.copy()
    buy_day["Date"] = pd.to_datetime(buy_day["Date"])
    sell_day = selling_df.copy()
    sell_day["Date"] = pd.to_datetime(sell_day["Date"])

    buy_day_agg = buy_day.groupby("Date").agg(
        Qty=("Total_Quantity", "sum"),
        Amt=("Total_Amount", "sum"),
    )
    buy_day_agg["Avg_Buy_Price"] = buy_day_agg["Amt"] / buy_day_agg["Qty"]

    sell_day_agg = sell_day.groupby("Date").agg(
        Qty=("Total_Quantity", "sum"),
        Amt=("Total_Amount", "sum"),
    )
    sell_day_agg["Avg_Sell_Price"] = sell_day_agg["Amt"] / sell_day_agg["Qty"]

    daily_agg = daily_agg.set_index("Date")
    daily_agg["Avg_Buy_Price"] = buy_day_agg["Avg_Buy_Price"]
    daily_agg["Avg_Sell_Price"] = sell_day_agg["Avg_Sell_Price"]
    daily_agg = daily_agg.fillna(0).reset_index()

    last_30 = daily_agg.tail(30)

    lines.append("## DAILY MARKET SUMMARY (Last 30 Trading Days)\n")
    lines.append("Aggregated across all brokers per day. Shows overall market activity for this stock.\n")
    lines.append("| Date | Total Bought | Avg Buy Price | Total Sold | Avg Sell Price | Net Qty |")
    lines.append("|------|-------------|---------------|------------|----------------|---------|")
    for _, row in last_30.iterrows():
        lines.append(
            f"| {row['Date'].strftime('%Y-%m-%d')} | {row['Total_Bought']:,.0f} | "
            f"{row['Avg_Buy_Price']:.2f} | {row['Total_Sold']:,.0f} | "
            f"{row['Avg_Sell_Price']:.2f} | {row['Net_Qty']:,.0f} |"
        )
    lines.append("")
    lines.append("---\n")

    # ── Volume analysis ──────────────────────────────────────────────────
    daily_vol = compute_daily_volume(buying_df, selling_df)
    total_daily_vol = daily_vol.sum(axis=1)  # sum across all brokers per day

    overall_avg = total_daily_vol.mean()
    last_30_avg = total_daily_vol.tail(30).mean() if len(total_daily_vol) >= 30 else total_daily_vol.mean()
    last_10_avg = total_daily_vol.tail(10).mean() if len(total_daily_vol) >= 10 else total_daily_vol.mean()
    last_5_avg = total_daily_vol.tail(5).mean() if len(total_daily_vol) >= 5 else total_daily_vol.mean()

    if last_10_avg > last_30_avg * 1.2:
        vol_trend = "INCREASING — Recent 10-day average is significantly above 30-day average"
    elif last_10_avg < last_30_avg * 0.8:
        vol_trend = "DECREASING — Recent 10-day average is significantly below 30-day average"
    else:
        vol_trend = "STABLE — Recent volume is roughly in line with 30-day average"

    lines.append("## VOLUME ANALYSIS\n")
    lines.append(f"- Overall Average Daily Volume: {overall_avg:,.0f}")
    lines.append(f"- Last 30-Day Average Daily Volume: {last_30_avg:,.0f}")
    lines.append(f"- Last 10-Day Average Daily Volume: {last_10_avg:,.0f}")
    lines.append(f"- Last 5-Day Average Daily Volume: {last_5_avg:,.0f}")
    lines.append(f"- Volume Trend: {vol_trend}")
    lines.append("")
    lines.append("---\n")

    # ── Cumulative net position trend (top 5 accumulators) ───────────────
    cumulative_net = compute_cumulative_net(buying_df, selling_df)
    top5_brokers = net_df.head(5)["Broker"].tolist()

    lines.append("## CUMULATIVE NET POSITION TREND (Top 5 Accumulators)\n")
    lines.append(
        "Shows how the top 5 accumulating brokers' net positions have changed over time. "
        "Sampled at 5 time points across the data range.\n"
    )

    cum_dates = cumulative_net.index
    n = len(cum_dates)
    if n >= 5:
        sample_indices = [0, n // 4, n // 2, 3 * n // 4, n - 1]
    else:
        sample_indices = list(range(n))
    sample_dates = [cum_dates[i] for i in sample_indices]

    for broker in top5_brokers:
        if broker not in cumulative_net.columns:
            continue
        lines.append(f"### Broker {int(broker)}\n")
        lines.append("| Date | Cumulative Net Position |")
        lines.append("|------|------------------------|")
        for d in sample_dates:
            val = cumulative_net.loc[d, broker]
            lines.append(f"| {d.strftime('%Y-%m-%d')} | {val:,.0f} |")
        lines.append("")

    lines.append("---\n")

    # ── Recent per-broker activity (last 5 trading days) ─────────────────
    recent_dates = sorted(summary_df["Date"].unique())[-5:]
    recent = summary_df[summary_df["Date"].isin(recent_dates)].copy()
    # Only include brokers that actually had activity
    recent = recent[(recent["Bought_Qty"] != 0) | (recent["Sold_Qty"] != 0)]
    recent = recent.sort_values(["Date", "Broker"])

    lines.append("## RECENT BROKER ACTIVITY (Last 5 Trading Days, Per Broker)\n")
    lines.append(
        "Detailed per-broker activity in the most recent trading days. "
        "Helps identify who is currently buying or selling.\n"
    )
    lines.append("| Date | Broker | Bought Qty | Avg Buy Price | Sold Qty | Avg Sell Price | Net Qty |")
    lines.append("|------|--------|-----------|---------------|----------|----------------|---------|")
    for _, row in recent.iterrows():
        sold_display = f"{abs(row['Sold_Qty']):,.0f}" if row["Sold_Qty"] != 0 else "0"
        lines.append(
            f"| {row['Date'].strftime('%Y-%m-%d')} | {int(row['Broker'])} | "
            f"{row['Bought_Qty']:,.0f} | "
            f"{row['Bought_Avg_Price']:.2f} | "
            f"{sold_display} | "
            f"{row['Sold_Avg_Price']:.2f} | "
            f"{row['Net_Qty']:,.0f} |"
        )
    lines.append("")
    lines.append("---\n")

    # ── Sector comparison ────────────────────────────────────────────────
    _append_sector_comparison(lines, symbol, info, _v)

    # ── Analysis request ─────────────────────────────────────────────────
    _append_analysis_request(lines)

    return "\n".join(lines)


def _append_sector_comparison(lines, symbol, info, _v):
    """Append a sector peer comparison table to the prompt."""
    import numpy as np

    if not info or not info.get("Sector"):
        return

    sector = info["Sector"]
    company_df = load_company_data()
    if company_df is None or company_df.empty:
        return

    peers = company_df[company_df["Sector"] == sector].copy()
    if len(peers) <= 1:
        return  # no peers to compare

    # Sort by market cap descending for a meaningful ordering
    peers = peers.sort_values("Market Capitalization", ascending=False).reset_index(drop=True)

    # Compute sector averages for key metrics
    avg_cols = ["Market Price", "EPS", "P/E Ratio", "Book Value", "PBV",
                "Market Capitalization", "30-Day Avg Volume", "% Change"]
    sector_avgs = {}
    for col in avg_cols:
        if col in peers.columns:
            sector_avgs[col] = peers[col].mean()

    lines.append(f"## SECTOR COMPARISON — {sector}\n")
    lines.append(
        f"All {len(peers)} companies in the **{sector}** sector are listed below. "
        f"The target stock **{symbol}** is marked with **>>>**. "
        f"Use this to compare valuation, size, and activity against peers.\n"
    )

    # Sector averages summary
    lines.append("### Sector Averages\n")
    for col in avg_cols:
        if col in sector_avgs:
            val = sector_avgs[col]
            if not np.isnan(val):
                if col in ("Market Capitalization", "30-Day Avg Volume", "Shares Outstanding"):
                    lines.append(f"- {col}: {val:,.0f}")
                elif col in ("% Change",):
                    lines.append(f"- {col}: {val:.2f}")
                else:
                    lines.append(f"- {col}: {val:,.2f}")
    lines.append("")

    # Peer table
    lines.append("### All Companies in Sector\n")
    lines.append(
        "| | Symbol | Company Name | Market Price | EPS | P/E | Book Value | PBV | Market Cap | 30D Avg Vol | % Change |"
    )
    lines.append(
        "|---|--------|-------------|-------------|-----|-----|-----------|-----|-----------|------------|----------|"
    )
    for _, row in peers.iterrows():
        marker = ">>>" if row["code"] == symbol else ""
        name = _v(row.get("Company Name"))
        # Truncate long names
        if len(name) > 30:
            name = name[:27] + "..."
        lines.append(
            f"| {marker} | {row['code']} | {name} | "
            f"{_v(row.get('Market Price'), '{:,.2f}')} | "
            f"{_v(row.get('EPS'), '{:.2f}')} | "
            f"{_v(row.get('P/E Ratio'), '{:.2f}')} | "
            f"{_v(row.get('Book Value'), '{:.2f}')} | "
            f"{_v(row.get('PBV'), '{:.2f}')} | "
            f"{_v(row.get('Market Capitalization'), '{:,.0f}')} | "
            f"{_v(row.get('30-Day Avg Volume'), '{:,.0f}')} | "
            f"{_v(row.get('% Change'), '{:.2f}')} |"
        )
    lines.append("")
    lines.append("---\n")


def _append_analysis_request(lines):
    """Append the final output section to the prompt lines."""
    lines.append("# SECTION 4: FINAL OUTPUT REQUIREMENTS\n")
    lines.append(
        "Based on ALL the data above and your understanding of NEPSE's dynamics, "
        "provide the following. Be concise but detailed and direct; explain why "
        "when needed.\n"
    )
    lines.append(
        "1. **Executive Summary**: The one-minute thesis — what is happening with "
        "this stock right now and what is the most likely next move? Cite the key "
        "evidence (broker IDs, price levels, volume patterns)."
    )
    lines.append(
        "2. **Fundamental Score** (out of 10): Based on EPS trajectory, dividend "
        "capacity, P/E vs sector, book value, NPL trend (if banking), PPA/PLF "
        "(if hydro). Explain the score."
    )
    lines.append(
        "3. **The Broker Verdict**: Is this stock in **Accumulation**, "
        "**Distribution**, or **Manipulation**? Support with:\n"
        "   - Broker Concentration Ratio (Top 3 buy / total volume)\n"
        "   - Big 5 broker activity (stealth buying vs aggressive sweeping vs absent)\n"
        "   - Matching/circular trading detected? (Y/N, with broker IDs)\n"
        "   - Smart money avg buy price vs current price (sitting on profit = "
        "distribution risk)"
    )
    lines.append(
        "4. **Sector Comparison**: How does this stock compare to peers in P/E, "
        "PBV, EPS, Market Cap, volume? Is it relatively undervalued or overvalued? "
        "Are there better operator-backed plays in the same sector?"
    )
    lines.append(
        "5. **Distribution Warning Signs**: Check for ANY of these — top "
        "accumulators now selling; climactic volume (5-10x avg) with stalling price; "
        "parabolic action (3+ days of 7-10% gains); failed breakout; negative "
        "divergence. Flag prominently if present."
    )
    lines.append(
        "6. **Accumulation Confirmation**: Check for — consistent smart-money buying "
        "over months; price in consolidation near support; low volume compression; "
        "upcoming catalyst (dividend, bonus, AGM, policy); buying during market-wide "
        "dips. Rate confidence: High/Medium/Low."
    )
    lines.append(
        "7. **Trade Plan**:\n"
        "   - **Entry Zone**: Based on Fibonacci 0.618 retracement, support level, "
        "or accumulation zone floor\n"
        "   - **Target 1 & 2**: Based on pivot points, resistance levels, or "
        "Fibonacci extensions\n"
        "   - **Stop Loss**: Based on ATR, previous swing low, or below key support "
        "(max 15% below entry)\n"
        "   - If AVOID: state why and what would need to change"
    )
    lines.append(
        "8. **Risk Rating**: Low / Medium / High / Extreme. State the single most "
        "important thing to watch (e.g. 'Watch if Broker 44 starts selling' or "
        "'Exit if volume spikes without price progress'). Consider NRB policy risk "
        "as a primary filter."
    )
    lines.append("")


PRICE_HISTORY_DIR = Path("price_history")


def load_price_history(symbol):
    """Load price history CSV for *symbol*.

    Returns:
        DataFrame with columns date, open, high, low, close, volume, turnover,
        percent_change — or None if the file doesn't exist.
    """
    csv_path = PRICE_HISTORY_DIR / f"{symbol}.csv"
    if not csv_path.is_file():
        return None
    df = pd.read_csv(csv_path, parse_dates=["date"])
    for col in ("open", "high", "low", "close", "turnover", "percent_change"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("date").reset_index(drop=True)


def build_price_history_markdown(symbol):
    """Build a self-contained LLM prompt focused on price history for *symbol*.

    Returns:
        str — markdown prompt, or None if no price history data exists.
    """
    import numpy as np

    df = load_price_history(symbol)
    if df is None or df.empty:
        return None

    info = get_company_info(symbol)
    lines = []

    # ── ROLE & CONTEXT ─────────────────────────────────────────────────
    lines.append("# ROLE: Expert NEPSE Stock Analyzer — Technical & Price History\n")
    lines.append(
        "You are analyzing the price history of a stock in the Nepal Stock Exchange "
        "(NEPSE), a frontier market where technical patterns can be **deliberately "
        "CREATED by operators** to trap retail investors. Your analysis must account "
        "for this. Be **concise but detailed and direct**; explain your reasoning "
        "when it matters.\n"
    )
    lines.append("---\n")

    # ── SECTION 1: REGULATORY FILTER ────────────────────────────────────
    lines.append("# SECTION 1: REGULATORY FILTER\n")
    lines.append(
        "**No technical signal is valid if it contradicts a major NRB policy shift.** "
        "Consider the following if you have external knowledge:\n\n"
        "- 91-day T-bill rate and interbank rate as lead indicators (high rates = "
        "bearish for equity)\n"
        "- Margin lending rules (4/12 → 15/20): tightening crushed the index from "
        "3198 to 1818; relaxations trigger rallies\n"
        "- Minister–Market Matrix: FM appointments drive multi-month sentiment "
        "(Paudel = bullish; Khatiwada = bearish)\n"
    )
    lines.append("---\n")

    # ── SECTION 2: TECHNICAL ANALYSIS ───────────────────────────────────
    lines.append("# SECTION 2: TECHNICAL ANALYSIS (Japanese Foundation + NEPSE Caveats)\n")
    lines.append(
        "Apply the following to the OHLC + volume data provided. NEPSE research has "
        "shown these techniques to be effective in this market:\n\n"
        "- **Heikin-Ashi & Candlestick Patterns**: Identify Hammer, Shooting Star, "
        "and Engulfing patterns at support/resistance. Focus on the weekly timeframe "
        "for Engulfing candles.\n"
        "- **Ichimoku Kinko Hyo**: Is price above the Kumo cloud? Analyze the TK "
        "Cross (Tenkan/Kijun) for trend confirmation. Ichimoku has proven more "
        "effective than RSI alone for NEPSE risk management.\n"
        "- **RSI & Divergence**: Look for Hidden Bullish Divergence (price higher "
        "low, RSI lower low) — a high-probability signal in NEPSE's cyclical waves. "
        "Caution: RSI in isolation can exit bull runs prematurely.\n"
        "- **MACD & SMA**: MACD + RSI combinations have shown strong results in "
        "NEPSE banking sub-index studies. Use for trend and entry/exit timing.\n"
        "- **Bollinger Bands**: Effective for measuring divergence from mean during "
        "active trends; less useful in extreme low-volatility periods.\n"
        "- **Elliott Wave & Fibonacci**: NEPSE follows primary impulse structure "
        "(Waves 1-5). Key levels at 38.2% and 61.8% retracement/extension.\n"
        "- **Smart Money Concepts (SMC/ICT)**: Detect liquidity grabs and stop hunts "
        "(sharp wicks against trend that reverse immediately). Volume confirmation "
        "essential — higher volume on breakout candles vs consolidation.\n"
        "- **Volume Profile**: Identify the Point of Control (POC). If current price "
        "< POC but broker concentration is high, flag as Silent Accumulation.\n\n"
        "**NEPSE CAVEATS — always apply:**\n"
        "- Operators paint patterns; confirm breakouts with sustained volume 3+ days\n"
        "- Circuit breakers ±10%: repeated +10% = operator markup; repeated -10% = "
        "forced liquidation\n"
        "- Support/resistance at round numbers (200, 300, 500, 1000) are manipulated\n"
        "- False breakouts are extremely common (stop-loss hunting)\n"
        "- Parabolic rallies (3+ days of 7-10% gains) = classic distribution setup\n"
        "- Weekly charts for big picture, daily for entry/exit timing\n"
    )
    lines.append("---\n")

    # ── Stock context ────────────────────────────────────────────────────
    lines.append(f"## STOCK: {symbol}\n")
    if info:
        lines.append(f"- Company Name: {info.get('Company Name', 'N/A')}")
        lines.append(f"- Sector: {info.get('Sector', 'N/A')}")
        lines.append(f"- Current Market Price: {info.get('Market Price', 'N/A')}")
    lines.append("")
    lines.append("---\n")

    # ── Full history summary stats ───────────────────────────────────────
    lines.append("## FULL PRICE HISTORY SUMMARY\n")
    lines.append(f"- Date Range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    lines.append(f"- Total Trading Days: {len(df)}")
    lines.append(f"- All-Time High: {df['high'].max():.2f} (on {df.loc[df['high'].idxmax(), 'date'].strftime('%Y-%m-%d')})")
    lines.append(f"- All-Time Low: {df['low'].min():.2f} (on {df.loc[df['low'].idxmin(), 'date'].strftime('%Y-%m-%d')})")
    lines.append(f"- Latest Close: {df.iloc[-1]['close']:.2f} (on {df.iloc[-1]['date'].strftime('%Y-%m-%d')})")
    lines.append(f"- Average Close: {df['close'].mean():.2f}")
    lines.append(f"- Average Volume: {df['volume'].mean():,.0f}")
    lines.append(f"- Average Turnover: {df['turnover'].mean():,.0f}")

    # Recent vs historical volume
    if len(df) >= 30:
        recent_30_vol = df.tail(30)["volume"].mean()
        lines.append(f"- Last 30-Day Avg Volume: {recent_30_vol:,.0f}")
    if len(df) >= 10:
        recent_10_vol = df.tail(10)["volume"].mean()
        lines.append(f"- Last 10-Day Avg Volume: {recent_10_vol:,.0f}")

    # Price change over periods
    if len(df) >= 2:
        latest = df.iloc[-1]["close"]
        first = df.iloc[0]["close"]
        total_change = ((latest - first) / first) * 100
        lines.append(f"- Total Price Change: {total_change:+.2f}%")
    if len(df) >= 30:
        p30 = df.iloc[-30]["close"]
        lines.append(f"- 30-Day Price Change: {((latest - p30) / p30) * 100:+.2f}%")
    if len(df) >= 90:
        p90 = df.iloc[-90]["close"]
        lines.append(f"- 90-Day Price Change: {((latest - p90) / p90) * 100:+.2f}%")

    lines.append("")
    lines.append("---\n")

    # ── Weekly summary (full history) ────────────────────────────────────
    weekly = df.copy()
    weekly["week"] = weekly["date"].dt.to_period("W").apply(lambda p: p.start_time)
    week_agg = weekly.groupby("week").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        turnover=("turnover", "sum"),
    ).reset_index()
    week_agg = week_agg.sort_values("week")

    lines.append("## WEEKLY PRICE SUMMARY (Full History)\n")
    lines.append(
        "Aggregated into weekly candles. Useful for identifying medium-term trends.\n"
    )
    lines.append("| Week Start | Open | High | Low | Close | Volume | Turnover |")
    lines.append("|-----------|------|------|-----|-------|--------|----------|")
    for _, row in week_agg.iterrows():
        lines.append(
            f"| {row['week'].strftime('%Y-%m-%d')} | {row['open']:.2f} | "
            f"{row['high']:.2f} | {row['low']:.2f} | {row['close']:.2f} | "
            f"{row['volume']:,} | {row['turnover']:,.0f} |"
        )
    lines.append("")
    lines.append("---\n")

    # ── Last 90 trading days (daily) ─────────────────────────────────────
    last_90 = df.tail(90)

    lines.append(f"## DAILY PRICE DATA (Last {len(last_90)} Trading Days)\n")
    lines.append(
        "Detailed daily OHLC data. Use this for short-term technical analysis.\n"
    )
    lines.append("| Date | Open | High | Low | Close | Volume | Turnover | % Change |")
    lines.append("|------|------|------|-----|-------|--------|----------|----------|")
    for _, row in last_90.iterrows():
        lines.append(
            f"| {row['date'].strftime('%Y-%m-%d')} | {row['open']:.2f} | "
            f"{row['high']:.2f} | {row['low']:.2f} | {row['close']:.2f} | "
            f"{row['volume']:,} | {row['turnover']:,.0f} | {row['percent_change']:+.2f}% |"
        )
    lines.append("")
    lines.append("---\n")

    # ── SECTION 3: FINAL OUTPUT ────────────────────────────────────────
    lines.append("# SECTION 3: FINAL OUTPUT REQUIREMENTS\n")
    lines.append(
        "Based on ALL the price history data above and the analytical framework, "
        "provide the following. Be concise but detailed and direct.\n"
    )
    lines.append(
        "1. **Executive Summary**: The one-minute technical thesis — what is the "
        "price/volume telling us right now and what is the most probable next move? "
        "Cite specific dates, prices, and volume numbers."
    )
    lines.append(
        "2. **Technical Score** (out of 10): Based on Ichimoku cloud position, "
        "candlestick patterns, RSI/MACD signals, Elliott Wave position, Fibonacci "
        "levels, and volume profile. Explain the score."
    )
    lines.append(
        "3. **Operator Cycle from Price Action**: What phase is this stock in? "
        "(Sideways accumulation, markup rally, distribution top, or markdown "
        "decline). Cite date ranges, price levels, and volume patterns."
    )
    lines.append(
        "4. **Support & Resistance**: Key levels, especially psychological round "
        "numbers (multiples of 50, 100, 500). Which have been tested multiple "
        "times? Which are operator-defended vs likely to break?"
    )
    lines.append(
        "5. **Volume Authenticity**: Are recent volume spikes sustained 3+ days "
        "(real) or single-day (manipulation)? Volume-price divergence present?"
    )
    lines.append(
        "6. **Circuit Breaker & Breakout Assessment**: Any sequences of +/-10% "
        "days? Has the stock broken out of consolidation — is it real (sustained "
        "volume) or a false breakout (stop-loss hunt)?"
    )
    lines.append(
        "7. **Trade Plan**:\n"
        "   - **Entry Zone**: Based on Fibonacci 0.618 retracement or key support\n"
        "   - **Target 1 & 2**: Based on pivot points, resistance, or Fibonacci "
        "extensions\n"
        "   - **Stop Loss**: Based on ATR or previous swing low; account for NEPSE "
        "±10% circuit breaker mechanics\n"
        "   - If AVOID: state why and what would need to change"
    )
    lines.append("")

    return "\n".join(lines)


def get_scraped_symbols():
    """Return a sorted list of symbols that have a floorsheets/ subdirectory."""
    if not FLOORSHEET_BASE_DIR.is_dir():
        return []
    return sorted(
        d.name for d in FLOORSHEET_BASE_DIR.iterdir()
        if d.is_dir() and any(d.glob("*.csv"))
    )
