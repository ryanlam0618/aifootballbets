import pandas as pd

# Check available data files
import os

print('Available CSV files in data/:')
for f in os.listdir('data'):
    if f.endswith('.csv'):
        size = os.path.getsize(f'data/{f}')
        print(f'  {f}: {size/1024/1024:.2f} MB')

# Check historical data
print()
print('='*60)
print('HISTORICAL DATA OVERVIEW')
print('='*60)

# Try history_data.csv
try:
    df = pd.read_csv('data/history_data.csv')
    print(f'File: data/history_data.csv')
except:
    print('Could not read history_data.csv')
    df = None

if df is not None:
    print(f'Total records: {len(df):,}')
    print(f'Columns: {len(df.columns)}')
    print()
    print('Columns:', list(df.columns))
    print()
    if 'league' in df.columns:
        print('League distribution:')
        print(df['league'].value_counts())
    print()
    if 'Date' in df.columns:
        print('Date range:')
        print(f'  Earliest: {df["Date"].min()}')
        print(f'  Latest: {df["Date"].max()}')
    print()
    if 'HomeTeam' in df.columns:
        print(f'Home teams: {df["HomeTeam"].nunique()}')
    if 'AwayTeam' in df.columns:
        print(f'Away teams: {df["AwayTeam"].nunique()}')
