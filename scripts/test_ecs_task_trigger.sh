#!/bin/bash
# 测试脚本：在 frontend 容器内手动触发 ECS 任务
# 用于验证 aws_ecs_run_all.sh 脚本在容器环境中是否能正常运行

set -e

echo "=========================================="
echo "AI-Trader ECS 任务触发测试"
echo "=========================================="
echo "执行时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 检查环境
echo "[1/4] 检查运行环境..."
echo "  - 当前用户: $(whoami)"
echo "  - 当前目录: $(pwd)"
echo "  - 容器主机名: $(hostname)"

# 检查必需工具
echo ""
echo "[2/4] 检查必需工具..."
for cmd in aws jq bash; do
  if command -v $cmd &> /dev/null; then
    echo "  ✓ $cmd: $(command -v $cmd)"
  else
    echo "  ✗ $cmd: 未安装"
    exit 1
  fi
done

# 检查脚本是否存在
echo ""
echo "[3/4] 检查 ECS 编排脚本..."
if [ -f "/usr/local/bin/aws_ecs_run_all.sh" ]; then
  echo "  ✓ aws_ecs_run_all.sh 已找到"
  ls -lh /usr/local/bin/aws_ecs_run_all.sh
else
  echo "  ✗ aws_ecs_run_all.sh 未找到"
  exit 1
fi

# 检查 EFS 挂载和配置文件
echo ""
echo "[4/4] 检查 EFS 挂载和配置文件..."
CONFIG_FILE="${1:-/mnt/efs/configs/astock_config_hourly.json}"

if [ -f "$CONFIG_FILE" ]; then
  echo "  ✓ 配置文件存在: $CONFIG_FILE"
  echo "  配置文件大小: $(du -h $CONFIG_FILE | cut -f1)"
else
  echo "  ✗ 配置文件不存在: $CONFIG_FILE"
  echo "  尝试查找其他配置文件..."
  ls -lh /mnt/efs/configs/*.json 2>/dev/null || echo "  未找到任何配置文件"
  exit 1
fi

# 检查 AWS 凭证
echo ""
echo "检查 AWS 认证..."
if aws sts get-caller-identity &> /dev/null; then
  echo "  ✓ AWS 认证成功"
  aws sts get-caller-identity
else
  echo "  ✗ AWS 认证失败，请检查环境变量："
  echo "    - AWS_ACCESS_KEY_ID"
  echo "    - AWS_SECRET_ACCESS_KEY"
  echo "    - AWS_REGION"
  exit 1
fi

echo ""
echo "=========================================="
echo "环境检查完成，准备执行任务"
echo "=========================================="
echo ""
echo "是否立即执行 ECS 任务？(会实际调用 AWS API)"
echo "配置文件: $CONFIG_FILE"
echo ""
read -p "输入 'yes' 继续: " confirm

if [ "$confirm" != "yes" ]; then
  echo "已取消执行"
  exit 0
fi

echo ""
echo "开始执行任务..."
echo "日志将保存到: /var/log/cron-trader.log"
echo ""

# 执行脚本（实时模式，不指定日期）
/usr/local/bin/aws_ecs_run_all.sh "$CONFIG_FILE" | tee -a /var/log/cron-trader.log

echo ""
echo "=========================================="
echo "任务执行完成"
echo "=========================================="
