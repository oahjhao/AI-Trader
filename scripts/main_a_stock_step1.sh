#!/bin/bash

# A股数据准备
# 参数: $1 = 起始日期 (YYYY-MM-DD), $2 = 结束日期 (YYYY-MM-DD)

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

cd data/A_stock

# 解析时间参数，如果没有提供则使用默认值（实盘模式）
START_DATE=${1:-""}
END_DATE=${2:-""}

# for alphavantage
#python get_daily_price_alphavantage.py
#python merge_jsonl_alphavantage.py
# # for tushare
date

if [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    echo "回测模式: 数据范围 $START_DATE 到 $END_DATE"
    /home/ec2-user/AI-Trader/venv/bin/python get_daily_price_tushare.py "$START_DATE" "$END_DATE"
    sleep 2
    /home/ec2-user/AI-Trader/venv/bin/python get_daily_price_ef.py "$START_DATE" "$END_DATE"
    sleep 5
    /home/ec2-user/AI-Trader/venv/bin/python get_hourly_price_ef.py "$START_DATE" "$END_DATE"
    sleep 5
else
    echo "实盘模式: 使用默认时间范围"
    /home/ec2-user/AI-Trader/venv/bin/python get_daily_price_tushare.py
    sleep 2
    /home/ec2-user/AI-Trader/venv/bin/python get_daily_price_ef.py
    sleep 5
    /home/ec2-user/AI-Trader/venv/bin/python get_hourly_price_ef.py
    sleep 5
fi

/home/ec2-user/AI-Trader/venv/bin/python merge_jsonl_daily_ef.py
sleep 2
/home/ec2-user/AI-Trader/venv/bin/python merge_jsonl_hourly_ef.py

cd ..
