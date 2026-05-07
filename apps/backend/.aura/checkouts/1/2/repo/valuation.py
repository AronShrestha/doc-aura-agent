"""NEPSE Stock Valuation & Normalization Tool.

Computes financial ratios, Z-score normalisation within sectors,
direction-adjusted composite scores, and renders tables / charts
inside the Streamlit dashboard.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

RATIO_COLS = [
    "P_E", "P_B", "P_S", "EV_EBITDA",
    "FCF_Yield", "Dividend_Yield", "ROE",
]

# Ratios where *lower* means cheaper → z-score is multiplied by -1.
INVERT_RATIOS = {"P_E", "P_B", "P_S", "EV_EBITDA"}

SECTOR_MAP = {
    "Development Bank Limited": "Development Banks",
    "Hydro Power": "Hydropower",
    "Hotels And Tourism": "Hotels and Tourism",
    "Tradings": "Trading",
    "Finance": "Finance Companies",
}

VALID_SECTORS = {
    "Commercial Banks",
    "Development Banks",
    "Finance Companies",
    "Microfinance",
    "Hydropower",
    "Life Insurance",
    "Non-Life Insurance",
    "Manufacturing And Processing",
    "Hotels and Tourism",
    "Trading",
    "Others",
}

FLAG_THRESHOLDS = [
    (1.5, float("inf"), "DEEP VALUE"),
    (0.5, 1.5, "FAIRLY CHEAP"),
    (-0.5, 0.5, "FAIRLY PRICED"),
    (-1.5, -0.5, "EXPENSIVE"),
    (float("-inf"), -1.5, "OVERVALUED"),
]

COMPANY_DATA_PATH = Path("company_details.csv")

OPTIONAL_UPLOAD_COLS = [
    "revenue_per_share",
    "free_cash_flow_per_share",
    "total_debt",
    "cash_and_equivalents",
    "ebitda",
    "net_profit",
    "total_equity",
]


# ── Data loading ─────────────────────────────────────────────────────────────

def load_valuation_data(uploaded_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Load company_details.csv, normalise column names, and optionally merge
    an uploaded CSV that provides extra financial fields."""

    if not COMPANY_DATA_PATH.exists():
        return pd.DataFrame()

    raw = pd.read_csv(COMPANY_DATA_PATH)

    df = pd.DataFrame()
    df["code"] = raw["code"]
    df["company_name"] = raw["Company Name"]
    df["sector"] = raw["Sector"].map(lambda s: SECTOR_MAP.get(s, s))
    df["stock_price"] = pd.to_numeric(raw["Market Price"], errors="coerce")
    df["EPS"] = pd.to_numeric(raw["EPS"], errors="coerce")
    df["book_value_per_share"] = pd.to_numeric(raw["Book Value"], errors="coerce")
    df["pct_dividend"] = pd.to_numeric(raw.get("% Dividend", pd.Series(dtype=float)), errors="coerce")
    df["pct_bonus"] = pd.to_numeric(raw.get("% Bonus", pd.Series(dtype=float)), errors="coerce")
    df["shares_outstanding"] = pd.to_numeric(raw["Shares Outstanding"], errors="coerce")
    df["market_cap"] = pd.to_numeric(raw["Market Capitalization"], errors="coerce")

    # NEPSE % Dividend is cash dividend as % of par value (NPR 100).
    df["annual_dividend_per_share"] = df["pct_dividend"]

    # Derive fields we can
    df["net_profit"] = df["EPS"] * df["shares_outstanding"]
    df["total_equity"] = df["book_value_per_share"] * df["shares_outstanding"]

    # Fill market_cap if missing
    mask = df["market_cap"].isna() | (df["market_cap"] == 0)
    df.loc[mask, "market_cap"] = df.loc[mask, "stock_price"] * df.loc[mask, "shares_outstanding"]

    # Merge optional uploaded data (keyed on code)
    if uploaded_df is not None and not uploaded_df.empty:
        upload = uploaded_df.copy()
        if "code" not in upload.columns:
            st.warning("Uploaded CSV must have a 'code' column to merge.")
        else:
            for col in OPTIONAL_UPLOAD_COLS:
                if col in upload.columns:
                    upload[col] = pd.to_numeric(upload[col], errors="coerce")
            merge_cols = ["code"] + [c for c in OPTIONAL_UPLOAD_COLS if c in upload.columns]
            df = df.merge(upload[merge_cols], on="code", how="left", suffixes=("", "_upload"))
            # Prefer uploaded net_profit / total_equity over derived
            for col in ("net_profit", "total_equity"):
                up_col = f"{col}_upload"
                if up_col in df.columns:
                    df[col] = df[up_col].combine_first(df[col])
                    df.drop(columns=[up_col], inplace=True)

    # Filter to valid sectors
    df = df[df["sector"].isin(VALID_SECTORS)].reset_index(drop=True)

    return df


# ── Ratio computation ────────────────────────────────────────────────────────

def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """Divide, returning NaN when denominator is zero or NaN."""
    result = num / den
    result[den.isna() | (den == 0)] = np.nan
    return result


def compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add ratio columns to *df*. Returns a copy."""
    df = df.copy()

    df["P_E"] = _safe_div(df["stock_price"], df["EPS"])
    df["P_B"] = _safe_div(df["stock_price"], df["book_value_per_share"])

    if "revenue_per_share" in df.columns:
        df["P_S"] = _safe_div(df["stock_price"], df["revenue_per_share"])
    else:
        df["P_S"] = np.nan

    # EV = market_cap + total_debt - cash_and_equivalents
    if "total_debt" in df.columns and "cash_and_equivalents" in df.columns:
        df["EV"] = df["market_cap"] + df["total_debt"].fillna(0) - df["cash_and_equivalents"].fillna(0)
    else:
        df["EV"] = np.nan

    if "ebitda" in df.columns:
        df["EV_EBITDA"] = _safe_div(df["EV"], df["ebitda"])
    else:
        df["EV_EBITDA"] = np.nan

    if "free_cash_flow_per_share" in df.columns:
        df["FCF_Yield"] = _safe_div(df["free_cash_flow_per_share"], df["stock_price"]) * 100
    else:
        df["FCF_Yield"] = np.nan

    df["Dividend_Yield"] = _safe_div(df["annual_dividend_per_share"], df["stock_price"]) * 100

    df["ROE"] = _safe_div(df["net_profit"], df["total_equity"]) * 100

    # Negative P/E or P/B are non-meaningful; treat as NaN
    for col in ("P_E", "P_B"):
        df.loc[df[col] <= 0, col] = np.nan

    return df


# ── Z-score normalisation ────────────────────────────────────────────────────

def zscore_normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Compute z-scores per ratio within each sector, apply direction
    adjustment, and return a DataFrame with z_* columns."""

    df = df.copy()
    z_cols = [f"z_{r}" for r in RATIO_COLS]
    for zc in z_cols:
        df[zc] = np.nan

    for _sector, grp in df.groupby("sector"):
        idx = grp.index
        for ratio in RATIO_COLS:
            vals = grp[ratio].dropna()
            if len(vals) < 2:
                continue
            mean = vals.mean()
            std = vals.std(ddof=0)
            if std == 0:
                continue
            z = (grp[ratio] - mean) / std
            if ratio in INVERT_RATIOS:
                z = z * -1
            df.loc[idx, f"z_{ratio}"] = z

    return df


# ── Composite score & flags ──────────────────────────────────────────────────

def compute_composite(df: pd.DataFrame) -> pd.DataFrame:
    """Compute composite_score as mean of available adjusted z-scores."""
    df = df.copy()
    z_cols = [f"z_{r}" for r in RATIO_COLS]
    z_matrix = df[z_cols]
    df["valid_ratios"] = z_matrix.notna().sum(axis=1)
    df["composite_score"] = z_matrix.mean(axis=1, skipna=True)
    df.loc[df["valid_ratios"] == 0, "composite_score"] = np.nan
    return df


def assign_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add valuation_flag and alert columns."""
    df = df.copy()

    def _flag(score):
        if pd.isna(score):
            return "N/A"
        for lo, hi, label in FLAG_THRESHOLDS:
            if lo <= score < hi:
                return label
            if score == hi and hi == float("inf"):
                return label
        return "N/A"

    df["valuation_flag"] = df["composite_score"].apply(_flag)

    alerts = []
    for _, row in df.iterrows():
        row_alerts = []
        if pd.notna(row.get("shares_outstanding")) and row["shares_outstanding"] < 1_000_000:
            row_alerts.append("LOW LIQUIDITY")
        alerts.append("; ".join(row_alerts) if row_alerts else "")
    df["alerts"] = alerts

    return df


# ── Sector summary ───────────────────────────────────────────────────────────

def build_sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build sector-level statistics table."""
    records = []
    for sector, grp in df.groupby("sector"):
        row = {"sector": sector}
        for ratio in RATIO_COLS:
            vals = grp[ratio].dropna()
            row[f"{ratio}_mean"] = vals.mean() if len(vals) else np.nan
            row[f"{ratio}_std"] = vals.std(ddof=0) if len(vals) >= 2 else np.nan

        valid = grp.dropna(subset=["composite_score"])
        if not valid.empty:
            row["cheapest"] = valid.loc[valid["composite_score"].idxmax(), "company_name"]
            row["most_expensive"] = valid.loc[valid["composite_score"].idxmin(), "company_name"]
        else:
            row["cheapest"] = "N/A"
            row["most_expensive"] = "N/A"
        records.append(row)

    return pd.DataFrame(records)


# ── Full pipeline ────────────────────────────────────────────────────────────

def run_valuation(uploaded_df: pd.DataFrame | None = None):
    """Execute the full valuation pipeline and return result DataFrames."""
    df = load_valuation_data(uploaded_df)
    if df.empty:
        return None

    df = compute_ratios(df)
    df = zscore_normalize(df)
    df = compute_composite(df)
    df = assign_flags(df)

    sector_summary = build_sector_summary(df)

    return {
        "full": df,
        "sector_summary": sector_summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Streamlit page
# ═══════════════════════════════════════════════════════════════════════════════

def render_valuation():
    """Render the Valuation & Normalization page inside the dashboard."""

    st.title("Stock Valuation & Normalization")
    st.caption(
        "Z-score based relative valuation across NEPSE sectors. "
        "Positive composite score = cheaper / better quality within its sector."
    )

    # ── Optional CSV upload ──────────────────────────────────────────────
    with st.expander("Upload additional financial data (optional)"):
        st.markdown(
            "Upload a CSV with a **code** column and any of: "
            "`revenue_per_share`, `free_cash_flow_per_share`, `total_debt`, "
            "`cash_and_equivalents`, `ebitda`, `net_profit`, `total_equity`. "
            "These enable P/S, EV/EBITDA, and FCF Yield ratios."
        )
        uploaded = st.file_uploader("CSV file", type=["csv"], key="val_upload")

    uploaded_df = None
    if uploaded is not None:
        try:
            uploaded_df = pd.read_csv(uploaded)
        except (pd.errors.ParserError, ValueError) as e:
            st.error(f"Failed to read uploaded CSV: {e}")

    # ── Run pipeline ─────────────────────────────────────────────────────
    result = run_valuation(uploaded_df)
    if result is None:
        st.warning(
            "No company data available. Go to the Dashboard page and click "
            "**Refresh Stock Prices** first."
        )
        return

    df = result["full"]
    sector_summary = result["sector_summary"]

    # ── Sector filter ────────────────────────────────────────────────────
    all_sectors = sorted(df["sector"].unique())
    selected_sectors = st.multiselect(
        "Filter by sector", options=all_sectors, default=[],
        placeholder="All sectors",
        key="val_sector_filter",
    )
    if selected_sectors:
        df = df[df["sector"].isin(selected_sectors)].copy()
        sector_summary = sector_summary[sector_summary["sector"].isin(selected_sectors)].copy()

    if df.empty:
        st.info("No companies match the selected filters.")
        return

    # ── Determine which ratios have data ─────────────────────────────────
    available_ratios = [r for r in RATIO_COLS if df[r].notna().any()]
    available_z = [f"z_{r}" for r in available_ratios]

    # ── Summary metrics ──────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Companies", len(df))
    m2.metric("Sectors", df["sector"].nunique())
    m3.metric("Ratios Available", len(available_ratios))
    valid_scores = df["composite_score"].dropna()
    m4.metric(
        "Deep Value Stocks",
        int((valid_scores > 1.5).sum()) if not valid_scores.empty else 0,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  Table 1 — Raw Ratios
    # ══════════════════════════════════════════════════════════════════════
    st.header("Raw Ratios")

    ratio_display = df[["code", "company_name", "sector", "stock_price"] + available_ratios].copy()
    ratio_display = ratio_display.sort_values("code").reset_index(drop=True)

    col_config_ratios = {
        "code": st.column_config.TextColumn("Code"),
        "company_name": st.column_config.TextColumn("Company"),
        "sector": st.column_config.TextColumn("Sector"),
        "stock_price": st.column_config.NumberColumn("Price", format="%.2f"),
    }
    for r in available_ratios:
        col_config_ratios[r] = st.column_config.NumberColumn(r, format="%.2f")

    st.dataframe(
        ratio_display,
        column_config=col_config_ratios,
        use_container_width=True,
        hide_index=True,
        height=450,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  Table 2 — Adjusted Z-Scores
    # ══════════════════════════════════════════════════════════════════════
    st.header("Adjusted Z-Scores")

    z_display = df[["code", "company_name", "sector"] + available_z].copy()
    z_display = z_display.sort_values("code").reset_index(drop=True)

    col_config_z = {
        "code": st.column_config.TextColumn("Code"),
        "company_name": st.column_config.TextColumn("Company"),
        "sector": st.column_config.TextColumn("Sector"),
    }
    for zc in available_z:
        col_config_z[zc] = st.column_config.NumberColumn(
            zc.replace("z_", ""), format="%.3f",
        )

    st.dataframe(
        z_display,
        column_config=col_config_z,
        use_container_width=True,
        hide_index=True,
        height=450,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  Table 3 — Composite Score Ranking
    # ══════════════════════════════════════════════════════════════════════
    st.header("Composite Score Ranking")

    ranking = (
        df[["code", "company_name", "sector", "composite_score",
            "valid_ratios", "valuation_flag", "alerts"]]
        .dropna(subset=["composite_score"])
        .sort_values("composite_score", ascending=False)
        .reset_index(drop=True)
    )
    ranking.insert(0, "rank", range(1, len(ranking) + 1))

    def _flag_color(flag):
        return {
            "DEEP VALUE": "background-color: #065f46; color: white",
            "FAIRLY CHEAP": "background-color: #059669; color: white",
            "FAIRLY PRICED": "background-color: #6b7280; color: white",
            "EXPENSIVE": "background-color: #dc2626; color: white",
            "OVERVALUED": "background-color: #7f1d1d; color: white",
        }.get(flag, "")

    st.dataframe(
        ranking,
        column_config={
            "rank": st.column_config.NumberColumn("#", format="%d"),
            "code": st.column_config.TextColumn("Code"),
            "company_name": st.column_config.TextColumn("Company"),
            "sector": st.column_config.TextColumn("Sector"),
            "composite_score": st.column_config.NumberColumn(
                "Composite Score", format="%.3f",
            ),
            "valid_ratios": st.column_config.NumberColumn(
                "Ratios Used", format="%d",
            ),
            "valuation_flag": st.column_config.TextColumn("Flag"),
            "alerts": st.column_config.TextColumn("Alerts"),
        },
        use_container_width=True,
        hide_index=True,
        height=500,
    )

    # Quick stats
    flag_counts = ranking["valuation_flag"].value_counts()
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    fc1.metric("Deep Value", flag_counts.get("DEEP VALUE", 0))
    fc2.metric("Fairly Cheap", flag_counts.get("FAIRLY CHEAP", 0))
    fc3.metric("Fairly Priced", flag_counts.get("FAIRLY PRICED", 0))
    fc4.metric("Expensive", flag_counts.get("EXPENSIVE", 0))
    fc5.metric("Overvalued", flag_counts.get("OVERVALUED", 0))

    # ══════════════════════════════════════════════════════════════════════
    #  Table 4 — Sector Summary
    # ══════════════════════════════════════════════════════════════════════
    st.header("Sector Summary")

    summary_cols = ["sector"]
    col_config_summary = {
        "sector": st.column_config.TextColumn("Sector"),
    }
    for r in available_ratios:
        mean_c = f"{r}_mean"
        std_c = f"{r}_std"
        if mean_c in sector_summary.columns:
            summary_cols.append(mean_c)
            col_config_summary[mean_c] = st.column_config.NumberColumn(
                f"{r} Mean", format="%.2f",
            )
        if std_c in sector_summary.columns:
            summary_cols.append(std_c)
            col_config_summary[std_c] = st.column_config.NumberColumn(
                f"{r} Std", format="%.2f",
            )

    summary_cols += ["cheapest", "most_expensive"]
    col_config_summary["cheapest"] = st.column_config.TextColumn("Cheapest")
    col_config_summary["most_expensive"] = st.column_config.TextColumn("Most Expensive")

    summary_display = sector_summary[
        [c for c in summary_cols if c in sector_summary.columns]
    ].sort_values("sector").reset_index(drop=True)

    st.dataframe(
        summary_display,
        column_config=col_config_summary,
        use_container_width=True,
        hide_index=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  Chart 1 — Composite Score Bar Chart
    # ══════════════════════════════════════════════════════════════════════
    st.header("Composite Score Distribution")

    chart_df = ranking.copy()

    sector_colors = px.colors.qualitative.Set2
    unique_sectors = sorted(chart_df["sector"].unique())
    color_map = {s: sector_colors[i % len(sector_colors)] for i, s in enumerate(unique_sectors)}

    # Limit to top/bottom for readability when many companies
    max_bars = st.slider(
        "Max companies to display", min_value=10, max_value=len(chart_df),
        value=min(50, len(chart_df)), step=5, key="val_max_bars",
    )
    if len(chart_df) > max_bars:
        top_n = max_bars // 2
        bottom_n = max_bars - top_n
        chart_df = pd.concat([chart_df.head(top_n), chart_df.tail(bottom_n)])

    fig_bar = go.Figure()
    for sector in unique_sectors:
        sdf = chart_df[chart_df["sector"] == sector]
        if sdf.empty:
            continue
        fig_bar.add_trace(go.Bar(
            y=sdf["code"],
            x=sdf["composite_score"],
            orientation="h",
            name=sector,
            marker_color=color_map[sector],
            hovertemplate=(
                "<b>%{y}</b> (%{customdata[0]})<br>"
                "Score: %{x:.3f}<br>"
                "Flag: %{customdata[1]}"
                "<extra></extra>"
            ),
            customdata=np.column_stack([
                sdf["company_name"].values,
                sdf["valuation_flag"].values,
            ]),
        ))

    fig_bar.add_vline(x=0, line_dash="dash", line_color="gray", line_width=0.8)
    fig_bar.update_layout(
        yaxis=dict(autorange="reversed"),
        xaxis_title="Composite Score",
        height=max(400, len(chart_df) * 22),
        margin=dict(l=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        barmode="overlay",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    #  Chart 2 — Sector Heatmap
    # ══════════════════════════════════════════════════════════════════════
    st.header("Valuation Heatmap")

    heatmap_sector = st.selectbox(
        "Select sector for heatmap",
        options=["All Sectors"] + sorted(df["sector"].unique()),
        key="val_heatmap_sector",
    )

    hm_df = df.copy()
    if heatmap_sector != "All Sectors":
        hm_df = hm_df[hm_df["sector"] == heatmap_sector]

    hm_df = hm_df.dropna(subset=["composite_score"]).sort_values(
        "composite_score", ascending=False,
    )

    if len(hm_df) > 80:
        hm_df = hm_df.head(80)
        st.caption("Showing top 80 companies by composite score for readability.")

    z_matrix = hm_df.set_index("code")[available_z].rename(
        columns={zc: zc.replace("z_", "") for zc in available_z}
    )

    if z_matrix.empty or z_matrix.shape[1] == 0:
        st.info("Not enough data to render heatmap.")
    else:
        fig_hm = go.Figure(data=go.Heatmap(
            z=z_matrix.values,
            x=z_matrix.columns.tolist(),
            y=z_matrix.index.tolist(),
            colorscale=[
                [0.0, "#b91c1c"],
                [0.25, "#ef4444"],
                [0.5, "#f3f4f6"],
                [0.75, "#34d399"],
                [1.0, "#065f46"],
            ],
            zmid=0,
            colorbar=dict(title="Z-Score"),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "%{x}: %{z:.3f}"
                "<extra></extra>"
            ),
        ))
        fig_hm.update_layout(
            yaxis=dict(autorange="reversed", dtick=1),
            xaxis=dict(side="top"),
            height=max(400, len(z_matrix) * 22),
            margin=dict(l=10, t=80),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

    # ── Download button ──────────────────────────────────────────────────
    st.divider()
    st.subheader("Export")

    export_df = df[
        ["code", "company_name", "sector", "stock_price"]
        + available_ratios + available_z
        + ["composite_score", "valid_ratios", "valuation_flag", "alerts"]
    ].sort_values("composite_score", ascending=False)

    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download full results as CSV",
        data=csv_bytes,
        file_name="nepse_valuation_results.csv",
        mime="text/csv",
    )
