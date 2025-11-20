#!/bin/bash

# Kill existing agent tool process 
echo 'Kill existing agent tool process...'
ps aux|grep agent_tools | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
sleep 5
echo 'Kill existing trading steps...'
ps aux|grep main_a_stock_step | grep -v grep | awk '{print $2}' |xargs -I {} sudo kill -9 {}
sleep 1
echo 'done.'

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

echo 'step2 starting...'
nohup sh scripts/main_a_stock_step2.sh > logs/step2.log 2>&1 &
sleep 2
echo 'step3 starting...'
nohup sh scripts/main_a_stock_step3.sh > logs/step3.log 2>&1 &
echo 'done.'
