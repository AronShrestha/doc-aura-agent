import pandas as pd
import numpy as np
import re
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("NEPSE STOCK MARKET ANALYSIS")
print("="*80)

# Load the data
print("\nLoading data...")
df = pd.read_csv('valid_company_details.csv', encoding='utf-8', on_bad_lines='skip')

# Clean column names
df.columns = df.columns.str.strip()

# Function to clean numeric values
def clean_numeric(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        value = value.replace(',', '').strip()
        match = re.search(r'-?\d+\.?\d*', value)
        if match:
            return float(match.group())
    try:
        return float(value)
    except:
        return np.nan

# Function to extract percentage
def extract_percentage(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        value = value.replace('%', '').strip()
        match = re.search(r'-?\d+\.?\d*', value)
        if match:
            return float(match.group())
    try:
        return float(value)
    except:
        return np.nan

# Function to extract high-low values
def extract_high_low(value):
    if pd.isna(value):
        return np.nan, np.nan
    if isinstance(value, str):
        if '-' in value:
            parts = value.split('-')
            try:
                high = float(parts[0].strip())
                low = float(parts[1].strip())
                return high, low
            except:
                return np.nan, np.nan
    return np.nan, np.nan

# Clean the data
print("Cleaning data...")
df['Shares Outstanding'] = df['Shares Outstanding'].apply(clean_numeric)
df['Market Price'] = df['Market Price'].apply(clean_numeric)
df['% Change'] = df['% Change'].apply(extract_percentage)
df['180 Day Average'] = df['180 Day Average'].apply(clean_numeric)
df['120 Day Average'] = df['120 Day Average'].apply(clean_numeric)
df['1 Year Yield'] = df['1 Year Yield'].apply(extract_percentage)
df['EPS'] = df['EPS'].apply(clean_numeric)
df['P/E Ratio'] = df['P/E Ratio'].apply(clean_numeric)
df['Book Value'] = df['Book Value'].apply(clean_numeric)
df['PBV'] = df['PBV'].apply(clean_numeric)
df['% Dividend'] = df['% Dividend'].apply(clean_numeric)
df['% Bonus'] = df['% Bonus'].apply(clean_numeric)
df['30-Day Avg Volume'] = df['30-Day Avg Volume'].apply(clean_numeric)
df['Market Capitalization'] = df['Market Capitalization'].apply(clean_numeric)

# Extract 52-week high and low
high_low = df['52 Weeks High - Low'].apply(extract_high_low)
df['52W High'] = high_low.apply(lambda x: x[0])
df['52W Low'] = high_low.apply(lambda x: x[1])

# Calculate additional metrics
df['Price to 52W High %'] = ((df['Market Price'] - df['52W High']) / df['52W High']) * 100
df['Price to 52W Low %'] = ((df['Market Price'] - df['52W Low']) / df['52W Low']) * 100
df['52W Range %'] = ((df['52W High'] - df['52W Low']) / df['52W Low']) * 100

# Remove rows with missing critical data
df_clean = df[df['Market Price'].notna() & df['Sector'].notna()].copy()

print(f"✓ Total companies analyzed: {len(df_clean)}")
print(f"✓ Total sectors: {df_clean['Sector'].nunique()}")

# Save cleaned data for visualization
df_clean.to_csv('cleaned_stock_data.csv', index=False)
print("✓ Saved cleaned data to: cleaned_stock_data.csv")

# Generate summary statistics
print("\n" + "="*80)
print("SUMMARY STATISTICS")
print("="*80)

summary_stats = {
    'Metric': [],
    'Value': []
}

# Market Overview
total_mcap = df_clean['Market Capitalization'].sum()
summary_stats['Metric'].extend([
    'Total Market Capitalization (Trillion NPR)',
    'Average Market Cap per Company (Billion NPR)',
    'Median Market Cap (Billion NPR)',
    'Total Companies',
    'Number of Sectors'
])
summary_stats['Value'].extend([
    f"{total_mcap/1e12:.2f}",
    f"{df_clean['Market Capitalization'].mean()/1e9:.2f}",
    f"{df_clean['Market Capitalization'].median()/1e9:.2f}",
    f"{len(df_clean)}",
    f"{df_clean['Sector'].nunique()}"
])

# Price Statistics
summary_stats['Metric'].extend([
    'Average Market Price (NPR)',
    'Median Market Price (NPR)',
    'Min Market Price (NPR)',
    'Max Market Price (NPR)'
])
summary_stats['Value'].extend([
    f"{df_clean['Market Price'].mean():.2f}",
    f"{df_clean['Market Price'].median():.2f}",
    f"{df_clean['Market Price'].min():.2f}",
    f"{df_clean['Market Price'].max():.2f}"
])

# % Change Statistics
change_data = df_clean['% Change'].dropna()
summary_stats['Metric'].extend([
    'Average Daily % Change (%)',
    'Median Daily % Change (%)',
    'Companies with Positive Change',
    'Companies with Negative Change'
])
positive_change = (change_data > 0).sum()
negative_change = (change_data < 0).sum()
summary_stats['Value'].extend([
    f"{change_data.mean():.2f}",
    f"{change_data.median():.2f}",
    f"{positive_change} ({positive_change/len(change_data)*100:.1f}%)",
    f"{negative_change} ({negative_change/len(change_data)*100:.1f}%)"
])

# Valuation Statistics
pe_data = df_clean[(df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & 
                   (df_clean['P/E Ratio'] < 100)]['P/E Ratio']
if len(pe_data) > 0:
    summary_stats['Metric'].extend([
        'Average P/E Ratio',
        'Median P/E Ratio',
        'Min P/E Ratio',
        'Max P/E Ratio'
    ])
    summary_stats['Value'].extend([
        f"{pe_data.mean():.2f}",
        f"{pe_data.median():.2f}",
        f"{pe_data.min():.2f}",
        f"{pe_data.max():.2f}"
    ])

pbv_data = df_clean[(df_clean['PBV'].notna()) & (df_clean['PBV'] > 0) & 
                    (df_clean['PBV'] < 10)]['PBV']
if len(pbv_data) > 0:
    summary_stats['Metric'].extend([
        'Average PBV',
        'Median PBV',
        'Companies with PBV < 1',
        'Companies with PBV > 2'
    ])
    summary_stats['Value'].extend([
        f"{pbv_data.mean():.2f}",
        f"{pbv_data.median():.2f}",
        f"{(pbv_data < 1).sum()}",
        f"{(pbv_data > 2).sum()}"
    ])

summary_df = pd.DataFrame(summary_stats)
summary_df.to_csv('summary_statistics.csv', index=False)
print("\n✓ Saved summary statistics to: summary_statistics.csv")

# Generate detailed insights
insights = []

insights.append("\n" + "="*80)
insights.append("DETAILED INSIGHTS REPORT")
insights.append("="*80)

# Basic Statistics
insights.append("\n1. MARKET OVERVIEW")
insights.append("-" * 80)
insights.append(f"Total Companies Analyzed: {len(df_clean)}")
insights.append(f"Total Sectors: {df_clean['Sector'].nunique()}")
insights.append(f"Total Market Capitalization: {total_mcap/1e12:.2f} Trillion NPR")
insights.append(f"Average Market Cap per Company: {df_clean['Market Capitalization'].mean()/1e9:.2f} Billion NPR")
insights.append(f"Median Market Cap: {df_clean['Market Capitalization'].median()/1e9:.2f} Billion NPR")

# Market Concentration
top_10_pct_companies = max(1, int(len(df_clean) * 0.1))
top_10_pct_mcap = df_clean.nlargest(top_10_pct_companies, 'Market Capitalization')['Market Capitalization'].sum()
concentration_pct = (top_10_pct_mcap / total_mcap) * 100 if total_mcap > 0 else 0
insights.append(f"\nMarket Concentration: Top 10% of companies hold {concentration_pct:.1f}% of total market cap")

# Price Analysis
insights.append("\n2. PRICE ANALYSIS")
insights.append("-" * 80)
insights.append(f"Average Market Price: {df_clean['Market Price'].mean():.2f} NPR")
insights.append(f"Median Market Price: {df_clean['Market Price'].median():.2f} NPR")
insights.append(f"Price Range: {df_clean['Market Price'].min():.2f} - {df_clean['Market Price'].max():.2f} NPR")

insights.append(f"\nAverage Daily % Change: {change_data.mean():.2f}%")
insights.append(f"Median Daily % Change: {change_data.median():.2f}%")
insights.append(f"Companies with Positive Change: {positive_change} ({positive_change/len(change_data)*100:.1f}%)")
insights.append(f"Companies with Negative Change: {negative_change} ({negative_change/len(change_data)*100:.1f}%)")

# Top Performers
top_gainers = df_clean.nlargest(10, '% Change')[['code', '% Change', 'Market Price', 'Sector']]
insights.append("\nTop 10 Gainers:")
for idx, row in top_gainers.iterrows():
    insights.append(f"  {row['code']}: {row['% Change']:.2f}% | Price: {row['Market Price']:.2f} NPR | Sector: {row['Sector']}")

top_losers = df_clean.nsmallest(10, '% Change')[['code', '% Change', 'Market Price', 'Sector']]
insights.append("\nTop 10 Losers:")
for idx, row in top_losers.iterrows():
    insights.append(f"  {row['code']}: {row['% Change']:.2f}% | Price: {row['Market Price']:.2f} NPR | Sector: {row['Sector']}")

# Valuation Metrics
insights.append("\n3. VALUATION METRICS")
insights.append("-" * 80)
if len(pe_data) > 0:
    insights.append(f"Average P/E Ratio: {pe_data.mean():.2f}")
    insights.append(f"Median P/E Ratio: {pe_data.median():.2f}")
    insights.append(f"P/E Ratio Range: {pe_data.min():.2f} - {pe_data.max():.2f}")

if len(pbv_data) > 0:
    insights.append(f"\nAverage PBV: {pbv_data.mean():.2f}")
    insights.append(f"Median PBV: {pbv_data.median():.2f}")
    insights.append(f"Companies with PBV < 1 (Potentially Undervalued): {(pbv_data < 1).sum()}")
    insights.append(f"Companies with PBV > 2: {(pbv_data > 2).sum()}")

eps_data = df_clean[df_clean['EPS'].notna()]['EPS']
if len(eps_data) > 0:
    positive_eps = (eps_data > 0).sum()
    negative_eps = (eps_data < 0).sum()
    insights.append(f"\nCompanies with Positive EPS: {positive_eps} ({positive_eps/len(eps_data)*100:.1f}%)")
    insights.append(f"Companies with Negative EPS: {negative_eps} ({negative_eps/len(eps_data)*100:.1f}%)")
    insights.append(f"Average EPS: {eps_data.mean():.2f}")
    insights.append(f"Median EPS: {eps_data.median():.2f}")

# Sector Analysis
insights.append("\n4. SECTOR ANALYSIS")
insights.append("-" * 80)
sector_stats = df_clean.groupby('Sector').agg({
    'Market Price': 'mean',
    '% Change': 'mean',
    'Market Capitalization': ['sum', 'mean', 'count']
}).round(2)

insights.append("\nSector Performance Summary:")
for sector in sector_stats.index:
    count = int(sector_stats.loc[sector, ('Market Capitalization', 'count')])
    avg_price = sector_stats.loc[sector, ('Market Price', 'mean')]
    avg_change = sector_stats.loc[sector, ('% Change', 'mean')]
    total_mcap = sector_stats.loc[sector, ('Market Capitalization', 'sum')]
    avg_mcap = sector_stats.loc[sector, ('Market Capitalization', 'mean')]
    
    insights.append(f"\n{sector}:")
    insights.append(f"  Companies: {count}")
    insights.append(f"  Avg Price: {avg_price:.2f} NPR")
    insights.append(f"  Avg % Change: {avg_change:.2f}%")
    insights.append(f"  Total Market Cap: {total_mcap/1e9:.2f} Billion NPR")
    insights.append(f"  Avg Market Cap: {avg_mcap/1e9:.2f} Billion NPR")

# Save sector analysis
sector_stats.to_csv('sector_analysis.csv')
print("✓ Saved sector analysis to: sector_analysis.csv")

# Yield and Dividend Analysis
insights.append("\n5. YIELD & DIVIDEND ANALYSIS")
insights.append("-" * 80)
yield_data = df_clean[df_clean['1 Year Yield'].notna()]['1 Year Yield']
if len(yield_data) > 0:
    insights.append(f"Average 1 Year Yield: {yield_data.mean():.2f}%")
    insights.append(f"Median 1 Year Yield: {yield_data.median():.2f}%")
    insights.append(f"Yield Range: {yield_data.min():.2f}% - {yield_data.max():.2f}%")
    
    top_yielders = df_clean[df_clean['1 Year Yield'].notna()].nlargest(10, '1 Year Yield')[['code', '1 Year Yield', 'Sector']]
    insights.append("\nTop 10 Companies by Yield:")
    for idx, row in top_yielders.iterrows():
        insights.append(f"  {row['code']}: {row['1 Year Yield']:.2f}% | Sector: {row['Sector']}")

div_data = df_clean[df_clean['% Dividend'].notna()]['% Dividend']
if len(div_data) > 0:
    insights.append(f"\nAverage % Dividend: {div_data.mean():.2f}%")
    insights.append(f"Median % Dividend: {div_data.median():.2f}%")
    insights.append(f"Companies Paying Dividends: {len(div_data)}")

# Volume Analysis
insights.append("\n6. VOLUME ANALYSIS")
insights.append("-" * 80)
volume_data = df_clean[df_clean['30-Day Avg Volume'].notna() & (df_clean['30-Day Avg Volume'] > 0)]['30-Day Avg Volume']
if len(volume_data) > 0:
    insights.append(f"Average 30-Day Volume: {volume_data.mean():,.0f}")
    insights.append(f"Median 30-Day Volume: {volume_data.median():,.0f}")
    
    top_volume = df_clean[df_clean['30-Day Avg Volume'].notna()].nlargest(10, '30-Day Avg Volume')[['code', '30-Day Avg Volume', 'Sector']]
    insights.append("\nTop 10 Companies by Volume:")
    for idx, row in top_volume.iterrows():
        insights.append(f"  {row['code']}: {row['30-Day Avg Volume']:,.0f} | Sector: {row['Sector']}")

# 52-Week Analysis
insights.append("\n7. 52-WEEK HIGH/LOW ANALYSIS")
insights.append("-" * 80)
df_52w = df_clean[df_clean['52W High'].notna() & df_clean['52W Low'].notna()].copy()
if len(df_52w) > 0:
    df_52w['Price Position'] = ((df_52w['Market Price'] - df_52w['52W Low']) / 
                                (df_52w['52W High'] - df_52w['52W Low'])) * 100
    insights.append(f"Companies near 52W High (>90%): {(df_52w['Price Position'] > 90).sum()}")
    insights.append(f"Companies near 52W Low (<10%): {(df_52w['Price Position'] < 10).sum()}")
    insights.append(f"Average Price Position: {df_52w['Price Position'].mean():.1f}%")
    insights.append(f"Median Price Position: {df_52w['Price Position'].median():.1f}%")
    
    near_high = df_52w[df_52w['Price Position'] > 90].nlargest(5, 'Price Position')[['code', 'Price Position', 'Market Price', '52W High']]
    if len(near_high) > 0:
        insights.append("\nCompanies Closest to 52W High:")
        for idx, row in near_high.iterrows():
            insights.append(f"  {row['code']}: {row['Price Position']:.1f}% | Current: {row['Market Price']:.2f} | High: {row['52W High']:.2f}")
    
    near_low = df_52w[df_52w['Price Position'] < 10].nsmallest(5, 'Price Position')[['code', 'Price Position', 'Market Price', '52W Low']]
    if len(near_low) > 0:
        insights.append("\nCompanies Closest to 52W Low:")
        for idx, row in near_low.iterrows():
            insights.append(f"  {row['code']}: {row['Price Position']:.1f}% | Current: {row['Market Price']:.2f} | Low: {row['52W Low']:.2f}")

# Investment Insights
insights.append("\n8. INVESTMENT INSIGHTS")
insights.append("-" * 80)

# Undervalued stocks
undervalued_stocks = df_clean[
    (df_clean['PBV'].notna()) & (df_clean['PBV'] < 1) &
    (df_clean['EPS'].notna()) & (df_clean['EPS'] > 0) &
    (df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & (df_clean['P/E Ratio'] < 30)
].nlargest(10, 'Market Capitalization')[['code', 'Market Price', 'PBV', 'P/E Ratio', 'EPS', 'Sector']]

if len(undervalued_stocks) > 0:
    insights.append("\nPotentially Undervalued Stocks (PBV < 1, Positive EPS, P/E < 30):")
    undervalued_stocks.to_csv('undervalued_stocks.csv', index=False)
    for idx, row in undervalued_stocks.iterrows():
        insights.append(f"  {row['code']}: Price={row['Market Price']:.2f}, PBV={row['PBV']:.2f}, P/E={row['P/E Ratio']:.2f}, EPS={row['EPS']:.2f}, Sector={row['Sector']}")
    print("✓ Saved undervalued stocks to: undervalued_stocks.csv")

# High yield stocks
high_yield_stocks = df_clean[
    (df_clean['1 Year Yield'].notna()) & (df_clean['1 Year Yield'] > 5) &
    (df_clean['Market Capitalization'].notna())
].nlargest(10, 'Market Capitalization')[['code', '1 Year Yield', 'Market Price', 'P/E Ratio', 'Sector']]

if len(high_yield_stocks) > 0:
    insights.append("\nHigh Yield Stocks (>5% yield):")
    high_yield_stocks.to_csv('high_yield_stocks.csv', index=False)
    for idx, row in high_yield_stocks.iterrows():
        pe_str = f"{row['P/E Ratio']:.2f}" if pd.notna(row['P/E Ratio']) else 'N/A'
        insights.append(f"  {row['code']}: Yield={row['1 Year Yield']:.2f}%, Price={row['Market Price']:.2f}, P/E={pe_str}, Sector={row['Sector']}")
    print("✓ Saved high yield stocks to: high_yield_stocks.csv")

# Growth stocks
growth_stocks = df_clean[
    (df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 15) & (df_clean['P/E Ratio'] < 50) &
    (df_clean['EPS'].notna()) & (df_clean['EPS'] > 0) &
    (df_clean['% Change'].notna()) & (df_clean['% Change'] > 0)
].nlargest(10, '% Change')[['code', 'P/E Ratio', '% Change', 'EPS', 'Market Price', 'Sector']]

if len(growth_stocks) > 0:
    insights.append("\nPotential Growth Stocks (P/E 15-50, Positive EPS, Positive Change):")
    growth_stocks.to_csv('growth_stocks.csv', index=False)
    for idx, row in growth_stocks.iterrows():
        insights.append(f"  {row['code']}: P/E={row['P/E Ratio']:.2f}, Change={row['% Change']:.2f}%, EPS={row['EPS']:.2f}, Price={row['Market Price']:.2f}, Sector={row['Sector']}")
    print("✓ Saved growth stocks to: growth_stocks.csv")

# Top companies by market cap
top_companies = df_clean.nlargest(20, 'Market Capitalization')[['code', 'Market Capitalization', 'Market Price', '% Change', 'P/E Ratio', 'Sector']]
top_companies['Market Cap (Billions)'] = top_companies['Market Capitalization'] / 1e9
top_companies.to_csv('top_companies_by_mcap.csv', index=False)
print("✓ Saved top 20 companies to: top_companies_by_mcap.csv")

# Print all insights
for insight in insights:
    print(insight)

# Save insights to file
with open('stock_analysis_insights.txt', 'w', encoding='utf-8') as f:
    for insight in insights:
        f.write(insight + '\n')

print("\n" + "="*80)
print("Analysis complete!")
print("="*80)
print("\nGenerated Files:")
print("  1. cleaned_stock_data.csv - Full cleaned dataset")
print("  2. summary_statistics.csv - Summary statistics")
print("  3. sector_analysis.csv - Sector-wise analysis")
print("  4. undervalued_stocks.csv - Potentially undervalued stocks")
print("  5. high_yield_stocks.csv - High yield stocks")
print("  6. growth_stocks.csv - Potential growth stocks")
print("  7. top_companies_by_mcap.csv - Top 20 companies by market cap")
print("  8. stock_analysis_insights.txt - Detailed insights report")
print("\nNote: To generate visualizations, install matplotlib and seaborn:")
print("  pip install matplotlib seaborn")
print("  Then run: python analyze_stocks.py")
