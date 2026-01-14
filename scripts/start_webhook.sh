#!/bin/bash
# webhook 推送服务启动脚本

set -e

# 切换到项目根目录
cd "$(dirname "$0")/.."

echo "🚀 启动 Webhook 推送服务..."

# 检查配置文件
if [ ! -f "./configs/webhook_config.json" ]; then
    echo "❌ 配置文件不存在: ./configs/webhook_config.json"
    echo "请先配置 webhook_config.json 文件"
    exit 1
fi

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3"
    exit 1
fi

# 检查依赖
echo "🔍 检查依赖包..."
python3 -c "import requests, schedule" 2>/dev/null || {
    echo "📦 安装依赖包..."
    pip3 install requests schedule
}

# 启动服务
echo "📢 启动 Webhook 服务..."
python3 ./webhook/dingtalk_webhook.py