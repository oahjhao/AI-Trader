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

# Parse command line argument for number of configs to process
MAX_CONFIGS=${1:-0}  # Default to 0 (process all configs if no argument provided)

# Define paths
SSE_PICK_2025_CSV="data/A_stock/sse_pick_2025.csv"
SSE_PICK_OUTPUT="data/A_stock/sse_pick.csv"
CONFIG_TEMPLATE="configs/default_astock_config.json"
CONFIG_OUTPUT_DIR="configs/configs_sse_pick_2025"
LOG_DIR="logs/backtest"

# Create necessary directories
mkdir -p "$CONFIG_OUTPUT_DIR"
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Starting Back Test System"
echo "=========================================="
echo "Project Root: $PROJECT_ROOT"
echo "Config Directory: $CONFIG_OUTPUT_DIR"
echo "Log Directory: $LOG_DIR"
if [ $MAX_CONFIGS -gt 0 ]; then
    echo "Max configs to process: $MAX_CONFIGS"
else
    echo "Max configs to process: ALL"
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

# ============================================================
# Phase 1: Generate all config files
# ============================================================
echo "=========================================="
echo "Phase 1: Generating Config Files"
echo "=========================================="

# Extract unique dates from sse_pick_2025.csv (skip header)
DATES=$(tail -n +2 "$SSE_PICK_2025_CSV" | cut -d',' -f1 | sort -u)

DATE_COUNT=$(echo "$DATES" | wc -l)
echo "Found $DATE_COUNT unique dates to generate configs for"
echo ""

CONFIG_GEN_COUNT=0

# Generate config for each date
for DATE in $DATES; do
    CONFIG_GEN_COUNT=$((CONFIG_GEN_COUNT + 1))
    
    echo "[$CONFIG_GEN_COUNT/$DATE_COUNT] Generating config for date: $DATE"
    
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
    
    # Step 2: Generate config file
    CONFIG_OUTPUT="${CONFIG_OUTPUT_DIR}/astock_config_daily_${DATE}.json"
    
    # Skip if config already exists
    if [ -f "$CONFIG_OUTPUT" ]; then
        echo "  Config already exists, skipping..."
        echo ""
        continue
    fi
    
    # Copy template and update dates
    cp "$CONFIG_TEMPLATE" "$CONFIG_OUTPUT"
    
    # Update agent_type to daily mode (BaseAgentAStock instead of BaseAgentAStockHourly)
    jq '.agent_type = "BaseAgentAStock"' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
    # Add backtest mode flag to disable search capability
    jq '.backtest_mode = true' "$CONFIG_OUTPUT" > "${CONFIG_OUTPUT}.tmp" && mv "${CONFIG_OUTPUT}.tmp" "$CONFIG_OUTPUT"
    
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
    
    echo "  ✅ Generated: $CONFIG_OUTPUT"
    echo "     Init Date: $INIT_DATE"
    echo "     End Date:  $END_DATE"
    echo ""
done

echo "=========================================="
echo "Config Generation Complete"
echo "=========================================="
echo "Total configs generated: $CONFIG_GEN_COUNT"
echo ""

# ============================================================
# Phase 2: Execute back tests
# ============================================================
echo "=========================================="
echo "Phase 2: Executing Back Tests"
echo "=========================================="
echo ""

# Get all config files sorted by date
CONFIG_FILES=$(ls -1 "${CONFIG_OUTPUT_DIR}/astock_config_daily_"*.json 2>/dev/null | sort)
TOTAL_CONFIGS=$(echo "$CONFIG_FILES" | grep -c "^" || echo 0)

if [ $TOTAL_CONFIGS -eq 0 ]; then
    echo "No config files found in $CONFIG_OUTPUT_DIR"
    exit 1
fi

echo "Found $TOTAL_CONFIGS config files to process"
echo ""

# Process counter
CURRENT=0
SUCCESS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

# Process each config
for CONFIG_FILE in $CONFIG_FILES; do
    CURRENT=$((CURRENT + 1))
    
    # Check if we've reached the maximum number of configs to process
    if [ $MAX_CONFIGS -gt 0 ] && [ $CURRENT -gt $MAX_CONFIGS ]; then
        echo "=========================================="
        echo "Reached maximum configs limit ($MAX_CONFIGS)"
        echo "Stopping back test execution"
        echo "=========================================="
        echo ""
        break
    fi
    
    # Extract date from config filename
    CONFIG_BASENAME=$(basename "$CONFIG_FILE")
    DATE=$(echo "$CONFIG_BASENAME" | sed 's/astock_config_daily_\([0-9]\{8\}\).json/\1/')
    
    YEAR=${DATE:0:4}
    MONTH=${DATE:4:2}
    DAY=${DATE:6:2}
    INIT_DATE="$YEAR-$MONTH-$DAY"
    
    echo "=========================================="
    echo "Processing config: $CONFIG_BASENAME [$CURRENT/$TOTAL_CONFIGS]"
    echo "Date: $INIT_DATE"
    echo "=========================================="
    
    # Step 1: Generate sse_pick.csv from sse_pick_2025.csv for this date
    echo "  Generating sse_pick.csv for date $DATE..."
    
    # Extract data for this date from sse_pick_2025.csv
    # Create header (without date column)
    echo "con_code,stock_name" > "$SSE_PICK_OUTPUT"
    # Extract rows for this date and remove the date column (cut -d',' -f2,3)
    grep "^$DATE," "$SSE_PICK_2025_CSV" | cut -d',' -f2,3 >> "$SSE_PICK_OUTPUT"
    
    STOCK_COUNT=$(tail -n +2 "$SSE_PICK_OUTPUT" | wc -l)
    if [ $STOCK_COUNT -eq 0 ]; then
        echo "  ⚠️  No stocks found for date $DATE, skipping..."
        SKIP_COUNT=$((SKIP_COUNT + 1))
        echo ""
        continue
    fi
    
    echo "  Generated sse_pick.csv with $STOCK_COUNT stocks"
    echo ""
    
    # Run back test steps
    echo "========================================"
    echo "  Starting Back Test Execution"
    echo "========================================"
    
    BACKTEST_LOG_DIR="${LOG_DIR}/${DATE}"
    mkdir -p "$BACKTEST_LOG_DIR"
    
    LOGFILE_STEP1="${BACKTEST_LOG_DIR}/step1.log"
    LOGFILE_STEP2="${BACKTEST_LOG_DIR}/step2.log"
    LOGFILE_STEP3="${BACKTEST_LOG_DIR}/step3.log"
    
    # Calculate end date from config
    if [[ "$OSTYPE" == "darwin"* ]]; then
        END_DATE=$(date -j -v+7d -f "%Y-%m-%d" "$INIT_DATE" "+%Y-%m-%d")
    else
        END_DATE=$(date -d "$INIT_DATE +7 days" "+%Y-%m-%d")
    fi
    
    # Step 1: Data preparation
    echo "  [Step 1/3] Data preparation (daily mode)..."
    rm -f data/A_stock/A_stock_daily.csv
    # rm -f data/A_stock/A_stock_hourly.csv

    # Kill existing agent tool process
    echo '  Kill existing agent tool process...'
    ps aux|grep agent_tools | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 5
    echo '  Kill existing trading steps...'
    ps aux|grep main_a_stock | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 1
    ps aux|grep astock_config | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
    sleep 1
    echo '  Done.'

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
    
    # Step 2: Start MCP services
    echo "  [Step 2/3] Starting MCP services..."
    # 使用 tee 同时输出到日志文件和标准输出
    nohup sh scripts/main_a_stock_step2.sh 2>&1 | tee "$LOGFILE_STEP2" &
    STEP2_PID=$!
    echo "  MCP services started (PID: $STEP2_PID)"
    sleep 10
    
    # Step 3: Run trading agent with specific config
    echo "  [Step 3/3] Running trading agent..."
    # 使用 tee 同时输出到日志文件和标准输出
    sh scripts/main_a_stock_step3.sh "$CONFIG_FILE" 2>&1 | tee "$LOGFILE_STEP3"
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
echo "Total configs available: $TOTAL_CONFIGS"
if [ $MAX_CONFIGS -gt 0 ]; then
    echo "Configs processed in this run: $CURRENT (limited to $MAX_CONFIGS)"
    REMAINING_CONFIGS=$((TOTAL_CONFIGS - CURRENT))
    echo "Configs remaining: $REMAINING_CONFIGS"
else
    echo "Configs processed: $CURRENT"
fi
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAIL_COUNT"
echo "Skipped: $SKIP_COUNT"
echo ""
echo "Configuration files directory: $CONFIG_OUTPUT_DIR"
echo "Total config files: $(ls -1 "${CONFIG_OUTPUT_DIR}/astock_config_daily_"*.json 2>/dev/null | wc -l)"
echo ""
echo "Back test logs saved to: $LOG_DIR"
echo ""
if [ $SUCCESS_COUNT -gt 0 ]; then
    echo "✅ Back test completed with $SUCCESS_COUNT successful runs"
fi
if [ $FAIL_COUNT -gt 0 ]; then
    echo "⚠️  $FAIL_COUNT back test runs failed. Check logs for details."
fi
if [ $SKIP_COUNT -gt 0 ]; then
    echo "ℹ️  $SKIP_COUNT configs were skipped (no stock data found)"
fi
if [ $MAX_CONFIGS -gt 0 ] && [ $CURRENT -ge $MAX_CONFIGS ]; then
    REMAINING_CONFIGS=$((TOTAL_CONFIGS - CURRENT))
    if [ $REMAINING_CONFIGS -gt 0 ]; then
        echo ""
        echo "💡 To continue with next batch, run:"
        echo "   sh scripts/start_back_test.sh $MAX_CONFIGS"
    fi
fi
echo "=========================================="
echo ""
