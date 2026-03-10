#!/bin/bash
# Data Preparation Entrypoint for agent-base
# This script only fetches and merges price data, then exits.
# Other agent containers will wait for this to complete.
#
# ============================================
# 参数来源：仅从环境变量获取
# ============================================
# 必需环境变量：
#   - CONFIG_FILE: 配置文件路径 (e.g. configs/astock_config_hourly.json)
#   - DATE_SUFFIX: 日期后缀，用于数据隔离 (e.g. 20250119)
#
# 可选环境变量（回测模式需要）：
#   - START_DATE: 开始日期 (e.g. 2025-01-01)
#   - END_DATE: 结束日期 (e.g. 2025-01-21)
#
# 由 aws_ecs_run_all.sh 通过 ECS 任务环境变量传入

set -e

echo "📊 Starting A-stock data preparation (agent-base)..."
echo "============================================"

# ============================================
# 严格校验必需环境变量
# ============================================
MISSING_VARS=""

if [ -z "$CONFIG_FILE" ]; then
    MISSING_VARS="${MISSING_VARS}CONFIG_FILE "
fi

if [ -z "$DATE_SUFFIX" ]; then
    MISSING_VARS="${MISSING_VARS}DATE_SUFFIX "
fi

if [ -n "$MISSING_VARS" ]; then
    echo "❌ ERROR: Missing required environment variables: $MISSING_VARS"
    echo ""
    echo "Required environment variables:"
    echo "  CONFIG_FILE  - Config file path (e.g. configs/astock_config_hourly.json)"
    echo "  DATE_SUFFIX  - Date suffix for data isolation (e.g. 20250119)"
    echo ""
    echo "Optional environment variables (for backtest mode):"
    echo "  START_DATE   - Start date (e.g. 2025-01-01)"
    echo "  END_DATE     - End date (e.g. 2025-01-21)"
    echo ""
    echo "Example ECS task override:"
    echo '  --overrides {"containerOverrides":[{"name":"trader-data-prep","environment":[{"name":"CONFIG_FILE","value":"configs/xxx.json"},{"name":"DATE_SUFFIX","value":"20250119"}]}]}'
    exit 1
fi

# 读取可选环境变量
INIT_DATE_ARG="${START_DATE:-}"
END_DATE_ARG="${END_DATE:-}"

BASE_DIR="/home/ec2-user/AI-Trader"

echo "📊 Environment Variables:"
echo "   CONFIG_FILE: $CONFIG_FILE"
echo "   DATE_SUFFIX: $DATE_SUFFIX"
echo "   START_DATE:  ${INIT_DATE_ARG:-'(not set - LIVE mode)'}"
echo "   END_DATE:    ${END_DATE_ARG:-'(not set - LIVE mode)'}"
echo "============================================"

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
    NOW_DATE=$(date +"%Y-%m-%d")
    echo "🌐 Mode: Live trading (Automatic history from current time)"
fi

cd "$BASE_DIR/scripts/a_stock"

echo ""
echo "============================================"
echo "📦 Step 1/4: Fetch Daily Stocks (Tushare)"
echo "============================================"
# 1. Fetch Daily Stocks & Index (Tushare)
if [ "$MODE" == "MANUAL" ]; then
    echo "🔧 Running: python get_daily_price_tushare.py $FETCH_INIT $FETCH_END --date-suffix $DATE_SUFFIX"
    python get_daily_price_tushare.py "$FETCH_INIT" "$FETCH_END" --date-suffix "$DATE_SUFFIX" || echo "⚠️ Tushare fetch failed"
else
    echo "🔧 Running: python get_daily_price_tushare.py --date-suffix $DATE_SUFFIX"
    python get_daily_price_tushare.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Tushare fetch failed"
fi
sleep 2

echo ""
echo "============================================"
echo "📦 Step 2/4: Fetch Daily Stocks (EF)"
echo "============================================"
# 2. Fetch Daily Stocks (EF)
if [ "$MODE" == "MANUAL" ]; then
    echo "🔧 Running: python get_daily_price_ef.py $FETCH_INIT $FETCH_END --date-suffix $DATE_SUFFIX"
    python get_daily_price_ef.py "$FETCH_INIT" "$FETCH_END" --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF daily fetch failed"
else
    echo "🔧 Running: python get_daily_price_ef.py --date-suffix $DATE_SUFFIX"
    python get_daily_price_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF daily fetch failed"
fi
sleep 2

echo ""
echo "============================================"
echo "📦 Step 3/4: Fetch Hourly Stocks (EF)"
echo "============================================"
# 3. Fetch Hourly Stocks (EF) - Only in LIVE mode
if [ "$MODE" == "LIVE" ]; then
    echo "🔧 Running: python get_hourly_price_ef.py --date-suffix $DATE_SUFFIX"
    python get_hourly_price_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ EF hourly fetch failed"
    sleep 2
else
    echo "⏭ Skipping Hourly data (MODE=$MODE)"
fi

echo ""
echo "============================================"
echo "📦 Step 4/4: Merge Price Data"
echo "============================================"
echo "🔧 Running: python merge_jsonl_daily_ef.py --date-suffix $DATE_SUFFIX"
python merge_jsonl_daily_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Daily merge failed"
sleep 2
if [ "$MODE" == "LIVE" ]; then
    echo "🔧 Running: python merge_jsonl_hourly_ef.py --date-suffix $DATE_SUFFIX"
    python merge_jsonl_hourly_ef.py --date-suffix "$DATE_SUFFIX" || echo "⚠️ Hourly merge failed"
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
