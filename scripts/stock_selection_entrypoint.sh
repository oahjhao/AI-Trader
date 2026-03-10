#\!/bin/bash
# Stock Selection Entrypoint for Container
set -e

echo "Starting Stock Selection (Container)..."
echo "============================================"

BASE_DIR="/home/ec2-user/AI-Trader"
DATA_DIR="/home/ec2-user/AI-Trader/data/A_stock"
STOCK_SELECTION_DIR="$BASE_DIR/scripts/stock_selection"

SELECTION_DATE="${SELECTION_DATE:-}"
UPDATE_MODE="${UPDATE_MODE:-incremental}"

echo "Environment Variables:"
echo "   SELECTION_DATE: ${SELECTION_DATE:-'(today)'}"
echo "   UPDATE_MODE:    $UPDATE_MODE"
echo "============================================"

# 设置 PYTHONPATH 确保模块导入正常
export PYTHONPATH="$STOCK_SELECTION_DIR:$PYTHONPATH"
cd "$STOCK_SELECTION_DIR"

if [ "$UPDATE_MODE" \!= "none" ]; then
    echo ""
    echo "Step 1: Data Update ($UPDATE_MODE)"
    echo "============================================"
    
    if [ "$UPDATE_MODE" = "full" ]; then
        python incremental_update.py --full
    else
        python incremental_update.py --days 30
    fi
    echo "Data update completed"
else
    echo "Step 1: Skip data update"
fi

echo ""
echo "Step 2: Run Stock Selection"
echo "============================================"

if [ -n "$SELECTION_DATE" ]; then
    DATE_ARG="${SELECTION_DATE//-/}"
    python stock_selector.py --date "$DATE_ARG"
else
    python stock_selector.py
fi

echo ""
echo "============================================"
echo "Stock Selection Complete\!"
echo "============================================"

if [ -n "$SELECTION_DATE" ]; then
    RESULT_FILE="$DATA_DIR/sse_pick_${DATE_ARG}.csv"
else
    TODAY=$(date +%Y%m%d)
    RESULT_FILE="$DATA_DIR/sse_pick_${TODAY}.csv"
fi

if [ -f "$RESULT_FILE" ]; then
    echo ""
    echo "Selection Results:"
    cat "$RESULT_FILE"
fi
