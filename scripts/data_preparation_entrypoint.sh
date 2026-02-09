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
BASE_DIR="/home/ec2-user/AI-Trader"


# 提取日期后缀（从 CONFIG_FILE 的 init_date 提取）
DATE_SUFFIX=""
if [ -n "$CONFIG_FILE" ]; then
    # 构建完整配置文件路径
    if [[ "$CONFIG_FILE" = /* ]]; then
        # 绝对路径
        CONFIG_FULL_PATH="$CONFIG_FILE"
    else
        # 相对路径，从 BASE_DIR 开始
        CONFIG_FULL_PATH="$BASE_DIR/$CONFIG_FILE"
    fi
    
    # 使用 Python 提取 init_date 并转换为 8 位数字后缀
    DATE_SUFFIX=$(python3 -c "
import json, sys
from pathlib import Path
config_path = Path('$CONFIG_FULL_PATH')
if config_path.exists():
    data = json.loads(config_path.read_text(encoding='utf-8'))
    init_date = data.get('date_range', {}).get('init_date', '')
    # 支持 '2025-01-19' 或 '2025-01-19 09:30:01' 格式
    date_only = init_date.split()[0] if ' ' in init_date else init_date
    suffix = date_only.replace('-', '').replace(':', '')[:8]
    print(suffix)
" 2>/dev/null || echo "")
    
    if [ -n "$DATE_SUFFIX" ]; then
        echo "📅 提取日期后缀: $DATE_SUFFIX (从配置文件 $CONFIG_FULL_PATH)"
    else
        echo "⚠️ 未能提取日期后缀，配置文件: $CONFIG_FULL_PATH"
    fi
fi

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

cd "$BASE_DIR/data/A_stock"

# 构建参数
if [ -n "$DATE_SUFFIX" ]; then
    echo "💾 将使用日期后缀: $DATE_SUFFIX 生成隔离数据文件"
fi

# 1. Fetch Daily Stocks & Index (Tushare)
if [ "$MODE" == "MANUAL" ]; then
    if [ -n "$DATE_SUFFIX" ]; then
        python get_daily_price_tushare.py "$FETCH_INIT" "$FETCH_END" --date-suffix "$DATE_SUFFIX" || echo "⚠️ Tushare fetch failed"
    else
        python get_daily_price_tushare.py "$FETCH_INIT" "$FETCH_END" || echo "⚠️ Tushare fetch failed"
    fi
else
    if [ -n "$DATE_SUFFIX" ]; then
        python get_daily_price_tushare.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Tushare fetch failed"
    else
        python get_daily_price_tushare.py || echo "⚠️ Tushare fetch failed"
    fi
fi
sleep 2

# 2. Fetch Daily Stocks (EF)
if [ "$MODE" == "MANUAL" ]; then
    if [ -n "$DATE_SUFFIX" ]; then
        python get_daily_price_ef.py "$FETCH_INIT" "$FETCH_END" --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF daily fetch failed"
    else
        python get_daily_price_ef.py "$FETCH_INIT" "$FETCH_END" || echo "⚠️ EF daily fetch failed"
    fi
else
    if [ -n "$DATE_SUFFIX" ]; then
        python get_daily_price_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF daily fetch failed"
    else
        python get_daily_price_ef.py || echo "⚠️ EF daily fetch failed"
    fi
fi
sleep 2

# 3. Fetch Hourly Stocks (EF) - Only in LIVE mode
if [ "$MODE" == "LIVE" ]; then
    if [ -n "$DATE_SUFFIX" ]; then
        python get_hourly_price_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF hourly fetch failed"
    else
        python get_hourly_price_ef.py || echo "⚠️ EF hourly fetch failed"
    fi
    sleep 2
else
    echo "⏭ Skipping Hourly data for Backtest/Manual Sync"
fi

echo "🔀 Merging price data..."
if [ -n "$DATE_SUFFIX" ]; then
    python merge_jsonl_daily_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Daily merge failed"
else
    python merge_jsonl_daily_ef.py || echo "⚠️ Daily merge failed"
fi
sleep 2
if [ "$MODE" == "LIVE" ]; then
    if [ -n "$DATE_SUFFIX" ]; then
        python merge_jsonl_hourly_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Hourly merge failed"
    else
        python merge_jsonl_hourly_ef.py || echo "⚠️ Hourly merge failed"
    fi
    sleep 2
fi

cd "$BASE_DIR"

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
