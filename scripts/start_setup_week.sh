#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin"

# Kill existing agent tool process
# echo 'Kill existing agent tool process...'
# ps aux|grep agent_tools | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
# sleep 5
# echo 'Kill existing trading steps...'
# ps aux|grep main_a_stock | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
# sleep 1
# ps aux|grep astock_config | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
# sleep 1
# echo 'done.'

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

JSON_FILE="config/astock_config_hourly.json"
YAML_FILE="docs/config.yaml"

TODAY=$(date +%Y-%m-%d' '%H:%M:%S)
TODAY_30after=$(date -d "+30 minutes" '+%Y-%m-%d %H:%M:%S')
jq --arg date "$TODAY" '.date_range.init_date = $date' "$JSON_FILE" > "${JSON_FILE}.tmp" && mv "${JSON_FILE}.tmp" "$JSON_FILE"
jq --arg date "$TODAY_30after" '.date_range.end_date = $date' "$JSON_FILE" > "${JSON_FILE}.tmp" && mv "${JSON_FILE}.tmp" "$JSON_FILE"
echo "$(date): Updated init_date to $TODAY and end_date to $TODAY_30after in $JSON_FILE"
#grep -E "(init_date|end_date): " "$JSON_FILE"

TODAY_DATE=$(date +%y%m%d)
jq --arg today "$TODAY_DATE" '
  .models |= map(
    .name   |= sub("_[0-9]{6}$"; "_\($today)")
  )
' "$JSON_FILE" > "${JSON_FILE}.tmp" &&  mv "${JSON_FILE}.tmp" "$JSON_FILE"

jq --arg today "$TODAY_DATE" '
  .models |= map(
    .signature |= sub("_[0-9]{6}$"; "_\($today)")
  )
' "$JSON_FILE" > "${JSON_FILE}.tmp" &&  mv "${JSON_FILE}.tmp" "$JSON_FILE"
echo "$JSON_FILE"
grep -E "(name|signature): " "$JSON_FILE" 

# 执行替换（精确匹配 folder 和 display_name 行）
sed -E "s/(_[0-9]{6})([\"'\` ]*$)/_$TODAY_DATE\2/g" "$YAML_FILE" > "${YAML_FILE}.tmp" && mv "${YAML_FILE}.tmp" "$YAML_FILE"
echo "$YAML_FILE"
#grep -E "(folder|display_name): " "$YAML_FILE"

#echo 'cleaning...'
rm -f data/A_stock/A_stock_daily.csv
rm -f data/A_stock/A_stock_hourly.csv

#RELEASE_BRANCH="release/hourly_auto_trade"
#echo 'git pull...'
#git fetch origin
#git checkout -B $RELEASE_BRANCH
#git reset --hard origin/$RELEASE_BRANCH

echo 'step1 starting...'
sh scripts/main_a_stock_step1.sh > logs/step1.log 2>&1
echo 'done.'
