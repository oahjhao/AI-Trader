#!/bin/bash

# 获取项目根目录（scripts/ 的父目录）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

echo "🔧 正在启动 MCP 服务..."
date
cd agent_tools
/home/ec2-user/AI-Trader/venv/bin/python start_mcp_services.py
cd ..
