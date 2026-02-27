#!/bin/bash
# 生成回测汇总 Excel 的开发环境辅助脚本
# 使用示例：
#   ./generate_backtest_excel.sh agent_data_astock 2025
#   ./generate_backtest_excel.sh agent_data_astock 2025 cn

set -euo pipefail

# -------- 参数解析 --------
DATA_GROUP="${1:-agent_data_astock}"   # 如：agent_data_astock
YEAR="${2:-$(date +%Y)}"               # 如：2025
MARKET="${3:-cn}"                      # cn / us / crypto

EFS_ROOT="/mnt/efs/ai-trader"
IMAGE="${IMAGE:-trader-app}"

echo ">>> Data group : ${DATA_GROUP}"
echo ">>> Year       : ${YEAR}"
echo ">>> Market     : ${MARKET}"
echo ">>> EFS root   : ${EFS_ROOT}"
echo ">>> Docker img : ${IMAGE}"

# -------- 基本检查 --------
if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未找到 docker 命令，请先安装 Docker。"
  exit 1
fi

if [ ! -d "${EFS_ROOT}" ]; then
  echo "[ERROR] EFS 根目录不存在：${EFS_ROOT}"
  echo "        请确认 EFS 已挂载到该路径。"
  exit 1
fi

# 可选：检查子目录
for sub in configs data logs; do
  if [ ! -d "${EFS_ROOT}/${sub}" ]; then
    echo "[WARN] 目录缺失：${EFS_ROOT}/${sub}（继续执行，若不需要可忽略）"
  fi
done

# -------- 检查镜像，不存在则自动构建 --------
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "[INFO] 未找到镜像 ${IMAGE}，尝试从 EFS 根目录构建..."
  docker build -t "${IMAGE}" "${EFS_ROOT}"
fi

# -------- 组装 Docker 挂载参数 --------
VOLUMES=(
  "-v" "${EFS_ROOT}/configs:/home/ec2-user/AI-Trader/configs"
  "-v" "${EFS_ROOT}/data:/home/ec2-user/AI-Trader/data"
  "-v" "${EFS_ROOT}/logs:/home/ec2-user/AI-Trader/logs"
)

# 如果有 .env，就挂进去，方便加载 OPENAI_API_KEY 等
if [ -f "${EFS_ROOT}/.env" ]; then
  VOLUMES+=("-v" "${EFS_ROOT}/.env:/home/ec2-user/AI-Trader/.env:ro")
fi

# -------- 在容器中执行 Python 生成 Excel --------
echo ">>> 启动容器并执行 export_yearly_excel ..."

docker run --rm \
  "${VOLUMES[@]}" \
  -e TZ=Asia/Shanghai \
  -e LOG_PATH="./data/${DATA_GROUP}" \
  "${IMAGE}" \
  bash -c "cd /home/ec2-user/AI-Trader && python -c '
from tools.result_tools import export_yearly_excel
import os
print(\"Starting Excel generation...\")
data_group = \"${DATA_GROUP}\"
year = ${YEAR}
market = \"${MARKET}\"
print(\"Parameters: data_group={}, year={}, market={}\".format(data_group, year, market))
log_path = os.getenv(\"LOG_PATH\", \"N/A\")
print(\"LOG_PATH: {}\".format(log_path))
p = export_yearly_excel(data_group, year, market=market)
print(\"✅ Excel generated at: {}\".format(p))
'"

OUT_PATH="${EFS_ROOT}/data/exports/backtest_summary_${DATA_GROUP}_${YEAR}.xlsx"
echo ">>> 本机 EFS 路径：${OUT_PATH}"
echo ">>> 前端访问 URL：/data/exports/backtest_summary_${DATA_GROUP}_${YEAR}.xlsx"
