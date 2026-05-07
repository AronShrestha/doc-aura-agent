"""NEPSE Floorsheet Dashboard – Streamlit app.

Run with:
    streamlit run dashboard.py
"""

import os
import base64
from datetime import datetime, date

import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

from analysis import (
    get_scraped_symbols,
    load_floorsheet_data,
    load_company_data,
    get_company_info,
    load_price_history,
    build_price_history_markdown,
    compute_net_holdings,
    compute_cumulative_net,
    compute_daily_volume,
    compute_daily_net,
    compute_daily_prices,
    build_daily_broker_summary,
    build_stock_markdown,
)
from scrape_floorsheet import run_scrape
from scrape_company import scrape_all_companies
from scrape_price_history import fetch_price_history
from valuation import render_valuation


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="NEPSE Dashboard", layout="wide")

# ── Session state defaults ───────────────────────────────────────────────────
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None
if "scrape_result" not in st.session_state:
    st.session_state.scrape_result = None
if "nepsealpha_token" not in st.session_state:
    st.session_state.nepsealpha_token = "ejqNMc2qUl2gzHspOStisky10SWbz4SSBGW93o9W"
if "nepsealpha_session" not in st.session_state:
    st.session_state.nepsealpha_session = "eyJpdiI6Inl6L2tSZGhYNWp2ZXdweTExZHNGTHc9PSIsInZhbHVlIjoiT0xBcjlEUGNLUnJnM1NkMzhCSTZXV1JVT2psN0tFdHFBQUlWYXFyU3Q1T0tIZTVEemJPcjNnMWVVc21hcnpTSlloWWxwSVlPVTN4SHpkQzdiM1N3K2htZ1M0bC9NSWNFT2RIZ3RWVkQreXlPUHJKRmNaWHVQbGlYRHdNVk1TYkEiLCJtYWMiOiI5ZTRiOTIyODlhNjMzNGRjZjRjYzI3M2EwNzUyMDkzYzU2N2VhYjdkMGQ4MTIzZDYzMmY3YzdiZGYzM2NiNWE2IiwidGFnIjoiIn0%3D"
if "nepsealpha_cf" not in st.session_state:
    st.session_state.nepsealpha_cf = "rpAlEGU.ZbKpYo8lR4kPdUsIPN_AEdfquDhVpNhyw5M-1771161532-1.2.1.1-jVlFyo96NjYWWv1rgcE.uWXOQbAl.oHmjZhSFAG9wq1nPEnyByB81PnqnVMNT3RUkijoZ2Zp2HdbTz9i7yTMAwu7vG6.wbHRn7.Sn.D9p28alga1hk0EQw9Vfv2g8xrwQkzB.HJQLFLkvR_KpfCMeatdi3v0m7wljYQk3PsvYJZXqJsJvI1fheMVJn8DiTjsf9gE5l2lP1IdlNw2ujtZGvQGyv7SuZbe5nXz2_vg7mM"


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOORSHEET SCRAPE CONTROLS (reusable)
# ═══════════════════════════════════════════════════════════════════════════════

def render_floorsheet_scrape_controls(default_symbol="", key_prefix="home"):
    """Render the floorsheet scrape UI (symbol input, button, progress, result).

    Used both on the home page and inside the stock detail page.
    """
    col_sym, col_btn = st.columns([3, 1])
    with col_sym:
        symbol = st.text_input(
            "Stock Symbol", value=default_symbol,
            placeholder="e.g. BHPL",
            key=f"{key_prefix}_symbol",
        ).strip().upper()

    with st.expander("Advanced Settings"):
        adv_c1, adv_c2 = st.columns(2)
        with adv_c1:
            max_workers = st.number_input(
                "Max Workers", min_value=1, max_value=32, value=8, step=1,
                key=f"{key_prefix}_workers",
            )
        with adv_c2:
            sleep_time = st.number_input(
                "Sleep Time (seconds)", min_value=0.0, max_value=30.0,
                value=10.0, step=0.5, key=f"{key_prefix}_sleep",
            )

        date_c1, date_c2 = st.columns(2)
        with date_c1:
            scrape_start = st.date_input(
                "Start Date", value=date(2023, 2, 14),
                key=f"{key_prefix}_start",
            )
        with date_c2:
            scrape_end = st.date_input(
                "End Date", value=date.today(),
                key=f"{key_prefix}_end",
            )

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        scrape_clicked = st.button(
            "Scrape Floorsheet", type="primary",
            use_container_width=True, key=f"{key_prefix}_btn",
        )

    if scrape_clicked:
        if not symbol:
            st.error("Please enter a stock symbol.")
        else:
            st.session_state.scrape_result = None

            progress_bar = st.progress(0, text="Starting scrape...")

            def on_progress(completed, total, stats):
                pct = completed / total if total else 1.0
                progress_bar.progress(
                    pct,
                    text=f"Scraping {symbol}:  {completed}/{total}  |  "
                         f"Saved: {stats['saved']}  |  "
                         f"Skipped: {stats['skipped']}  |  "
                         f"Errors: {stats['errors']}",
                )

            result = run_scrape(
                symbol=symbol,
                max_workers=int(max_workers),
                sleep_time=float(sleep_time),
                start_date=datetime.combine(scrape_start, datetime.min.time()),
                end_date=datetime.combine(scrape_end, datetime.min.time()),
                progress_callback=on_progress,
            )

            st.session_state.scrape_result = result
            progress_bar.progress(1.0, text="Scraping complete!")

    result = st.session_state.scrape_result
    if result is not None:
        if result["total"] == 0 and result.get("already_existed", 0) > 0:
            st.info(f"All dates already scraped ({result['already_existed']} CSV files exist).")
        else:
            r_c1, r_c2, r_c3 = st.columns(3)
            r_c1.metric("Saved", result["saved"])
            r_c2.metric("Skipped (no data)", result["skipped"])
            r_c3.metric("Errors", result["errors"])

            if result["errors"] > 0:
                st.warning(
                    f"{result['errors']} date(s) failed to scrape: "
                    f"{', '.join(sorted(result.get('error_dates', [])))}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOORSHEET ANALYSIS (reusable)
# ═══════════════════════════════════════════════════════════════════════════════

def render_floorsheet_analysis(symbol: str):
    """Render the full floorsheet analysis (tables + charts) for *symbol*."""

    with st.spinner("Loading floorsheet data..."):
        data = load_floorsheet_data(symbol)

    buying_df = data["buying_df"]
    selling_df = data["selling_df"]

    # ── Summary metrics ──────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total CSV files", f"{data['total_csvs']:,}")
    c2.metric("Dates with data", f"{data['dates_with_data']:,}")
    c3.metric("Buying records", f"{len(buying_df):,}")
    c4.metric("Selling records", f"{len(selling_df):,}")

    if buying_df.empty:
        st.warning("No floorsheet data found for this symbol.")
        return

    # ── Floorsheet Data Table ────────────────────────────────────────────
    st.subheader("Floorsheet Data")

    summary_df = build_daily_broker_summary(buying_df, selling_df)

    filter_c1, filter_c2 = st.columns(2)
    with filter_c1:
        min_date = summary_df["Date"].min().date()
        max_date = summary_df["Date"].max().date()
        date_range = st.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    with filter_c2:
        all_brokers = sorted(summary_df["Broker"].unique())
        selected_brokers = st.multiselect(
            "Filter by Broker(s)",
            options=all_brokers,
            default=[],
            placeholder="All brokers",
        )

    filtered = summary_df.copy()
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered["Date"].dt.date >= start) & (filtered["Date"].dt.date <= end)
        ]
    if selected_brokers:
        filtered = filtered[filtered["Broker"].isin(selected_brokers)]

    display_df = filtered.copy()
    display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")

    st.dataframe(
        display_df,
        column_config={
            "Date": st.column_config.TextColumn("Date"),
            "Broker": st.column_config.NumberColumn("Broker", format="%d"),
            "Bought_Qty": st.column_config.NumberColumn("Bought Qty (+)", format="%,.0f"),
            "Bought_Avg_Price": st.column_config.NumberColumn("Bought Avg Price", format="%.2f"),
            "Sold_Qty": st.column_config.NumberColumn("Sold Qty (-)", format="%,.0f"),
            "Sold_Avg_Price": st.column_config.NumberColumn("Sold Avg Price", format="%.2f"),
            "Net_Qty": st.column_config.NumberColumn("Net Qty", format="%,.0f"),
        },
        use_container_width=True,
        hide_index=True,
        height=500,
    )
    st.caption(f"Showing {len(filtered):,} rows")

    # ── Compute analysis ─────────────────────────────────────────────────
    net_df = compute_net_holdings(buying_df, selling_df)
    cumulative_net = compute_cumulative_net(buying_df, selling_df)
    daily_vol = compute_daily_volume(buying_df, selling_df)
    daily_net_df = compute_daily_net(buying_df, selling_df)
    buy_price_pivot, sell_price_pivot = compute_daily_prices(buying_df, selling_df)

    # ── 1. Net Holdings by Broker ────────────────────────────────────────
    st.subheader("Net Holdings by Broker")

    TIMEFRAME_OFFSETS = {
        "All Time": None,
        "1 Week": pd.DateOffset(weeks=1),
        "1 Month": pd.DateOffset(months=1),
        "3 Months": pd.DateOffset(months=3),
        "6 Months": pd.DateOffset(months=6),
        "1 Year": pd.DateOffset(years=1),
    }

    timeframe = st.selectbox(
        "Time Frame",
        list(TIMEFRAME_OFFSETS.keys()),
        index=0,
        key="net_holdings_timeframe",
    )

    offset = TIMEFRAME_OFFSETS[timeframe]
    if offset is not None:
        cutoff = pd.Timestamp.now() - offset
        tf_buy = buying_df[pd.to_datetime(buying_df["Date"]) >= cutoff]
        tf_sell = selling_df[pd.to_datetime(selling_df["Date"]) >= cutoff]
        tf_net_df = compute_net_holdings(tf_buy, tf_sell)
    else:
        tf_net_df = net_df

    if tf_net_df.empty:
        st.info(f"No floorsheet data in the selected time frame ({timeframe}).")
    else:
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in tf_net_df["Net_Quantity"]]
        fig1_customdata = np.column_stack([
            tf_net_df["Total_Bought"].values, tf_net_df["Avg_Buy_Price"].values,
            tf_net_df["Total_Sold"].values, tf_net_df["Avg_Sell_Price"].values,
        ])
        fig1 = go.Figure(go.Bar(
            x=tf_net_df["Broker"].astype(str), y=tf_net_df["Net_Quantity"],
            marker_color=colors, customdata=fig1_customdata,
            hovertemplate=(
                "<b>Broker %{x}</b><br>"
                "Net Qty: %{y:,.0f}<br>"
                "Bought: %{customdata[0]:,.0f} @ %{customdata[1]:.2f}<br>"
                "Sold: %{customdata[2]:,.0f} @ %{customdata[3]:.2f}"
                "<extra></extra>"
            ),
        ))
        fig1.add_hline(y=0, line_dash="dash", line_color="black", line_width=0.8)
        fig1.update_layout(
            xaxis_title="Broker", yaxis_title="Net Quantity (Bought − Sold)",
            xaxis_tickangle=-90, height=500, margin=dict(b=120),
        )
        st.plotly_chart(fig1, use_container_width=True)

    # ── 2. Top 10 Accumulators & Top 10 Sellers ─────────────────────────
    st.subheader("Top 10 Accumulators & Top 10 Sellers")
    top10 = tf_net_df.head(10)
    bottom10 = tf_net_df.tail(10).iloc[::-1]

    _bar_hover = (
        "<b>Broker %{y}</b><br>"
        "Net Qty: %{x:,.0f}<br>"
        "Bought: %{customdata[0]:,.0f} @ %{customdata[1]:.2f}<br>"
        "Sold: %{customdata[2]:,.0f} @ %{customdata[3]:.2f}"
        "<extra></extra>"
    )

    fig2 = make_subplots(rows=1, cols=2,
                         subplot_titles=["Top 10 Accumulators (Most Bought)",
                                         "Top 10 Sellers (Most Sold)"])

    top10_cd = np.column_stack([
        top10["Total_Bought"].values, top10["Avg_Buy_Price"].values,
        top10["Total_Sold"].values, top10["Avg_Sell_Price"].values,
    ])
    fig2.add_trace(go.Bar(
        y=top10["Broker"].astype(str), x=top10["Net_Quantity"],
        orientation="h", marker_color="#2ecc71",
        customdata=top10_cd, hovertemplate=_bar_hover,
        text=[f"{q:,.0f} @ {p:.2f}" for q, p in zip(top10["Net_Quantity"], top10["Avg_Buy_Price"])],
        textposition="outside", showlegend=False,
    ), row=1, col=1)

    bottom10_cd = np.column_stack([
        bottom10["Total_Bought"].values, bottom10["Avg_Buy_Price"].values,
        bottom10["Total_Sold"].values, bottom10["Avg_Sell_Price"].values,
    ])
    fig2.add_trace(go.Bar(
        y=bottom10["Broker"].astype(str), x=bottom10["Net_Quantity"],
        orientation="h", marker_color="#e74c3c",
        customdata=bottom10_cd, hovertemplate=_bar_hover,
        text=[f"{q:,.0f} @ {p:.2f}" for q, p in zip(bottom10["Net_Quantity"], bottom10["Avg_Sell_Price"])],
        textposition="outside", showlegend=False,
    ), row=1, col=2)

    fig2.update_yaxes(autorange="reversed", row=1, col=1)
    fig2.update_yaxes(autorange="reversed", row=1, col=2)
    fig2.update_layout(height=500)
    st.plotly_chart(fig2, use_container_width=True)

    # Helper: cumulative-net Scatter trace with price hover data
    _hover_tpl = (
        "<b>Broker %{fullData.name}</b><br>"
        "Date: %{x|%Y-%m-%d}<br>"
        "Cumulative Net: %{y:,.0f}<br>"
        "Daily Net: %{customdata[0]:,.0f}<br>"
        "Buy Avg Price: %{customdata[1]:.2f}<br>"
        "Sell Avg Price: %{customdata[2]:.2f}"
        "<extra></extra>"
    )

    def _cumul_trace(broker, width=1.5):
        cd = np.column_stack([
            daily_net_df[broker].values,
            buy_price_pivot[broker].fillna(0).values,
            sell_price_pivot[broker].fillna(0).values,
        ])
        return go.Scatter(
            x=cumulative_net.index, y=cumulative_net[broker],
            customdata=cd, hovertemplate=_hover_tpl,
            mode="lines", name=f"Broker {broker}",
            line=dict(width=width),
        )

    # ── 3. Cumulative Net – Top 10 Accumulators ─────────────────────────
    st.subheader("Cumulative Net Quantity Over Time — Top 10 Accumulators")
    top10_brokers = net_df.head(10)["Broker"].tolist()
    fig3 = go.Figure()
    for broker in top10_brokers:
        if broker in cumulative_net.columns:
            fig3.add_trace(_cumul_trace(broker))
    fig3.update_layout(xaxis_title="Date", yaxis_title="Cumulative Net Quantity",
                       height=550, legend=dict(x=0, y=1))
    st.plotly_chart(fig3, use_container_width=True)

    # ── 4. Cumulative Net – Top 10 Sellers ───────────────────────────────
    st.subheader("Cumulative Net Quantity Over Time — Top 10 Sellers")
    bottom10_brokers = net_df.tail(10)["Broker"].tolist()
    fig4 = go.Figure()
    for broker in bottom10_brokers:
        if broker in cumulative_net.columns:
            fig4.add_trace(_cumul_trace(broker))
    fig4.update_layout(xaxis_title="Date", yaxis_title="Cumulative Net Quantity",
                       height=550, legend=dict(x=0, y=0))
    st.plotly_chart(fig4, use_container_width=True)

    # ── 5. Cumulative Net – Custom Broker Filter ─────────────────────────
    st.subheader("Cumulative Net Quantity Over Time — Custom Broker Filter")
    all_broker_list = sorted(cumulative_net.columns.tolist())
    custom_brokers = st.multiselect(
        "Select broker(s) to plot", options=all_broker_list,
        default=[], placeholder="Type or pick broker numbers...",
        key="custom_cumulative_brokers",
    )
    if custom_brokers:
        fig_custom = go.Figure()
        for broker in custom_brokers:
            fig_custom.add_trace(_cumul_trace(broker))
        fig_custom.update_layout(xaxis_title="Date", yaxis_title="Cumulative Net Quantity",
                                 height=550, legend=dict(x=0, y=1))
        st.plotly_chart(fig_custom, use_container_width=True)
    else:
        st.info("Select one or more brokers above to see their cumulative net quantity over time.")

    # ── 6. Daily Trading Volume – Top 10 Most Active ─────────────────────
    st.subheader("Daily Trading Volume — Top 10 Most Active Brokers (7-day Rolling Avg)")
    total_volume = daily_vol.sum().sort_values(ascending=False)
    top10_vol_brokers = total_volume.head(10).index.tolist()

    fig5 = go.Figure()
    for broker in top10_vol_brokers:
        rolling = daily_vol[broker].rolling(window=7, min_periods=1).mean()
        fig5.add_trace(go.Scatter(
            x=daily_vol.index, y=rolling, mode="lines",
            name=f"Broker {broker}", line=dict(width=1.2), opacity=0.85,
        ))
    fig5.update_layout(xaxis_title="Date", yaxis_title="Daily Volume (7-day rolling avg)",
                       height=550, legend=dict(x=0, y=1))
    st.plotly_chart(fig5, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  STOCK DETAIL VIEW
# ═══════════════════════════════════════════════════════════════════════════════

def render_stock_detail(symbol: str):
    """Show stock info card + floorsheet analysis for *symbol*."""

    if st.button("← Back to Home"):
        st.session_state.selected_symbol = None
        st.rerun()

    st.title(f"{symbol}")

    # ── Action buttons row ─────────────────────────────────────────────
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        st.link_button(
            "View Chart on NepseAlpha",
            f"https://nepsealpha.com/trading/chart?symbol={symbol}",
        )

    # ── LLM Analysis Prompt ──────────────────────────────────────────────
    with st.expander("LLM Analysis Prompt (copy & paste to any LLM)"):
        with st.spinner("Building analysis prompt..."):
            markdown_text = build_stock_markdown(symbol)

        b64 = base64.b64encode(markdown_text.encode("utf-8")).decode("utf-8")
        components.html(
            f"""
            <button id="copyBtn" style="
                background-color: #ff4b4b; color: white; border: none;
                padding: 0.5rem 1rem; border-radius: 0.5rem; cursor: pointer;
                font-size: 0.9rem; font-weight: 500;
            ">
                Copy to Clipboard
            </button>
            <span id="status" style="margin-left: 0.75rem; font-size: 0.85rem; color: #888;"></span>
            <script>
            const btn = document.getElementById('copyBtn');
            const status = document.getElementById('status');
            btn.addEventListener('click', async () => {{
                try {{
                    const text = atob("{b64}");
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.position = 'fixed';
                    ta.style.left = '-9999px';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                    status.textContent = 'Copied!';
                    status.style.color = '#2ecc71';
                    setTimeout(() => {{ status.textContent = ''; }}, 3000);
                }} catch(e) {{
                    status.textContent = 'Failed to copy';
                    status.style.color = '#e74c3c';
                }}
            }});
            </script>
            """,
            height=50,
        )

        st.code(markdown_text, language="markdown")

    # ── Stock Info Card ──────────────────────────────────────────────────
    info = get_company_info(symbol)
    if info:
        st.subheader("Stock Information")
        st.caption(f"Sector: **{info.get('Sector', 'N/A')}**  |  "
                   f"Last Traded: **{info.get('Last Traded On', 'N/A')}**")

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Market Price", f"{info.get('Market Price', 'N/A')}")
        m2.metric("% Change", f"{info.get('% Change', 'N/A')}")
        m3.metric("EPS", f"{info.get('EPS', 'N/A')}")
        m4.metric("P/E Ratio", f"{info.get('P/E Ratio', 'N/A')}")
        m5.metric("Book Value", f"{info.get('Book Value', 'N/A')}")
        m6.metric("PBV", f"{info.get('PBV', 'N/A')}")

        m7, m8, m9, m10 = st.columns(4)
        mkt_cap = info.get("Market Capitalization", "N/A")
        if isinstance(mkt_cap, (int, float)) and not pd.isna(mkt_cap):
            mkt_cap = f"{mkt_cap:,.0f}"
        m7.metric("Market Cap", mkt_cap)

        shares = info.get("Shares Outstanding", "N/A")
        if isinstance(shares, (int, float)) and not pd.isna(shares):
            shares = f"{shares:,.0f}"
        m8.metric("Shares Outstanding", shares)

        m9.metric("52W High-Low", info.get("52 Weeks High - Low", "N/A"))
        m10.metric("1 Year Yield", info.get("1 Year Yield", "N/A"))
    else:
        st.info("No company data available. Refresh stock prices on the home page to load it.")

    # ── NepseAlpha Embed ──────────────────────────────────────────────────
    components.html(
        f'<iframe src="https://nepsealpha.com/search?q={symbol}" '
        f'width="100%" height="600" style="border:none;"></iframe>',
        height=600,
    )

    st.divider()

    # ── Price History Section ─────────────────────────────────────────────
    st.header(f"Price History — {symbol}")

    price_df = load_price_history(symbol)

    # Fetch controls (always show so user can refresh)
    with st.expander("Fetch / Refresh Price History"):
        ph_c1, ph_c2 = st.columns(2)
        with ph_c1:
            ph_start = st.date_input(
                "Start Date", value=date(2021, 1, 1), key="ph_start",
            )
        with ph_c2:
            ph_end = st.date_input(
                "End Date", value=date.today(), key="ph_end",
            )

        na_token = st.text_input(
            "_token (CSRF)", value=st.session_state.nepsealpha_token,
            key="ph_token", type="password",
        )
        na_session = st.text_input(
            "nepsealpha_session cookie", value=st.session_state.nepsealpha_session,
            key="ph_session", type="password",
        )
        na_cf = st.text_input(
            "cf_clearance cookie", value=st.session_state.nepsealpha_cf,
            key="ph_cf", type="password",
        )

        if st.button("Fetch Price History", type="primary", key="ph_fetch_btn"):
            if not na_token or not na_session:
                st.error("Please provide at least the _token and nepsealpha_session cookie.")
            else:
                # Persist credentials in session state
                st.session_state.nepsealpha_token = na_token
                st.session_state.nepsealpha_session = na_session
                st.session_state.nepsealpha_cf = na_cf

                with st.spinner(f"Fetching price history for {symbol}..."):
                    try:
                        price_df = fetch_price_history(
                            symbol=symbol,
                            start_date=str(ph_start),
                            end_date=str(ph_end),
                            token=na_token,
                            session_cookie=na_session,
                            cf_clearance=na_cf,
                        )
                        st.success(f"Fetched {len(price_df)} records for {symbol}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to fetch: {e}")

    if price_df is not None and not price_df.empty:
        # ── Candlestick chart with volume subplot ─────────────────────────
        fig_price = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
        )

        fig_price.add_trace(go.Candlestick(
            x=price_df["date"],
            open=price_df["open"],
            high=price_df["high"],
            low=price_df["low"],
            close=price_df["close"],
            name="OHLC",
        ), row=1, col=1)

        colors = [
            "#2ecc71" if row["close"] >= row["open"] else "#e74c3c"
            for _, row in price_df.iterrows()
        ]
        fig_price.add_trace(go.Bar(
            x=price_df["date"],
            y=price_df["volume"],
            marker_color=colors,
            name="Volume",
            opacity=0.7,
        ), row=2, col=1)

        fig_price.update_layout(
            height=600,
            xaxis_rangeslider_visible=False,
            showlegend=False,
            margin=dict(t=30),
        )
        fig_price.update_yaxes(title_text="Price (NPR)", row=1, col=1)
        fig_price.update_yaxes(title_text="Volume", row=2, col=1)

        st.plotly_chart(fig_price, use_container_width=True)

        # ── Filterable data table ─────────────────────────────────────────
        st.subheader("Price History Data")

        ph_min_date = price_df["date"].min().date()
        ph_max_date = price_df["date"].max().date()
        ph_date_range = st.date_input(
            "Filter Date Range",
            value=(ph_min_date, ph_max_date),
            min_value=ph_min_date,
            max_value=ph_max_date,
            key="ph_date_filter",
        )

        ph_filtered = price_df.copy()
        if isinstance(ph_date_range, (list, tuple)) and len(ph_date_range) == 2:
            ph_filtered = ph_filtered[
                (ph_filtered["date"].dt.date >= ph_date_range[0])
                & (ph_filtered["date"].dt.date <= ph_date_range[1])
            ]

        display_ph = ph_filtered.copy()
        display_ph["date"] = display_ph["date"].dt.strftime("%Y-%m-%d")

        st.dataframe(
            display_ph,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "open": st.column_config.NumberColumn("Open", format="%.2f"),
                "high": st.column_config.NumberColumn("High", format="%.2f"),
                "low": st.column_config.NumberColumn("Low", format="%.2f"),
                "close": st.column_config.NumberColumn("Close", format="%.2f"),
                "volume": st.column_config.NumberColumn("Volume", format="%,d"),
                "turnover": st.column_config.NumberColumn("Turnover", format="%,.0f"),
                "percent_change": st.column_config.NumberColumn("% Change", format="%.2f%%"),
            },
            use_container_width=True,
            hide_index=True,
            height=400,
        )
        st.caption(f"Showing {len(ph_filtered):,} of {len(price_df):,} records")

        # ── Price History LLM Prompt ──────────────────────────────────────
        with st.expander("Price History LLM Prompt (copy & paste to any LLM)"):
            with st.spinner("Building price history prompt..."):
                ph_markdown = build_price_history_markdown(symbol)

            if ph_markdown:
                ph_b64 = base64.b64encode(ph_markdown.encode("utf-8")).decode("utf-8")
                components.html(
                    f"""
                    <button id="copyPhBtn" style="
                        background-color: #ff4b4b; color: white; border: none;
                        padding: 0.5rem 1rem; border-radius: 0.5rem; cursor: pointer;
                        font-size: 0.9rem; font-weight: 500;
                    ">
                        Copy to Clipboard
                    </button>
                    <span id="phStatus" style="margin-left: 0.75rem; font-size: 0.85rem; color: #888;"></span>
                    <script>
                    const phBtn = document.getElementById('copyPhBtn');
                    const phStatus = document.getElementById('phStatus');
                    phBtn.addEventListener('click', async () => {{
                        try {{
                            const text = atob("{ph_b64}");
                            const ta = document.createElement('textarea');
                            ta.value = text;
                            ta.style.position = 'fixed';
                            ta.style.left = '-9999px';
                            document.body.appendChild(ta);
                            ta.select();
                            document.execCommand('copy');
                            document.body.removeChild(ta);
                            phStatus.textContent = 'Copied!';
                            phStatus.style.color = '#2ecc71';
                            setTimeout(() => {{ phStatus.textContent = ''; }}, 3000);
                        }} catch(e) {{
                            phStatus.textContent = 'Failed to copy';
                            phStatus.style.color = '#e74c3c';
                        }}
                    }});
                    </script>
                    """,
                    height=50,
                )
                st.code(ph_markdown, language="markdown")
            else:
                st.warning("Could not build price history prompt.")
    else:
        st.info("No price history data available. Use the panel above to fetch it.")

    st.divider()

    # ── Floorsheet Section ───────────────────────────────────────────────
    st.header(f"Floorsheet — {symbol}")

    floorsheet_dir = f"floorsheets/{symbol}"
    has_floorsheet = (
        os.path.isdir(floorsheet_dir)
        and any(f.endswith(".csv") for f in os.listdir(floorsheet_dir))
    )

    if has_floorsheet:
        render_floorsheet_analysis(symbol)
    else:
        st.warning("No floorsheet data available for this symbol.")
        st.subheader("Scrape Floorsheet")
        render_floorsheet_scrape_controls(
            default_symbol=symbol, key_prefix="detail",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  HOME VIEW
# ═══════════════════════════════════════════════════════════════════════════════

NUMERIC_FILTER_COLS = [
    "Market Price", "% Change", "180 Day Average", "120 Day Average",
    "EPS", "P/E Ratio", "Book Value", "PBV",
    "30-Day Avg Volume", "Market Capitalization", "Shares Outstanding",
    "Price/Share Ratio",
]

FILTER_OPS = {
    "<": lambda col, val: col < val,
    "<=": lambda col, val: col <= val,
    "=": lambda col, val: col == val,
    ">=": lambda col, val: col >= val,
    ">": lambda col, val: col > val,
}


def render_home():
    st.title("NEPSE Dashboard")

    # ══════════════════════════════════════════════════════════════════════
    #  Section 1: Stock Market Overview
    # ══════════════════════════════════════════════════════════════════════
    st.header("Stock Market Overview")

    if st.button("Refresh Stock Prices", type="primary"):
        progress = st.progress(0, text="Fetching company data...")

        def on_company_progress(completed, total):
            pct = completed / total if total else 1.0
            progress.progress(pct, text=f"Scraping companies: {completed}/{total}")

        scrape_all_companies(max_workers=20, progress_callback=on_company_progress)
        progress.progress(1.0, text="Done! Stock data refreshed.")
        st.rerun()

    company_df = load_company_data()

    if company_df is not None and not company_df.empty:
        # ── Filters ──────────────────────────────────────────────────────
        with st.expander("Filters", expanded=False):
            # Stock code filter
            all_codes = sorted(company_df["code"].dropna().unique())
            selected_codes = st.multiselect(
                "Stock Code", options=all_codes, default=[],
                placeholder="Type to search stocks...",
            )

            # Sector filter
            sectors = sorted(company_df["Sector"].dropna().unique())
            selected_sectors = st.multiselect(
                "Sector", options=sectors, default=[],
                placeholder="All sectors",
            )

            # Numeric column filters
            st.markdown("**Numeric Filters**")

            if "num_filters" not in st.session_state:
                st.session_state.num_filters = []

            # Render existing filter rows
            available_cols = [c for c in NUMERIC_FILTER_COLS if c in company_df.columns]
            filters_to_apply = []

            for i, filt in enumerate(st.session_state.num_filters):
                fc1, fc2, fc3, fc4 = st.columns([3, 1, 2, 1])
                with fc1:
                    col = st.selectbox(
                        "Column", options=available_cols,
                        index=available_cols.index(filt["col"]) if filt["col"] in available_cols else 0,
                        key=f"filt_col_{i}",
                        label_visibility="collapsed",
                    )
                with fc2:
                    op = st.selectbox(
                        "Op", options=list(FILTER_OPS.keys()),
                        index=list(FILTER_OPS.keys()).index(filt["op"]),
                        key=f"filt_op_{i}",
                        label_visibility="collapsed",
                    )
                with fc3:
                    val = st.number_input(
                        "Value", value=filt["val"],
                        key=f"filt_val_{i}",
                        label_visibility="collapsed",
                    )
                with fc4:
                    if st.button("Remove", key=f"filt_rm_{i}"):
                        st.session_state.num_filters.pop(i)
                        st.rerun()

                filters_to_apply.append({"col": col, "op": op, "val": val})

            if st.button("+ Add Filter"):
                st.session_state.num_filters.append({
                    "col": available_cols[0] if available_cols else "",
                    "op": ">=",
                    "val": 0.0,
                })
                st.rerun()

            # Sync back
            st.session_state.num_filters = filters_to_apply

        # ── Apply filters ────────────────────────────────────────────────
        df = company_df.copy()

        if selected_codes:
            df = df[df["code"].isin(selected_codes)]

        if selected_sectors:
            df = df[df["Sector"].isin(selected_sectors)]

        for filt in filters_to_apply:
            col_name = filt["col"]
            if col_name in df.columns:
                op_fn = FILTER_OPS[filt["op"]]
                df = df[op_fn(df[col_name], filt["val"])].copy()

        # ── Display table ────────────────────────────────────────────────
        st.caption(f"Showing {len(df):,} of {len(company_df):,} stocks  —  click a row to view details")

        display = df.reset_index(drop=True)
        event = st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=500,
            on_select="rerun",
            selection_mode="single-row",
            key="stock_table",
        )

        # Navigate on row selection
        if event and event.selection and event.selection.rows:
            selected_row = event.selection.rows[0]
            code = display.iloc[selected_row]["code"]
            st.session_state.selected_symbol = code
            st.rerun()
    else:
        st.info("No company data found. Click **Refresh Stock Prices** to fetch the latest data.")

    # ══════════════════════════════════════════════════════════════════════
    #  Section 2: Floorsheet Scraper
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.header("Scrape Floorsheet")
    render_floorsheet_scrape_controls(key_prefix="home")

    # ── Scraped stocks list ──────────────────────────────────────────────
    st.divider()
    st.header("Scraped Stocks")

    symbols = get_scraped_symbols()
    if not symbols:
        st.info("No scraped floorsheet data found in `floorsheets/` yet.")
    else:
        n_cols = min(len(symbols), 8)
        for row_start in range(0, len(symbols), n_cols):
            row_syms = symbols[row_start:row_start + n_cols]
            cols = st.columns(n_cols)
            for j, sym in enumerate(row_syms):
                with cols[j]:
                    if st.button(sym, key=f"sym_{sym}", use_container_width=True):
                        st.session_state.selected_symbol = sym
                        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTING
# ═══════════════════════════════════════════════════════════════════════════════

if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Dashboard"

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Valuation"],
    index=["Dashboard", "Valuation"].index(st.session_state.nav_page),
    key="nav_radio",
)
st.session_state.nav_page = page

if page == "Valuation":
    render_valuation()
elif st.session_state.selected_symbol:
    render_stock_detail(st.session_state.selected_symbol)
else:
    render_home()
