#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin"

# ============================================================
# A-Stock Back Test Script - Daily Trading Mode
# ============================================================
# This script runs back tests using daily price data (YYYY-MM-DD format)
# instead of hourly data, due to missing intraday data.
# 
# Key changes from hourly mode:
# - Uses YYYY-MM-DD date format (no time component)
# - Config template: default_astock_config.json (BaseAgentAStock)
# - Data scripts receive date-only parameters
# - Compatible with both backtest and live trading scenarios
# ============================================================

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# Parse command line argument for number of dates to process
MAX_DATES=${1:-0}  # Default to 0 (process all dates if no argument provided)

# Define paths
SSE_PICK_2025_CSV="data/A_stock/sse_pick_2025.csv"
SSE_PICK_OUTPUT="data/A_stock/sse_pick.csv"
CONFIG_TEMPLATE="configs/astock_config_hourly.json"
CONFIG_OUTPUT_DIR="configs"
LOG_DIR="logs/backtest"

# Create log directory if not exists
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Starting Back Test Configuration Generator"
echo "=========================================="
echo "Project Root: $PROJECT_ROOT"
echo "Log Directory: $LOG_DIR"
if [ $MAX_DATES -gt 0 ]; then
    echo "Max dates to process: $MAX_DATES"
else
    echo "Max dates to process: ALL"
fi
echo ""

# Check if required files exist
if [ ! -f "$SSE_PICK_2025_CSV" ]; then
    echo "Error: $SSE_PICK_2025_CSV not found!"
    exit 1
fi

if [ ! -f "$CONFIG_TEMPLATE" ]; then
    echo "Error: $CONFIG_TEMPLATE not found!"
    exit 1
fi

# Extract unique dates from sse_pick_2025.csv (skip header)
DATES=$(tail -n +2 "$SSE_PICK_2025_CSV" | cut -d',' -f1 | sort -u)

echo "Found unique dates:"
echo "$DATES"
echo ""

DATE_COUNT=$(echo "$DATES" | wc -l)
echo "Total unique dates: $DATE_COUNT"
echo ""

# Process counter
CURRENT=0
SUCCESS_COUNT=0
FAIL_COUNT=0

# Process each date
for DATE in $DATES; do
    CURRENT=$((CURRENT + 1))
    
    # Check if we've reached the maximum number of dates to process
    if [ $MAX_DATES -gt 0 ] && [ $CURRENT -gt $MAX_DATES ]; then
        echo "=========================================="
        echo "Reached maximum dates limit ($MAX_DATES)"
        echo "Stopping back test execution"
        echo "=========================================="
        echo ""
        break
    fi
    
    echo "=========================================="
    echo "Processing date: $DATE [$CURRENT/$DATE_COUNT]"
    echo "=========================================="
    
    # Format date for file naming (already in YYYYMMDD format)
    YEAR=${DATE:0:4}
    MONTH=${DATE:4:2}
    DAY=${DATE:6:2}
    
    # Format date for config (YYYY-MM-DD for daily trading)
    INIT_DATE="$YEAR-$MONTH-$DAY"
    
    # Calculate end date (+7 days)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        END_DATE=$(date -j -v+7d -f "%Y-%m-%d" "$INIT_DATE" "+%Y-%m-%d")
    else
        # Linux
        END_DATE=$(date -d "$INIT_DATE +7 days" "+%Y-%m-%d")
    fi
    
    echo "  Init Date: $INIT_DATE (daily trading mode)"
    echo "  End Date:  $END_DATE"
    
    # Step 1: Generate sse_pick.csv from sse_pick_2025.csv for this date
    echo "  Generating sse_pick.csv..."
    
    # Extract data for this date from sse_pick_2025.csv
    # Create header
    echo "date,con_code,stock_name" > "$SSE_PICK_OUTPUT"
    # Extract rows for this date
    grep "^$DATE," "$SSE_PICK_2025_CSV" >> "$SSE_PICK_OUTPUT"
    
    STOCK_COUNT=$(tail -n +2 "$SSE_PICK_OUTPUT" | wc -l)
    echo "  Generated sse_pick.csv with $STOCK_COUNT stocks"
    echo ""
    
    # Step 2: Generate config file
    CONFIG_OUTPUT="${CONFIG_OUTPUT_DIR}/astock_config_daily_${DATE}.json"
    echo "  Generating config: $CONFIG_OUTPUT"
    
    # Copy template and update dates
    cp "$CONFIG_TEMPLATE" "$CONFIG_OUTPUT"
    
    # Update agent_type to daily mode (BaseAgentAStock instead of BaseAgentAStockHourly)
    jq '.agent_type = "BaseAgentAStock"' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    # Update init_date (daily format: YYYY-MM-DD)
    jq --arg date "$INIT_DATE" '.date_range.init_date = $date' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    # Update end_date (daily format: YYYY-MM-DD)
    jq --arg date "$END_DATE" '.date_range.end_date = $date' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    # Format date for model name (YYMMDD)
    MODEL_DATE="${YEAR:2:2}${MONTH}${DAY}"
    
    # Update model names
    jq --arg model_date "$MODEL_DATE" '
      .models |= map(
        .name |= sub("_[0-9]{6}$"; "_\($model_date)")
      )
    ' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    # Update model signatures
    jq --arg model_date "$MODEL_DATE" '
      .models |= map(
        .signature |= sub("_[0-9]{6}$"; "_\($model_date)")
      )
    ' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    echo "  Config file generated successfully"
    echo "  Model date suffix: $MODEL_DATE"
    echo ""
    
    # Step 3: Run back test steps
    echo "========================================"
    echo "  Starting Back Test Execution"
    echo "========================================"
    
    BACKTEST_LOG_DIR="${LOG_DIR}/${DATE}"
    mkdir -p "$BACKTEST_LOG_DIR"
    
    LOGFILE_STEP1="${BACKTEST_LOG_DIR}/step1.log"
    LOGFILE_STEP2="${BACKTEST_LOG_DIR}/step2.log"
    LOGFILE_STEP3="${BACKTEST_LOG_DIR}/step3.log"
    
    # Step 3.1: Data preparation
    echo "  [Step 1/3] Data preparation (daily mode)..."
    rm -f data/A_stock/A_stock_daily.csv
    # rm -f data/A_stock/A_stock_hourly.csv

    # Kill existing agent tool process
    echo 'Kill existing agent tool process...'
    ps aux|grep agent_tools | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 5
    echo 'Kill existing trading steps...'
    ps aux|grep main_a_stock | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 1
    ps aux|grep astock_config | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 1
    echo 'done.'

    # 使用 tee 同时输出到日志文件和标准输出
    # Pass date range in YYYY-MM-DD format (no time component)
    sh scripts/main_a_stock_step1.sh "$INIT_DATE" "$END_DATE" 2>&1 | tee "$LOGFILE_STEP1"
    STEP1_EXIT_CODE=${PIPESTATUS[0]}
    if [ $STEP1_EXIT_CODE -ne 0 ]; then
        echo "  ❌ Step 1 failed with exit code $STEP1_EXIT_CODE"
        echo "  Log file: $LOGFILE_STEP1"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi
    echo "  ✅ Step 1 completed"
    sleep 5
    
    # Step 3.2: Start MCP services
    echo "  [Step 2/3] Starting MCP services..."
    # 使用 tee 同时输出到日志文件和标准输出
    nohup sh scripts/main_a_stock_step2.sh 2>&1 | tee "$LOGFILE_STEP2" &
    STEP2_PID=$!
    echo "  MCP services started (PID: $STEP2_PID)"
    sleep 10
    
    # Step 3.3: Run trading agent with specific config
    echo "  [Step 3/3] Running trading agent..."
    # 使用 tee 同时输出到日志文件和标准输出
    sh scripts/main_a_stock_step3.sh "$CONFIG_OUTPUT" 2>&1 | tee "$LOGFILE_STEP3"
    STEP3_EXIT_CODE=${PIPESTATUS[0]}
    
    # Kill MCP services
    echo "  Stopping MCP services..."
    ps aux | grep agent_tools | grep -v grep | awk '{print $2}' | xargs -I {} kill -9 {} 2>/dev/null
    sleep 2
    
    if [ $STEP3_EXIT_CODE -ne 0 ]; then
        echo "  ❌ Step 3 failed with exit code $STEP3_EXIT_CODE"
        echo "  Log file: $LOGFILE_STEP3"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi
    echo "  ✅ Step 3 completed"
    echo ""
    
    # Step 4: Remove used data from sse_pick_2025.csv (only after successful backtest)
    echo "  Cleaning up: Removing used data from sse_pick_2025.csv..."
    grep -v "^$DATE," "$SSE_PICK_2025_CSV" > "${SSE_PICK_2025_CSV}.tmp" && mv "${SSE_PICK_2025_CSV}.tmp" "$SSE_PICK_2025_CSV"
    REMAINING_COUNT=$(tail -n +2 "$SSE_PICK_2025_CSV" | wc -l)
    echo "  Remaining stocks in sse_pick_2025.csv: $REMAINING_COUNT"
    echo ""
    
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    echo "  ✅ Back test for date $DATE completed successfully"
    echo "  Logs saved to: $BACKTEST_LOG_DIR"
    echo ""
    
done

#echo 'cleaning...'
rm -f data/A_stock/A_stock_daily.csv
# rm -f data/A_stock/A_stock_hourly.csv

echo ""
echo "=========================================="
echo "Back Test Execution Summary"
echo "=========================================="
echo "Total dates in queue: $DATE_COUNT"
if [ $MAX_DATES -gt 0 ]; then
    echo "Dates processed in this run: $CURRENT (limited to $MAX_DATES)"
    REMAINING_DATES=$((DATE_COUNT - SUCCESS_COUNT))
    echo "Dates remaining: $REMAINING_DATES"
else
    echo "Dates processed: $CURRENT"
fi
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAIL_COUNT"
echo ""
echo "Configuration files:"
ls -1 "${CONFIG_OUTPUT_DIR}/astock_config_daily_2025"*.json 2>/dev/null | wc -l | xargs echo "Total config files:"
echo ""
echo "Back test logs saved to: $LOG_DIR"
echo ""
if [ $SUCCESS_COUNT -gt 0 ]; then
    echo "✅ Back test completed with $SUCCESS_COUNT successful runs"
fi
if [ $FAIL_COUNT -gt 0 ]; then
    echo "⚠️  $FAIL_COUNT back test runs failed. Check logs for details."
fi
if [ $MAX_DATES -gt 0 ] && [ $CURRENT -ge $MAX_DATES ]; then
    REMAINING_DATES=$(tail -n +2 "$SSE_PICK_2025_CSV" | cut -d',' -f1 | sort -u | wc -l)
    if [ $REMAINING_DATES -gt 0 ]; then
        echo ""
        echo "💡 To continue with next batch, run:"
        echo "   sh scripts/start_back_test.sh $MAX_DATES"
    fi
fi
echo "=========================================="
echo ""
