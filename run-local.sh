#!/bin/bash
# ============================================
# AI-Trader 本地容器化运行脚本
# ============================================
# 
# 使用 Docker 容器运行 AI-Trader，替代 AWS ECS 部署
#
# 快速示例:
#   BACKTEST 模式: ./run-local.sh configs/astock_config_hourly_260202.json 2026-02-02 2026-02-09
#   LIVE 模式:     ./run-local.sh configs/astock_config_hourly_260202.json --live
#   指定 Agent:    ./run-local.sh configs/xxx.json --agent DS_pick_tech_260202
#   跳过数据准备:  ./run-local.sh configs/xxx.json --skip-data-prep
#   仅数据准备:    ./run-local.sh --data-prep-only configs/xxx.json 2026-01-01 2026-01-21
#   仅选股:        ./run-local.sh --stock-selection --date 2026-03-06
#   选股+数据更新: ./run-local.sh --stock-selection --update-data
#
# 命令行选项:
#   --live              LIVE 实时交易模式
#   --agent SIG         只运行指定的 Agent
#   --skip-data-prep    跳过数据准备步骤
#   --data-prep-only    仅运行数据准备
#   --stock-selection   运行选股策略
#   --update-data       选股前更新数据
#   --full-update       全量数据更新
#   --date DATE         选股日期
#   --build             强制重新构建镜像
#   -h, --help          显示帮助信息

set -e

# ============================================
# 项目路径配置
# ============================================
PROJECT_ROOT="/home/admin/.openclaw/workspace/projects/AI-Trader"
DATA_ROOT="/home/admin/.openclaw/data/ai-trader"

# Docker 配置
IMAGE_NAME="ai-trader:latest"
CONTAINER_DATA_PATH="/home/ec2-user/AI-Trader"

# ============================================
# 解析命令行选项
# ============================================
AGENT_FILTER=""
SKIP_DATA_PREP=false
LIVE_MODE=false
FORCE_BUILD=false
DATA_PREP_ONLY=false
STOCK_SELECTION=false
UPDATE_DATA=false
FULL_UPDATE=false
SELECTION_DATE=""

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      AGENT_FILTER="$2"
      shift 2
      ;;
    --skip-data-prep)
      SKIP_DATA_PREP=true
      shift
      ;;
    --data-prep-only)
      DATA_PREP_ONLY=true
      shift
      ;;
    --stock-selection)
      STOCK_SELECTION=true
      shift
      ;;
    --update-data)
      UPDATE_DATA=true
      shift
      ;;
    --full-update)
      FULL_UPDATE=true
      shift
      ;;
    --date)
      SELECTION_DATE="$2"
      shift 2
      ;;
    --live)
      LIVE_MODE=true
      shift
      ;;
    --build)
      FORCE_BUILD=true
      shift
      ;;
    -h|--help)
      cat << EOF
用法: $0 [CONFIG_FILE] [INIT_DATE] [END_DATE] [选项]

参数:
  CONFIG_FILE  配置文件路径（相对于 configs/ 目录）
  INIT_DATE    起始日期 YYYY-MM-DD（可选，用于回测）
  END_DATE     结束日期 YYYY-MM-DD（可选，用于回测）

选项:
  --live              LIVE 实时交易模式
  --agent SIGNATURE   只运行指定的 Agent
  --skip-data-prep    跳过数据准备步骤
  --data-prep-only    仅运行数据准备（不运行 Agent）
  --stock-selection   运行选股策略
  --update-data       选股前更新数据
  --full-update       全量数据更新（首次运行）
  --date DATE         选股日期 YYYY-MM-DD
  --build             强制重新构建 Docker 镜像

示例:
  # 回测模式
  $0 configs/astock_config_hourly_260202.json 2025-01-01 2025-01-21

  # LIVE 实时交易
  $0 configs/astock_config_hourly_260202.json --live

  # 只运行指定 Agent
  $0 configs/astock_config_hourly_260202.json --agent DS_pick_monk_260202

  # 仅数据准备
  $0 --data-prep-only configs/astock_config_hourly_260202.json 2025-01-01 2025-01-21

  # 仅选股（使用今天日期）
  $0 --stock-selection

  # 选股并更新数据
  $0 --stock-selection --update-data --date 2026-03-06

  # 强制重新构建镜像
  $0 configs/astock_config_hourly_260202.json --build

EOF
      exit 0
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

echo "=========================================="
echo "🖥️  AI-Trader 本地容器化运行"
echo "=========================================="

if [ "$LIVE_MODE" = true ]; then
  echo "[INFO] 🚀 运行模式: LIVE (实时交易)"
fi
if [ -n "$AGENT_FILTER" ]; then
  echo "[INFO] 🎯 指定运行 Agent: $AGENT_FILTER"
fi
if [ "$SKIP_DATA_PREP" = true ]; then
  echo "[INFO] ⏭️  跳过数据准备"
fi

# ============================================
# 纯 bash JSON 解析函数
# ============================================
parse_json_value() {
  local json_file="$1"
  local key_path="$2"
  
  if [ ! -f "$json_file" ]; then
    return 1
  fi
  
  case "$key_path" in
    "date_range.init_date")
      grep -o '"init_date"[[:space:]]*:[[:space:]]*"[^"]*"' "$json_file" | sed 's/.*"\([^"]*\)"$/\1/' | head -1
      ;;
    "date_range.end_date")
      grep -o '"end_date"[[:space:]]*:[[:space:]]*"[^"]*"' "$json_file" | sed 's/.*"\([^"]*\)"$/\1/' | head -1
      ;;
    "models[].signature")
      local in_model=false
      local is_enabled=false
      local signature=""
      
      while IFS= read -r line; do
        if echo "$line" | grep -q '"name"[[:space:]]*:'; then
          in_model=true
          is_enabled=false
          signature=""
        fi
        
        if [ "$in_model" = true ]; then
          if echo "$line" | grep -q '"signature"[[:space:]]*:'; then
            signature=$(echo "$line" | sed 's/.*"signature"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
          fi
          
          if echo "$line" | grep -q '"enabled"[[:space:]]*:[[:space:]]*true'; then
            is_enabled=true
          fi
          
          if echo "$line" | grep -q '}'; then
            if [ "$is_enabled" = true ] && [ -n "$signature" ]; then
              echo "$signature"
            fi
            in_model=false
          fi
        fi
      done < "$json_file"
      ;;
  esac
}

modify_json_end_date() {
  local json_file="$1"
  local new_end_date="$2"
  
  if [ ! -f "$json_file" ]; then
    return 1
  fi
  
  # 使用 Python 处理，避免 sed 对空格的问题
  python3 -c "
import json
import sys
with open('$json_file', 'r') as f:
    config = json.load(f)
config['date_range']['end_date'] = '$new_end_date'
with open('$json_file', 'w') as f:
    json.dump(config, f, indent=2)
" 2>/dev/null
  return $?
}

# ============================================
# 加载环境变量
# ============================================
load_env_file() {
  local env_files=(
    "$DATA_ROOT/.env"
    "$PROJECT_ROOT/.env"
    "/home/admin/.openclaw/.env"
  )
  
  for env_file in "${env_files[@]}"; do
    if [ -f "$env_file" ]; then
      echo "[INFO] 加载环境变量: $env_file"
      set -a
      source "$env_file"
      set +a
      return 0
    fi
  done
}

load_env_file

# ============================================
# 解析配置参数
# ============================================
CONFIG_FILE="${ARGS[0]:-configs/astock_config_hourly.json}"

# 智能路径解析
if [[ "$CONFIG_FILE" != /* ]]; then
  # 相对路径，尝试多个位置
  if [ -f "$DATA_ROOT/$CONFIG_FILE" ]; then
    CONFIG_FILE="$DATA_ROOT/$CONFIG_FILE"
  elif [ -f "$DATA_ROOT/configs/${CONFIG_FILE##*/}" ]; then
    CONFIG_FILE="$DATA_ROOT/configs/${CONFIG_FILE##*/}"
  elif [ -f "$PROJECT_ROOT/$CONFIG_FILE" ]; then
    CONFIG_FILE="$PROJECT_ROOT/$CONFIG_FILE"
  fi
fi

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[ERROR] 配置文件不存在: $CONFIG_FILE"
  exit 1
fi

echo "[INFO] 📄 配置文件: $CONFIG_FILE"

INIT_DATE="${ARGS[1]:-}"
END_DATE="${ARGS[2]:-}"

# 从配置文件名提取日期后缀
DATE_SUFFIX=""
if [[ $CONFIG_FILE =~ _([0-9]{8})\.json$ ]]; then
  DATE_SUFFIX="${BASH_REMATCH[1]}"
  echo "[INFO] 📅 日期后缀: $DATE_SUFFIX"
fi

# 自动检测回测模式
if [ -z "$INIT_DATE" ] && [ -z "$END_DATE" ] && [ "$LIVE_MODE" = false ]; then
  _cfg_init=$(parse_json_value "$CONFIG_FILE" "date_range.init_date")
  _cfg_end=$(parse_json_value "$CONFIG_FILE" "date_range.end_date")
  
  if [ -n "$_cfg_init" ] && [ -n "$_cfg_end" ]; then
    _end_date_only=$(echo "$_cfg_end" | cut -d' ' -f1)
    _today=$(TZ='Asia/Shanghai' date +%Y-%m-%d)
    
    if [[ "$_end_date_only" < "$_today" ]]; then
      INIT_DATE="$_cfg_init"
      END_DATE="$_cfg_end"
      echo "[INFO] 📅 自动检测到回测模式: $INIT_DATE ~ $END_DATE"
    fi
  fi
fi

# ============================================
# LIVE 模式处理
# ============================================
if [ "$LIVE_MODE" = true ]; then
  echo "[INFO] 🔧 LIVE模式：更新配置文件 end_date"
  
  # 小时级 Agent 需要带时间的格式
  CURRENT_DATE=$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S')
  echo "[INFO] 📅 当前北京时间: $CURRENT_DATE"
  
  CONFIG_BACKUP="${CONFIG_FILE}.backup.$(date +%s)"
  cp "$CONFIG_FILE" "$CONFIG_BACKUP"
  
  if modify_json_end_date "$CONFIG_FILE" "$CURRENT_DATE"; then
    echo "[INFO] ✅ 已更新配置文件"
  else
    echo "[ERROR] 无法修改配置文件"
    mv "$CONFIG_BACKUP" "$CONFIG_FILE"
    exit 1
  fi
fi

# ============================================
# 构建/检查 Docker 镜像
# ============================================
build_docker_image() {
  echo ""
  echo "=========================================="
  echo "构建 Docker 镜像"
  echo "=========================================="
  
  cd "$PROJECT_ROOT"
  
  echo "[INFO] 构建镜像: $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" .
  
  if [ $? -ne 0 ]; then
    echo "[ERROR] 镜像构建失败"
    exit 1
  fi
  
  echo "[SUCCESS] 镜像构建完成: $IMAGE_NAME"
}

check_and_build_image() {
  # 检查镜像是否存在
  if ! docker images "$IMAGE_NAME" | grep -q "ai-trader" || [ "$FORCE_BUILD" = true ]; then
    echo "[INFO] 镜像不存在或强制构建，开始构建..."
    build_docker_image
  else
    echo "[INFO] ✅ 镜像已存在: $IMAGE_NAME"
  fi
}

# ============================================
# 从配置文件加载 Agent 列表
# ============================================
load_agents_from_config() {
  echo "[INFO] 从配置文件加载 Agent 列表..."
  
  local agents=$(parse_json_value "$CONFIG_FILE" "models[].signature")
  
  if [ -z "$agents" ]; then
    echo "[ERROR] 配置文件中未找到启用的 Agent"
    exit 1
  fi
  
  SIGNATURES=()
  while IFS= read -r sig; do
    SIGNATURES+=("$sig")
  done <<< "$agents"
  
  echo "[INFO] 找到 ${#SIGNATURES[@]} 个启用的 Agent:"
  for sig in "${SIGNATURES[@]}"; do
    echo "[INFO]   - $sig"
  done
  
  # 过滤指定 Agent
  if [ -n "$AGENT_FILTER" ]; then
    local found=false
    for sig in "${SIGNATURES[@]}"; do
      if [ "$sig" = "$AGENT_FILTER" ]; then
        found=true
        break
      fi
    done
    
    if [ "$found" = true ]; then
      SIGNATURES=("$AGENT_FILTER")
      echo "[INFO] 🎯 已过滤，只运行: $AGENT_FILTER"
    else
      echo "[ERROR] Agent '$AGENT_FILTER' 未在配置文件中找到"
      exit 1
    fi
  fi
}

# ============================================
# 运行数据准备容器
# ============================================
run_data_preparation() {
  echo ""
  echo "=========================================="
  echo "Step 1: 数据准备 (容器)"
  echo "=========================================="
  
  # 构建容器内配置文件路径
  local CONFIG_IN_CONTAINER="configs/${CONFIG_FILE##*/}"
  
  # 确定模式
  if [ -n "$INIT_DATE" ] && [ -n "$END_DATE" ]; then
    MODE="MANUAL"
    echo "[INFO] 模式: MANUAL (回测/手动同步)"
    echo "[INFO] 日期范围: $INIT_DATE ~ $END_DATE"
  else
    MODE="LIVE"
    echo "[INFO] 模式: LIVE (实时交易)"
  fi
  
  # 清理旧容器
  docker rm -f trader-data-prep-local 2>/dev/null || true
  
  # 构建环境变量参数
  local ENV_ARGS="-e CONFIG_FILE=$CONFIG_IN_CONTAINER -e DATE_SUFFIX=$DATE_SUFFIX"
  
  if [ "$MODE" == "MANUAL" ]; then
    ENV_ARGS="$ENV_ARGS -e START_DATE=$INIT_DATE -e END_DATE=$END_DATE"
  fi
  
  # 运行数据准备容器
  echo "[INFO] 启动数据准备容器..."
  docker run --rm \
    --name trader-data-prep-local \
    -v "$DATA_ROOT/configs:$CONTAINER_DATA_PATH/configs" \
    -v "$DATA_ROOT/data:$CONTAINER_DATA_PATH/data" \
    -v "$DATA_ROOT/logs:$CONTAINER_DATA_PATH/logs" \
    $ENV_ARGS \
    "$IMAGE_NAME" \
    bash scripts/data_preparation_entrypoint.sh
  
  if [ $? -ne 0 ]; then
    echo "[ERROR] 数据准备失败"
    exit 1
  fi
  
  echo "[SUCCESS] 数据准备完成！"
}

# ============================================
# 运行 Agent 任务容器
# ============================================
run_agent_tasks() {
  echo ""
  echo "=========================================="
  echo "Step 2: 运行 Trader Agent (容器)"
  echo "=========================================="
  
  # 加载 Agent 列表
  load_agents_from_config
  
  # 构建容器内配置文件路径
  local CONFIG_IN_CONTAINER="configs/${CONFIG_FILE##*/}"
  
  # 存储后台进程
  declare -a AGENT_PIDS=()
  
  # 并行启动所有 Agent 容器
  for SIGNATURE in "${SIGNATURES[@]}"; do
    echo "[INFO] 启动 Agent: $SIGNATURE"
    
    # 清理旧容器
    docker rm -f "trader-agent-$SIGNATURE" 2>/dev/null || true
    
    # 启动容器
    docker run --rm \
      --name "trader-agent-$SIGNATURE" \
      --network host \
      -v "$DATA_ROOT/configs:$CONTAINER_DATA_PATH/configs" \
      -v "$DATA_ROOT/data:$CONTAINER_DATA_PATH/data" \
      -v "$DATA_ROOT/logs:$CONTAINER_DATA_PATH/logs" \
      -v "$DATA_ROOT/docs:$CONTAINER_DATA_PATH/docs" \
      -v "$DATA_ROOT/.env:$CONTAINER_DATA_PATH/.env:ro" \
      -e DATE_SUFFIX="$DATE_SUFFIX" \
      "$IMAGE_NAME" \
      bash scripts/container_entrypoint.sh "$CONFIG_IN_CONTAINER" --signature "$SIGNATURE" &
    
    AGENT_PIDS+=("$!")
    echo "[INFO] ✅ $SIGNATURE 已启动 (PID: $!)"
  done
  
  echo ""
  echo "[INFO] 等待所有 Agent 完成..."
  
  # 等待所有进程完成
  local ALL_SUCCESS=true
  local SUCCESS_COUNT=0
  local FAILED_COUNT=0
  local idx=0
  
  for pid in "${AGENT_PIDS[@]}"; do
    SIGNATURE="${SIGNATURES[$idx]}"
    echo "[INFO] 等待 $SIGNATURE (PID: $pid)..."
    
    if wait "$pid"; then
      echo "[SUCCESS] ✓ $SIGNATURE 完成"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
      echo "[ERROR] ✗ $SIGNATURE 失败"
      FAILED_COUNT=$((FAILED_COUNT + 1))
      ALL_SUCCESS=false
    fi
    
    idx=$((idx + 1))
  done
  
  # 显示结果
  echo ""
  echo "=========================================="
  echo "执行摘要"
  echo "=========================================="
  echo "[INFO] 总任务数: ${#SIGNATURES[@]}"
  echo "[SUCCESS] 成功: $SUCCESS_COUNT"
  
  if [ $FAILED_COUNT -gt 0 ]; then
    echo "[ERROR] 失败: $FAILED_COUNT"
  fi
  
  if [ "$ALL_SUCCESS" = true ]; then
    echo ""
    echo "[SUCCESS] 🎉 所有 Agent 执行成功！"
    return 0
  else
    echo ""
    echo "[WARN] ⚠️ 部分 Agent 执行失败"
    return 1
  fi
}

# ============================================
# 清理函数
# ============================================
cleanup() {
  if [ -n "$CONFIG_BACKUP" ] && [ -f "$CONFIG_BACKUP" ]; then
    echo "[INFO] 🧹 清理配置文件备份"
    rm -f "$CONFIG_BACKUP"
  fi
}

trap cleanup EXIT

# ============================================
# 运行选股策略（容器化）
# ============================================
run_stock_selection() {
  echo ""
  echo "=========================================="
  echo "📊 选股策略执行 (容器)"
  echo "=========================================="
  
  # 检查并构建镜像
  check_and_build_image
  
  # 构建环境变量
  local ENV_ARGS=""
  
  if [ -n "$SELECTION_DATE" ]; then
    ENV_ARGS="$ENV_ARGS -e SELECTION_DATE=$SELECTION_DATE"
  fi
  
  # 确定更新模式
  if [ "$FULL_UPDATE" = true ]; then
    ENV_ARGS="$ENV_ARGS -e UPDATE_MODE=full"
  elif [ "$UPDATE_DATA" = true ]; then
    ENV_ARGS="$ENV_ARGS -e UPDATE_MODE=incremental"
  else
    ENV_ARGS="$ENV_ARGS -e UPDATE_MODE=none"
  fi
  
  echo "[INFO] 环境变量: $ENV_ARGS"
  
  # 清理旧容器
  docker rm -f trader-stock-selection 2>/dev/null || true
  
  # 运行选股容器
  # 代码打包在镜像中 scripts/stock_selection/
  # 数据目录通过 volume mount 挂载
  echo "[INFO] 启动选股容器..."
  
  docker run --rm \
    --name trader-stock-selection \
    -v "$DATA_ROOT/data/A_stock:/home/ec2-user/AI-Trader/data/A_stock" \
    $ENV_ARGS \
    "$IMAGE_NAME" \
    bash scripts/stock_selection_entrypoint.sh
  
  if [ $? -ne 0 ]; then
    echo "[ERROR] 选股策略执行失败"
    exit 1
  fi
  
  echo "[SUCCESS] 选股策略执行完成！"
}

# ============================================
# 主流程
# ============================================

# 选股模式
if [ "$STOCK_SELECTION" = true ]; then
  echo "[INFO] 📊 运行模式: 选股策略 (容器化)"
  run_stock_selection
  exit $?
fi

# 仅数据准备模式
if [ "$DATA_PREP_ONLY" = true ]; then
  echo "[INFO] 📦 运行模式: 仅数据准备"
  
  # 解析配置参数
  CONFIG_FILE="${ARGS[0]:-}"
  INIT_DATE="${ARGS[1]:-}"
  END_DATE="${ARGS[2]:-}"
  
  if [ -z "$CONFIG_FILE" ]; then
    echo "[ERROR] 数据准备模式需要指定配置文件"
    exit 1
  fi
  
  # 智能路径解析
  if [[ "$CONFIG_FILE" != /* ]]; then
    if [ -f "$DATA_ROOT/$CONFIG_FILE" ]; then
      CONFIG_FILE="$DATA_ROOT/$CONFIG_FILE"
    elif [ -f "$DATA_ROOT/configs/${CONFIG_FILE##*/}" ]; then
      CONFIG_FILE="$DATA_ROOT/configs/${CONFIG_FILE##*/}"
    elif [ -f "$PROJECT_ROOT/$CONFIG_FILE" ]; then
      CONFIG_FILE="$PROJECT_ROOT/$CONFIG_FILE"
    fi
  fi
  
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "[ERROR] 配置文件不存在: $CONFIG_FILE"
    exit 1
  fi
  
  echo "[INFO] 📄 配置文件: $CONFIG_FILE"
  
  # 从配置文件名提取日期后缀
  if [[ $CONFIG_FILE =~ _([0-9]{8})\.json$ ]]; then
    DATE_SUFFIX="${BASH_REMATCH[1]}"
    echo "[INFO] 📅 日期后缀: $DATE_SUFFIX"
  fi
  
  check_and_build_image
  run_data_preparation
  
  echo ""
  echo "=========================================="
  echo "✅ 数据准备完成！"
  echo "=========================================="
  exit 0
fi

# 正常模式：数据准备 + Agent 执行

# 检查并构建镜像
check_and_build_image

# Step 1: 数据准备
if [ "$SKIP_DATA_PREP" = true ]; then
  echo ""
  echo "=========================================="
  echo "Step 1: 跳过数据准备 (--skip-data-prep)"
  echo "=========================================="
else
  run_data_preparation
fi

# Step 2: 运行 Agent
if run_agent_tasks; then
  echo ""
  echo "=========================================="
  echo "✅ 所有任务执行完成！"
  echo "=========================================="
  exit 0
else
  echo ""
  echo "=========================================="
  echo "❌ 部分任务执行失败"
  echo "=========================================="
  exit 1
fi
