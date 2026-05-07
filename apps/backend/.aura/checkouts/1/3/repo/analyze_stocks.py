import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (15, 10)
plt.rcParams['font.size'] = 10

# Load the data
print("Loading data...")
df = pd.read_csv('valid_company_details.csv', encoding='utf-8', on_bad_lines='skip')

# Clean column names
df.columns = df.columns.str.strip()

# Function to clean numeric values
def clean_numeric(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        # Remove commas, spaces, and extract numbers
        value = value.replace(',', '').strip()
        # Extract first number if multiple numbers exist
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
        # Remove % sign and extract number
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

print(f"Total companies analyzed: {len(df_clean)}")
print(f"Total sectors: {df_clean['Sector'].nunique()}")

# Create visualizations
print("Creating visualizations...")

# 1. Market Capitalization Distribution
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Market Capitalization', fontsize=16, fontweight='bold')

# Market Cap distribution (log scale)
ax1 = axes[0, 0]
market_cap_log = np.log10(df_clean['Market Capitalization'].dropna() + 1)
ax1.hist(market_cap_log, bins=30, edgecolor='black', alpha=0.7, color='steelblue')
ax1.set_xlabel('Log10(Market Capitalization)', fontweight='bold')
ax1.set_ylabel('Number of Companies', fontweight='bold')
ax1.set_title('Market Capitalization Distribution (Log Scale)', fontweight='bold')
ax1.grid(True, alpha=0.3)

# Top 20 companies by market cap
ax2 = axes[0, 1]
top_20 = df_clean.nlargest(20, 'Market Capitalization')[['code', 'Market Capitalization']]
top_20['Market Cap (Billions)'] = top_20['Market Capitalization'] / 1e9
bars = ax2.barh(range(len(top_20)), top_20['Market Cap (Billions)'], color='coral')
ax2.set_yticks(range(len(top_20)))
ax2.set_yticklabels(top_20['code'], fontsize=9)
ax2.set_xlabel('Market Capitalization (Billions NPR)', fontweight='bold')
ax2.set_title('Top 20 Companies by Market Cap', fontweight='bold')
ax2.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, (idx, row) in enumerate(top_20.iterrows()):
    ax2.text(row['Market Cap (Billions)'], i, f'{row["Market Cap (Billions)"]:.2f}B', 
             va='center', fontsize=8)

# Market Cap by Sector
ax3 = axes[1, 0]
sector_mcap = df_clean.groupby('Sector')['Market Capitalization'].sum().sort_values(ascending=False)
bars = ax3.bar(range(len(sector_mcap)), sector_mcap / 1e9, color='mediumseagreen')
ax3.set_xticks(range(len(sector_mcap)))
ax3.set_xticklabels(sector_mcap.index, rotation=45, ha='right', fontsize=9)
ax3.set_ylabel('Total Market Cap (Billions NPR)', fontweight='bold')
ax3.set_title('Market Capitalization by Sector', fontweight='bold')
ax3.grid(True, alpha=0.3, axis='y')
# Add value labels
for i, (sector, value) in enumerate(sector_mcap.items()):
    ax3.text(i, value/1e9, f'{value/1e9:.1f}B', ha='center', va='bottom', fontsize=8, rotation=90)

# Market Cap concentration
ax4 = axes[1, 1]
total_mcap = df_clean['Market Capitalization'].sum()
top_10_pct = df_clean.nlargest(int(len(df_clean) * 0.1), 'Market Capitalization')['Market Capitalization'].sum()
top_25_pct = df_clean.nlargest(int(len(df_clean) * 0.25), 'Market Capitalization')['Market Capitalization'].sum()
concentration = [top_10_pct/total_mcap*100, top_25_pct/total_mcap*100, 
                 (total_mcap-top_25_pct)/total_mcap*100]
labels = ['Top 10%', 'Next 15%', 'Remaining 75%']
colors = ['#ff6b6b', '#4ecdc4', '#95a5a6']
ax4.pie(concentration, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
ax4.set_title('Market Cap Concentration', fontweight='bold')

plt.tight_layout()
plt.savefig('1_market_capitalization.png', dpi=300, bbox_inches='tight')
print("Saved: 1_market_capitalization.png")

# 2. Price Analysis
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Price Metrics', fontsize=16, fontweight='bold')

# Price distribution
ax1 = axes[0, 0]
price_data = df_clean['Market Price'].dropna()
ax1.hist(price_data, bins=50, edgecolor='black', alpha=0.7, color='skyblue')
ax1.set_xlabel('Market Price (NPR)', fontweight='bold')
ax1.set_ylabel('Number of Companies', fontweight='bold')
ax1.set_title('Market Price Distribution', fontweight='bold')
ax1.axvline(price_data.median(), color='red', linestyle='--', linewidth=2, label=f'Median: {price_data.median():.2f}')
ax1.axvline(price_data.mean(), color='green', linestyle='--', linewidth=2, label=f'Mean: {price_data.mean():.2f}')
ax1.legend()
ax1.grid(True, alpha=0.3)

# % Change distribution
ax2 = axes[0, 1]
change_data = df_clean['% Change'].dropna()
ax2.hist(change_data, bins=50, edgecolor='black', alpha=0.7, color='lightcoral')
ax2.set_xlabel('% Change', fontweight='bold')
ax2.set_ylabel('Number of Companies', fontweight='bold')
ax2.set_title('Daily % Change Distribution', fontweight='bold')
ax2.axvline(0, color='black', linestyle='-', linewidth=1)
ax2.axvline(change_data.median(), color='red', linestyle='--', linewidth=2, label=f'Median: {change_data.median():.2f}%')
ax2.legend()
ax2.grid(True, alpha=0.3)

# Top gainers and losers
ax3 = axes[1, 0]
top_gainers = df_clean.nlargest(10, '% Change')[['code', '% Change']]
top_losers = df_clean.nsmallest(10, '% Change')[['code', '% Change']]
y_pos_gainers = range(len(top_gainers))
y_pos_losers = range(len(top_gainers), len(top_gainers) + len(top_losers))
ax3.barh(y_pos_gainers, top_gainers['% Change'], color='green', alpha=0.7, label='Top Gainers')
ax3.barh(y_pos_losers, top_losers['% Change'], color='red', alpha=0.7, label='Top Losers')
ax3.set_yticks(list(y_pos_gainers) + list(y_pos_losers))
ax3.set_yticklabels(list(top_gainers['code']) + list(top_losers['code']), fontsize=9)
ax3.set_xlabel('% Change', fontweight='bold')
ax3.set_title('Top 10 Gainers vs Top 10 Losers', fontweight='bold')
ax3.axvline(0, color='black', linestyle='-', linewidth=1)
ax3.legend()
ax3.grid(True, alpha=0.3, axis='x')

# Price vs 52-week range
ax4 = axes[1, 1]
df_52w = df_clean[df_clean['52W High'].notna() & df_clean['52W Low'].notna()].copy()
df_52w['Price Position'] = ((df_52w['Market Price'] - df_52w['52W Low']) / 
                            (df_52w['52W High'] - df_52w['52W Low'])) * 100
ax4.scatter(df_52w['Market Capitalization'] / 1e9, df_52w['Price Position'], 
           alpha=0.6, s=50, c=df_52w['% Change'], cmap='RdYlGn')
ax4.set_xlabel('Market Capitalization (Billions NPR)', fontweight='bold')
ax4.set_ylabel('Price Position in 52W Range (%)', fontweight='bold')
ax4.set_title('Price Position vs Market Cap (colored by % Change)', fontweight='bold')
ax4.axhline(50, color='gray', linestyle='--', alpha=0.5)
ax4.grid(True, alpha=0.3)
cbar = plt.colorbar(ax4.collections[0], ax=ax4)
cbar.set_label('% Change', fontweight='bold')

plt.tight_layout()
plt.savefig('2_price_analysis.png', dpi=300, bbox_inches='tight')
print("Saved: 2_price_analysis.png")

# 3. Valuation Metrics
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Valuation Metrics', fontsize=16, fontweight='bold')

# P/E Ratio distribution
ax1 = axes[0, 0]
pe_data = df_clean[(df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & 
                   (df_clean['P/E Ratio'] < 100)]['P/E Ratio']
ax1.hist(pe_data, bins=40, edgecolor='black', alpha=0.7, color='gold')
ax1.set_xlabel('P/E Ratio', fontweight='bold')
ax1.set_ylabel('Number of Companies', fontweight='bold')
ax1.set_title('P/E Ratio Distribution (0-100)', fontweight='bold')
ax1.axvline(pe_data.median(), color='red', linestyle='--', linewidth=2, 
           label=f'Median: {pe_data.median():.2f}')
ax1.legend()
ax1.grid(True, alpha=0.3)

# PBV distribution
ax2 = axes[0, 1]
pbv_data = df_clean[(df_clean['PBV'].notna()) & (df_clean['PBV'] > 0) & 
                   (df_clean['PBV'] < 10)]['PBV']
ax2.hist(pbv_data, bins=40, edgecolor='black', alpha=0.7, color='mediumpurple')
ax2.set_xlabel('Price to Book Value (PBV)', fontweight='bold')
ax2.set_ylabel('Number of Companies', fontweight='bold')
ax2.set_title('PBV Distribution (0-10)', fontweight='bold')
ax2.axvline(1, color='red', linestyle='--', linewidth=2, label='PBV = 1')
ax2.axvline(pbv_data.median(), color='blue', linestyle='--', linewidth=2, 
           label=f'Median: {pbv_data.median():.2f}')
ax2.legend()
ax2.grid(True, alpha=0.3)

# P/E vs PBV scatter
ax3 = axes[1, 0]
pe_pbv = df_clean[(df_clean['P/E Ratio'].notna()) & (df_clean['PBV'].notna()) & 
                  (df_clean['P/E Ratio'] > 0) & (df_clean['P/E Ratio'] < 100) &
                  (df_clean['PBV'] > 0) & (df_clean['PBV'] < 10)]
ax3.scatter(pe_pbv['PBV'], pe_pbv['P/E Ratio'], alpha=0.6, s=50, 
           c=pe_pbv['Market Capitalization'] / 1e9, cmap='viridis')
ax3.set_xlabel('Price to Book Value (PBV)', fontweight='bold')
ax3.set_ylabel('P/E Ratio', fontweight='bold')
ax3.set_title('P/E Ratio vs PBV (colored by Market Cap)', fontweight='bold')
ax3.grid(True, alpha=0.3)
cbar = plt.colorbar(ax3.collections[0], ax=ax3)
cbar.set_label('Market Cap (Billions NPR)', fontweight='bold')

# EPS distribution
ax4 = axes[1, 1]
eps_data = df_clean[(df_clean['EPS'].notna()) & (df_clean['EPS'] > -50) & 
                    (df_clean['EPS'] < 100)]['EPS']
ax4.hist(eps_data, bins=50, edgecolor='black', alpha=0.7, color='lightgreen')
ax4.set_xlabel('Earnings Per Share (EPS)', fontweight='bold')
ax4.set_ylabel('Number of Companies', fontweight='bold')
ax4.set_title('EPS Distribution', fontweight='bold')
ax4.axvline(0, color='red', linestyle='--', linewidth=2)
ax4.axvline(eps_data.median(), color='blue', linestyle='--', linewidth=2, 
           label=f'Median: {eps_data.median():.2f}')
ax4.legend()
ax4.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('3_valuation_metrics.png', dpi=300, bbox_inches='tight')
print("Saved: 3_valuation_metrics.png")

# 4. Sector Analysis
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Sector Analysis', fontsize=16, fontweight='bold')

# Number of companies by sector
ax1 = axes[0, 0]
sector_counts = df_clean['Sector'].value_counts().sort_values(ascending=True)
bars = ax1.barh(range(len(sector_counts)), sector_counts.values, color='teal')
ax1.set_yticks(range(len(sector_counts)))
ax1.set_yticklabels(sector_counts.index, fontsize=9)
ax1.set_xlabel('Number of Companies', fontweight='bold')
ax1.set_title('Companies per Sector', fontweight='bold')
ax1.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, count in enumerate(sector_counts.values):
    ax1.text(count, i, f'{count}', va='center', fontsize=9)

# Average market price by sector
ax2 = axes[0, 1]
sector_price = df_clean.groupby('Sector')['Market Price'].mean().sort_values(ascending=True)
bars = ax2.barh(range(len(sector_price)), sector_price.values, color='crimson')
ax2.set_yticks(range(len(sector_price)))
ax2.set_yticklabels(sector_price.index, fontsize=9)
ax2.set_xlabel('Average Market Price (NPR)', fontweight='bold')
ax2.set_title('Average Market Price by Sector', fontweight='bold')
ax2.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, price in enumerate(sector_price.values):
    ax2.text(price, i, f'{price:.0f}', va='center', fontsize=9)

# Average P/E by sector
ax3 = axes[1, 0]
sector_pe = df_clean[(df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & 
                     (df_clean['P/E Ratio'] < 100)].groupby('Sector')['P/E Ratio'].mean().sort_values(ascending=True)
bars = ax3.barh(range(len(sector_pe)), sector_pe.values, color='orange')
ax3.set_yticks(range(len(sector_pe)))
ax3.set_yticklabels(sector_pe.index, fontsize=9)
ax3.set_xlabel('Average P/E Ratio', fontweight='bold')
ax3.set_title('Average P/E Ratio by Sector', fontweight='bold')
ax3.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, pe in enumerate(sector_pe.values):
    ax3.text(pe, i, f'{pe:.1f}', va='center', fontsize=9)

# Average % Change by sector
ax4 = axes[1, 1]
sector_change = df_clean.groupby('Sector')['% Change'].mean().sort_values(ascending=True)
bars = ax4.barh(range(len(sector_change)), sector_change.values, 
               color=['green' if x > 0 else 'red' for x in sector_change.values])
ax4.set_yticks(range(len(sector_change)))
ax4.set_yticklabels(sector_change.index, fontsize=9)
ax4.set_xlabel('Average % Change', fontweight='bold')
ax4.set_title('Average Daily % Change by Sector', fontweight='bold')
ax4.axvline(0, color='black', linestyle='-', linewidth=1)
ax4.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, change in enumerate(sector_change.values):
    ax4.text(change, i, f'{change:.2f}%', va='center', fontsize=9)

plt.tight_layout()
plt.savefig('4_sector_analysis.png', dpi=300, bbox_inches='tight')
print("Saved: 4_sector_analysis.png")

# 5. Yield and Dividend Analysis
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Yield & Dividend Analysis', fontsize=16, fontweight='bold')

# 1 Year Yield distribution
ax1 = axes[0, 0]
yield_data = df_clean[df_clean['1 Year Yield'].notna()]['1 Year Yield']
ax1.hist(yield_data, bins=40, edgecolor='black', alpha=0.7, color='lightblue')
ax1.set_xlabel('1 Year Yield (%)', fontweight='bold')
ax1.set_ylabel('Number of Companies', fontweight='bold')
ax1.set_title('1 Year Yield Distribution', fontweight='bold')
ax1.axvline(yield_data.median(), color='red', linestyle='--', linewidth=2, 
           label=f'Median: {yield_data.median():.2f}%')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Dividend distribution
ax2 = axes[0, 1]
div_data = df_clean[df_clean['% Dividend'].notna()]['% Dividend']
ax2.hist(div_data, bins=40, edgecolor='black', alpha=0.7, color='lightpink')
ax2.set_xlabel('% Dividend', fontweight='bold')
ax2.set_ylabel('Number of Companies', fontweight='bold')
ax2.set_title('% Dividend Distribution', fontweight='bold')
ax2.axvline(div_data.median(), color='red', linestyle='--', linewidth=2, 
           label=f'Median: {div_data.median():.2f}%')
ax2.legend()
ax2.grid(True, alpha=0.3)

# Top dividend yielders
ax3 = axes[1, 0]
top_yield = df_clean[df_clean['1 Year Yield'].notna()].nlargest(15, '1 Year Yield')[['code', '1 Year Yield']]
bars = ax3.barh(range(len(top_yield)), top_yield['1 Year Yield'], color='darkgreen')
ax3.set_yticks(range(len(top_yield)))
ax3.set_yticklabels(top_yield['code'], fontsize=9)
ax3.set_xlabel('1 Year Yield (%)', fontweight='bold')
ax3.set_title('Top 15 Companies by Yield', fontweight='bold')
ax3.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, (idx, row) in enumerate(top_yield.iterrows()):
    ax3.text(row['1 Year Yield'], i, f'{row["1 Year Yield"]:.2f}%', 
             va='center', fontsize=8)

# Yield vs Market Cap
ax4 = axes[1, 1]
yield_mcap = df_clean[df_clean['1 Year Yield'].notna() & df_clean['Market Capitalization'].notna()]
ax4.scatter(yield_mcap['Market Capitalization'] / 1e9, yield_mcap['1 Year Yield'], 
           alpha=0.6, s=50, c=yield_mcap['P/E Ratio'], cmap='coolwarm')
ax4.set_xlabel('Market Capitalization (Billions NPR)', fontweight='bold')
ax4.set_ylabel('1 Year Yield (%)', fontweight='bold')
ax4.set_title('Yield vs Market Cap (colored by P/E Ratio)', fontweight='bold')
ax4.grid(True, alpha=0.3)
cbar = plt.colorbar(ax4.collections[0], ax=ax4)
cbar.set_label('P/E Ratio', fontweight='bold')

plt.tight_layout()
plt.savefig('5_yield_dividend.png', dpi=300, bbox_inches='tight')
print("Saved: 5_yield_dividend.png")

# 6. Volume Analysis
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
fig.suptitle('NEPSE Stock Market Analysis - Volume Analysis', fontsize=16, fontweight='bold')

# Volume distribution (log scale)
ax1 = axes[0, 0]
volume_data = df_clean[df_clean['30-Day Avg Volume'].notna() & (df_clean['30-Day Avg Volume'] > 0)]
volume_log = np.log10(volume_data['30-Day Avg Volume'] + 1)
ax1.hist(volume_log, bins=40, edgecolor='black', alpha=0.7, color='salmon')
ax1.set_xlabel('Log10(30-Day Avg Volume)', fontweight='bold')
ax1.set_ylabel('Number of Companies', fontweight='bold')
ax1.set_title('30-Day Average Volume Distribution (Log Scale)', fontweight='bold')
ax1.grid(True, alpha=0.3)

# Top 20 by volume
ax2 = axes[0, 1]
top_vol = volume_data.nlargest(20, '30-Day Avg Volume')[['code', '30-Day Avg Volume']]
top_vol['Volume (Thousands)'] = top_vol['30-Day Avg Volume'] / 1000
bars = ax2.barh(range(len(top_vol)), top_vol['Volume (Thousands)'], color='indianred')
ax2.set_yticks(range(len(top_vol)))
ax2.set_yticklabels(top_vol['code'], fontsize=9)
ax2.set_xlabel('30-Day Avg Volume (Thousands)', fontweight='bold')
ax2.set_title('Top 20 Companies by Volume', fontweight='bold')
ax2.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, (idx, row) in enumerate(top_vol.iterrows()):
    ax2.text(row['Volume (Thousands)'], i, f'{row["Volume (Thousands)"]:.0f}K', 
             va='center', fontsize=8)

# Volume vs Market Cap
ax3 = axes[1, 0]
vol_mcap = df_clean[df_clean['30-Day Avg Volume'].notna() & df_clean['Market Capitalization'].notna() & 
                   (df_clean['30-Day Avg Volume'] > 0)]
ax3.scatter(vol_mcap['Market Capitalization'] / 1e9, 
           np.log10(vol_mcap['30-Day Avg Volume'] + 1),
           alpha=0.6, s=50, c=vol_mcap['% Change'], cmap='RdYlGn')
ax3.set_xlabel('Market Capitalization (Billions NPR)', fontweight='bold')
ax3.set_ylabel('Log10(30-Day Avg Volume)', fontweight='bold')
ax3.set_title('Volume vs Market Cap (colored by % Change)', fontweight='bold')
ax3.grid(True, alpha=0.3)
cbar = plt.colorbar(ax3.collections[0], ax=ax3)
cbar.set_label('% Change', fontweight='bold')

# Volume by Sector
ax4 = axes[1, 1]
sector_vol = df_clean[df_clean['30-Day Avg Volume'].notna() & 
                     (df_clean['30-Day Avg Volume'] > 0)].groupby('Sector')['30-Day Avg Volume'].mean().sort_values(ascending=True)
bars = ax4.barh(range(len(sector_vol)), sector_vol.values / 1000, color='mediumvioletred')
ax4.set_yticks(range(len(sector_vol)))
ax4.set_yticklabels(sector_vol.index, fontsize=9)
ax4.set_xlabel('Average 30-Day Volume (Thousands)', fontweight='bold')
ax4.set_title('Average Volume by Sector', fontweight='bold')
ax4.grid(True, alpha=0.3, axis='x')
# Add value labels
for i, vol in enumerate(sector_vol.values):
    ax4.text(vol/1000, i, f'{vol/1000:.0f}K', va='center', fontsize=9)

plt.tight_layout()
plt.savefig('6_volume_analysis.png', dpi=300, bbox_inches='tight')
print("Saved: 6_volume_analysis.png")

# Generate detailed insights report
print("\n" + "="*80)
print("DETAILED INSIGHTS REPORT")
print("="*80)

insights = []

# Basic Statistics
insights.append("\n1. MARKET OVERVIEW")
insights.append("-" * 80)
insights.append(f"Total Companies Analyzed: {len(df_clean)}")
insights.append(f"Total Sectors: {df_clean['Sector'].nunique()}")
insights.append(f"Total Market Capitalization: {df_clean['Market Capitalization'].sum()/1e12:.2f} Trillion NPR")
insights.append(f"Average Market Cap per Company: {df_clean['Market Capitalization'].mean()/1e9:.2f} Billion NPR")
insights.append(f"Median Market Cap: {df_clean['Market Capitalization'].median()/1e9:.2f} Billion NPR")

# Market Concentration
top_10_pct_companies = int(len(df_clean) * 0.1)
top_10_pct_mcap = df_clean.nlargest(top_10_pct_companies, 'Market Capitalization')['Market Capitalization'].sum()
concentration_pct = (top_10_pct_mcap / df_clean['Market Capitalization'].sum()) * 100
insights.append(f"\nMarket Concentration: Top 10% of companies hold {concentration_pct:.1f}% of total market cap")

# Price Analysis
insights.append("\n2. PRICE ANALYSIS")
insights.append("-" * 80)
insights.append(f"Average Market Price: {df_clean['Market Price'].mean():.2f} NPR")
insights.append(f"Median Market Price: {df_clean['Market Price'].median():.2f} NPR")
insights.append(f"Price Range: {df_clean['Market Price'].min():.2f} - {df_clean['Market Price'].max():.2f} NPR")

# % Change Analysis
change_data = df_clean['% Change'].dropna()
insights.append(f"\nAverage Daily % Change: {change_data.mean():.2f}%")
insights.append(f"Median Daily % Change: {change_data.median():.2f}%")
positive_change = (change_data > 0).sum()
negative_change = (change_data < 0).sum()
insights.append(f"Companies with Positive Change: {positive_change} ({positive_change/len(change_data)*100:.1f}%)")
insights.append(f"Companies with Negative Change: {negative_change} ({negative_change/len(change_data)*100:.1f}%)")

# Top Performers
top_gainers = df_clean.nlargest(5, '% Change')[['code', '% Change', 'Market Price', 'Sector']]
insights.append("\nTop 5 Gainers:")
for idx, row in top_gainers.iterrows():
    insights.append(f"  {row['code']}: {row['% Change']:.2f}% | Price: {row['Market Price']:.2f} NPR | Sector: {row['Sector']}")

top_losers = df_clean.nsmallest(5, '% Change')[['code', '% Change', 'Market Price', 'Sector']]
insights.append("\nTop 5 Losers:")
for idx, row in top_losers.iterrows():
    insights.append(f"  {row['code']}: {row['% Change']:.2f}% | Price: {row['Market Price']:.2f} NPR | Sector: {row['Sector']}")

# Valuation Metrics
insights.append("\n3. VALUATION METRICS")
insights.append("-" * 80)
pe_data = df_clean[(df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & 
                   (df_clean['P/E Ratio'] < 100)]['P/E Ratio']
insights.append(f"Average P/E Ratio: {pe_data.mean():.2f}")
insights.append(f"Median P/E Ratio: {pe_data.median():.2f}")
insights.append(f"P/E Ratio Range: {pe_data.min():.2f} - {pe_data.max():.2f}")

pbv_data = df_clean[(df_clean['PBV'].notna()) & (df_clean['PBV'] > 0) & 
                    (df_clean['PBV'] < 10)]['PBV']
insights.append(f"\nAverage PBV: {pbv_data.mean():.2f}")
insights.append(f"Median PBV: {pbv_data.median():.2f}")
undervalued = (pbv_data < 1).sum()
overvalued = (pbv_data > 2).sum()
insights.append(f"Companies with PBV < 1 (Potentially Undervalued): {undervalued}")
insights.append(f"Companies with PBV > 2: {overvalued}")

eps_data = df_clean[df_clean['EPS'].notna()]['EPS']
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
    'Market Capitalization': ['sum', 'mean'],
    'P/E Ratio': lambda x: x[(x > 0) & (x < 100)].mean()
}).round(2)

insights.append("\nSector Performance Summary:")
for sector in sector_stats.index:
    insights.append(f"\n{sector}:")
    insights.append(f"  Companies: {df_clean[df_clean['Sector'] == sector].shape[0]}")
    insights.append(f"  Avg Price: {sector_stats.loc[sector, ('Market Price', 'mean')]:.2f} NPR")
    insights.append(f"  Avg % Change: {sector_stats.loc[sector, ('% Change', 'mean')]:.2f}%")
    insights.append(f"  Total Market Cap: {sector_stats.loc[sector, ('Market Capitalization', 'sum')]/1e9:.2f} Billion NPR")
    insights.append(f"  Avg Market Cap: {sector_stats.loc[sector, ('Market Capitalization', 'mean')]/1e9:.2f} Billion NPR")
    if pd.notna(sector_stats.loc[sector, ('P/E Ratio', '<lambda>')]):
        insights.append(f"  Avg P/E Ratio: {sector_stats.loc[sector, ('P/E Ratio', '<lambda>')]:.2f}")

# Yield and Dividend Analysis
insights.append("\n5. YIELD & DIVIDEND ANALYSIS")
insights.append("-" * 80)
yield_data = df_clean[df_clean['1 Year Yield'].notna()]['1 Year Yield']
insights.append(f"Average 1 Year Yield: {yield_data.mean():.2f}%")
insights.append(f"Median 1 Year Yield: {yield_data.median():.2f}%")
insights.append(f"Yield Range: {yield_data.min():.2f}% - {yield_data.max():.2f}%")

div_data = df_clean[df_clean['% Dividend'].notna()]['% Dividend']
if len(div_data) > 0:
    insights.append(f"\nAverage % Dividend: {div_data.mean():.2f}%")
    insights.append(f"Median % Dividend: {div_data.median():.2f}%")
    insights.append(f"Companies Paying Dividends: {len(div_data)}")

top_yielders = df_clean[df_clean['1 Year Yield'].notna()].nlargest(5, '1 Year Yield')[['code', '1 Year Yield', 'Sector']]
insights.append("\nTop 5 Companies by Yield:")
for idx, row in top_yielders.iterrows():
    insights.append(f"  {row['code']}: {row['1 Year Yield']:.2f}% | Sector: {row['Sector']}")

# Volume Analysis
insights.append("\n6. VOLUME ANALYSIS")
insights.append("-" * 80)
volume_data = df_clean[df_clean['30-Day Avg Volume'].notna() & (df_clean['30-Day Avg Volume'] > 0)]['30-Day Avg Volume']
insights.append(f"Average 30-Day Volume: {volume_data.mean():,.0f}")
insights.append(f"Median 30-Day Volume: {volume_data.median():,.0f}")

top_volume = df_clean[df_clean['30-Day Avg Volume'].notna()].nlargest(5, '30-Day Avg Volume')[['code', '30-Day Avg Volume', 'Sector']]
insights.append("\nTop 5 Companies by Volume:")
for idx, row in top_volume.iterrows():
    insights.append(f"  {row['code']}: {row['30-Day Avg Volume']:,.0f} | Sector: {row['Sector']}")

# 52-Week Analysis
insights.append("\n7. 52-WEEK HIGH/LOW ANALYSIS")
insights.append("-" * 80)
df_52w = df_clean[df_clean['52W High'].notna() & df_clean['52W Low'].notna()].copy()
df_52w['Price Position'] = ((df_52w['Market Price'] - df_52w['52W Low']) / 
                            (df_52w['52W High'] - df_52w['52W Low'])) * 100
insights.append(f"Companies near 52W High (>90%): {(df_52w['Price Position'] > 90).sum()}")
insights.append(f"Companies near 52W Low (<10%): {(df_52w['Price Position'] < 10).sum()}")
insights.append(f"Average Price Position: {df_52w['Price Position'].mean():.1f}%")
insights.append(f"Median Price Position: {df_52w['Price Position'].median():.1f}%")

near_high = df_52w[df_52w['Price Position'] > 90].nlargest(5, 'Price Position')[['code', 'Price Position', 'Market Price', '52W High']]
insights.append("\nCompanies Closest to 52W High:")
for idx, row in near_high.iterrows():
    insights.append(f"  {row['code']}: {row['Price Position']:.1f}% | Current: {row['Market Price']:.2f} | High: {row['52W High']:.2f}")

near_low = df_52w[df_52w['Price Position'] < 10].nsmallest(5, 'Price Position')[['code', 'Price Position', 'Market Price', '52W Low']]
insights.append("\nCompanies Closest to 52W Low:")
for idx, row in near_low.iterrows():
    insights.append(f"  {row['code']}: {row['Price Position']:.1f}% | Current: {row['Market Price']:.2f} | Low: {row['52W Low']:.2f}")

# Investment Insights
insights.append("\n8. INVESTMENT INSIGHTS")
insights.append("-" * 80)

# Undervalued stocks (low PBV, positive EPS, reasonable P/E)
undervalued_stocks = df_clean[
    (df_clean['PBV'].notna()) & (df_clean['PBV'] < 1) &
    (df_clean['EPS'].notna()) & (df_clean['EPS'] > 0) &
    (df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 0) & (df_clean['P/E Ratio'] < 30)
].nlargest(10, 'Market Capitalization')[['code', 'Market Price', 'PBV', 'P/E Ratio', 'EPS', 'Sector']]

if len(undervalued_stocks) > 0:
    insights.append("\nPotentially Undervalued Stocks (PBV < 1, Positive EPS, P/E < 30):")
    for idx, row in undervalued_stocks.iterrows():
        insights.append(f"  {row['code']}: Price={row['Market Price']:.2f}, PBV={row['PBV']:.2f}, P/E={row['P/E Ratio']:.2f}, EPS={row['EPS']:.2f}, Sector={row['Sector']}")

# High yield stocks
high_yield_stocks = df_clean[
    (df_clean['1 Year Yield'].notna()) & (df_clean['1 Year Yield'] > 5) &
    (df_clean['Market Capitalization'].notna())
].nlargest(10, 'Market Capitalization')[['code', '1 Year Yield', 'Market Price', 'P/E Ratio', 'Sector']]

if len(high_yield_stocks) > 0:
    insights.append("\nHigh Yield Stocks (>5% yield):")
    for idx, row in high_yield_stocks.iterrows():
        pe_str = f"{row['P/E Ratio']:.2f}" if pd.notna(row['P/E Ratio']) else 'N/A'
        insights.append(f"  {row['code']}: Yield={row['1 Year Yield']:.2f}%, Price={row['Market Price']:.2f}, P/E={pe_str}, Sector={row['Sector']}")

# Growth stocks (high P/E, positive EPS growth potential)
growth_stocks = df_clean[
    (df_clean['P/E Ratio'].notna()) & (df_clean['P/E Ratio'] > 15) & (df_clean['P/E Ratio'] < 50) &
    (df_clean['EPS'].notna()) & (df_clean['EPS'] > 0) &
    (df_clean['% Change'].notna()) & (df_clean['% Change'] > 0)
].nlargest(10, '% Change')[['code', 'P/E Ratio', '% Change', 'EPS', 'Market Price', 'Sector']]

if len(growth_stocks) > 0:
    insights.append("\nPotential Growth Stocks (P/E 15-50, Positive EPS, Positive Change):")
    for idx, row in growth_stocks.iterrows():
        insights.append(f"  {row['code']}: P/E={row['P/E Ratio']:.2f}, Change={row['% Change']:.2f}%, EPS={row['EPS']:.2f}, Price={row['Market Price']:.2f}, Sector={row['Sector']}")

# Print all insights
for insight in insights:
    print(insight)

# Save insights to file
with open('stock_analysis_insights.txt', 'w', encoding='utf-8') as f:
    for insight in insights:
        f.write(insight + '\n')

print("\n" + "="*80)
print("Analysis complete! All visualizations and insights have been saved.")
print("="*80)
print("\nGenerated Files:")
print("  1. 1_market_capitalization.png")
print("  2. 2_price_analysis.png")
print("  3. 3_valuation_metrics.png")
print("  4. 4_sector_analysis.png")
print("  5. 5_yield_dividend.png")
print("  6. 6_volume_analysis.png")
print("  7. stock_analysis_insights.txt")
