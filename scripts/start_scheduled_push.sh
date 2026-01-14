#!/bin/bash
# 定时推送服务启动脚本

set -e

# 切换到项目根目录
cd "$(dirname "$0")/.."

echo "🚀 启动定时推送服务..."

# 检查虚拟环境
if [ ! -d "./venv" ]; then
    echo "❌ 虚拟环境不存在，请先创建虚拟环境"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "❌ .env 文件不存在，请先创建 .env 文件"
    exit 1
fi

# 检查必要配置
if ! grep -q "WEBHOOK_URL\|DINGTALK_WEBHOOK_URL" .env; then
    echo "❌ 请在 .env 文件中配置 Webhook URL"
    echo "   示例:"
    echo "   DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
    echo "   或"
    echo "   WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
    exit 1
fi

# 检查依赖
echo "🔍 检查依赖包..."
python3 -c "import requests, schedule, pandas" 2>/dev/null || {
    echo "📦 安装依赖包..."
    pip3 install requests schedule pandas
}

# 执行即时推送
echo "📢 执行即时推送..."
echo "推送信息将在开头包含 position 关键字"
echo ""

python3 ./scripts/scheduled_push.py