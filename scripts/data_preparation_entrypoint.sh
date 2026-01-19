#!/bin/bash
# Data Preparation Entrypoint for agent-base
# This script only fetches and merges price data, then exits.
# Other agent containers will wait for this to complete.

set -e

echo "📊 Starting A-stock data preparation (agent-base)..."
cd data/A_stock

# Check if we're in backtest mode (START_DATE and END_DATE env vars)
if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    echo "📈 Backtest mode: Data range $START_DATE to $END_DATE"
    python get_daily_price_tushare.py "$START_DATE" "$END_DATE" || echo "⚠️  Tushare fetch failed, continuing..."
    sleep 2
    python get_daily_price_ef.py "$START_DATE" "$END_DATE" || echo "⚠️  EF daily fetch failed, continuing..."
    sleep 5
    python get_hourly_price_ef.py "$START_DATE" "$END_DATE" || echo "⚠️  EF hourly fetch failed, continuing..."
    sleep 5
else
    echo "🔴 Live trading mode: Using default time range"
    python get_daily_price_tushare.py || echo "⚠️  Tushare fetch failed, continuing..."
    sleep 2
    python get_daily_price_ef.py || echo "⚠️  EF daily fetch failed, continuing..."
    sleep 5
    python get_hourly_price_ef.py || echo "⚠️  EF hourly fetch failed, continuing..."
    sleep 5
fi

echo "🔀 Merging price data..."
python merge_jsonl_daily_ef.py || echo "⚠️  Daily merge failed, continuing..."
sleep 2
python merge_jsonl_hourly_ef.py || echo "⚠️  Hourly merge failed, continuing..."

cd ../..

echo "✅ Data preparation complete! Other agents can now proceed."
