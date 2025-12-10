#!/bin/bash

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

#JSON_FILE="configs/astock_test_config.json"
#TODAY=$(date +%Y-%m-%d)
#jq --arg date "$TODAY" '.date_range.end_date = $date' "$JSON_FILE" > "${JSON_FILE}.tmp" && mv "${JSON_FILE}.tmp" "$JSON_FILE"
#echo "$(date): Updated end_date to $TODAY in $JSON_FILE"

echo 'step1 starting...'
sh scripts/main_a_stock_step1.sh > logs/step1.log 2>&1
sleep 5
echo 'step3 starting...'
nohup sh scripts/main_a_stock_step3_test.sh > logs/step3_test.log 2>&1 &
echo 'done.'
