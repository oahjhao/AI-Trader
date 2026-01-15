#!/bin/bash

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

# 接受配置文件作为参数，如果没有提供则使用默认配置
CONFIG_FILE=${1:-"configs/astock_config_hourly.json"}

echo "🤖 正在启动主交易智能体（A股模式）..."
echo "📝 使用配置文件: $CONFIG_FILE"
date
/home/ec2-user/AI-Trader/venv/bin/python main.py "$CONFIG_FILE"  # 运行A股配置
echo "✅ AI-Trader 已停止"
