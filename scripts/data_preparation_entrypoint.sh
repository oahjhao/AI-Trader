#!/bin/bash
# Data Preparation Entrypoint for agent-base
# This script only fetches and merges price data, then exits.
# Other agent containers will wait for this to complete.

set -e

echo "📊 Starting A-stock data preparation (agent-base)..."

# Optional CLI args:
#   $1: config file path (relative to project root, e.g. configs/astock_config_hourly.json)
#   $2: init_date
#   $3: end_date
CONFIG_FILE="$1"
INIT_DATE_ARG="$2"
END_DATE_ARG="$3"

# Determine mode and target dates
if [ -n "$INIT_DATE_ARG" ] && [ -n "$END_DATE_ARG" ]; then
    MODE="MANUAL"
    FETCH_INIT="$INIT_DATE_ARG"
    FETCH_END="$END_DATE_ARG"
    echo "🛠 Mode: Manual Update/Backtest Sync"
    echo "📍 Anchor init_date: $FETCH_INIT, end_date: $FETCH_END"
else
    MODE="LIVE"
    FETCH_INIT=""
    FETCH_END=""
    NOW_DATE=$(date +"%Y-%m-%d %H:%M:%S")
    echo "🌐 Mode: Live trading (Automatic history from current time)"
fi

cd data/A_stock

# 1. Fetch Daily Stocks & Index (Tushare)
if [ "$MODE" == "MANUAL" ]; then
    python get_daily_price_tushare.py "$FETCH_INIT" "$FETCH_END" || echo "⚠️ Tushare fetch failed"
else
    python get_daily_price_tushare.py || echo "⚠️ Tushare fetch failed"
fi
sleep 2

# 2. Fetch Daily Stocks (EF)
if [ "$MODE" == "MANUAL" ]; then
    python get_daily_price_ef.py "$FETCH_INIT" "$FETCH_END" || echo "⚠️ EF daily fetch failed"
else
    python get_daily_price_ef.py || echo "⚠️ EF daily fetch failed"
fi
sleep 2

# 3. Fetch Hourly Stocks (EF) - Only in LIVE mode
if [ "$MODE" == "LIVE" ]; then
    python get_hourly_price_ef.py || echo "⚠️ EF hourly fetch failed"
    sleep 2
else
    echo "⏭ Skipping Hourly data for Backtest/Manual Sync"
fi

echo "🔀 Merging price data..."
python merge_jsonl_daily_ef.py || echo "⚠️ Daily merge failed"
sleep 2
if [ "$MODE" == "LIVE" ]; then
    python merge_jsonl_hourly_ef.py || echo "⚠️ Hourly merge failed"
    sleep 2
fi

cd ../..

# Optionally update config file's date_range
if [ -n "$CONFIG_FILE" ]; then
    if [ "$MODE" = "MANUAL" ]; then
        echo "📝 Updating $CONFIG_FILE: init_date=$FETCH_INIT, end_date=$FETCH_END"
        python - "$CONFIG_FILE" "$FETCH_INIT" "$FETCH_END" << 'PY'
import json
import sys
from pathlib import Path
config_path = Path(sys.argv[1])
init_date = sys.argv[2]
end_date = sys.argv[3]
if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8"))
    dr = data.get("date_range", {})
    dr["init_date"] = init_date
    dr["end_date"] = end_date
    data["date_range"] = dr
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Config updated successfully")
PY
    elif [ "$MODE" = "LIVE" ]; then
        # LIVE Mode: only update end_date to current time
        echo "📝 Updating $CONFIG_FILE: end_date=$NOW_DATE"
        python - "$CONFIG_FILE" "$NOW_DATE" << 'PY'
import json
import sys
from pathlib import Path
config_path = Path(sys.argv[1])
now_date = sys.argv[2]
if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8"))
    dr = data.get("date_range", {})
    dr["end_date"] = now_date
    data["date_range"] = dr
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Config end_date updated to {now_date}")
PY
    fi
fi

echo "✅ Data preparation complete! Other agents can now proceed."
