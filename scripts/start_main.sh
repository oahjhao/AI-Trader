#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin"

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

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

JSON_FILE="configs/astock_config_hourly.json"
TODAY=$(date +%Y-%m-%d' '%H:%M:%S)
jq --arg date "$TODAY" '.date_range.end_date = $date' "$JSON_FILE" > "${JSON_FILE}.tmp" && mv "${JSON_FILE}.tmp" "$JSON_FILE"
echo "$(date): Updated end_date to $TODAY in $JSON_FILE"

TODAY_LOG=$(date +%Y-%m-%d'-'%H:%M:%S)
LOGFILE_STEP1="logs/step1.log"
LOGFILE_STEP2="logs/step2.log"
LOGFILE_STEP3="logs/step3.log"

echo 'step1 starting...'
sh scripts/main_a_stock_step1.sh 2>&1 | tee "$LOGFILE_STEP1"
sleep 10
echo 'step2 starting...'
nohup sh scripts/main_a_stock_step2.sh 2>&1 | tee "$LOGFILE_STEP2" &
sleep 5
echo 'step3 starting...'
nohup sh scripts/main_a_stock_step3.sh 2>&1 | tee "$LOGFILE_STEP3" &
echo 'done.'
