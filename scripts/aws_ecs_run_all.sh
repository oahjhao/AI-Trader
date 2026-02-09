#!/bin/bash
# AWS ECS Run All - 按照 docker-compose 逻辑顺序执行 ECS 任务
# 用法: ./aws_ecs_run_all.sh [CONFIG_FILE] [INIT_DATE] [END_DATE] [--local] [--agent SIGNATURE] [--skip-data-prep]
# 示例: 
#   ECS 模式: ./aws_ecs_run_all.sh configs/astock_config_hourly.json 2025-01-01 2025-01-21
#   本地测试: ./aws_ecs_run_all.sh configs/astock_config_daily_20250815.json 2025-08-15 2025-08-22 --local
#   只运行某个 Agent: ./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json --local --agent DS_pick_monk_260202
#   跳过数据准备: ./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json --local --agent DS_pick_monk_260202 --skip-data-prep

set -e

# ============================================
# 解析命令行选项
# ============================================
RUN_MODE="ecs"  # 默认 ECS 模式
AGENT_FILTER=""  # 指定运行的 Agent（为空则运行全部）
SKIP_DATA_PREP=false  # 是否跳过数据准备

# 解析 --local、--agent、--skip-data-prep 选项
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)
      RUN_MODE="local"
      shift
      ;;
    --agent)
      AGENT_FILTER="$2"
      shift 2
      ;;
    --skip-data-prep)
      SKIP_DATA_PREP=true
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [ "$RUN_MODE" = "local" ]; then
  echo "[INFO] 💻 运行模式: 本地 Docker 容器测试"
else
  echo "[INFO] ☁️  运行模式: AWS ECS"
fi
if [ -n "$AGENT_FILTER" ]; then
  echo "[INFO] 🎯 指定运行 Agent: $AGENT_FILTER"
fi
if [ "$SKIP_DATA_PREP" = true ]; then
  echo "[INFO] ⏭️  跳过数据准备"
fi

# ============================================
# 加载 .env 环境变量
# ============================================
load_env_file() {
  local env_files=("/.env" "./.env" "/home/ec2-user/AI-Trader/.env")
  
  for env_file in "${env_files[@]}"; do
    if [ -f "$env_file" ]; then
      echo "[INFO] 加载环境变量文件: $env_file"
      # 使用 export 导出所有变量，忽略注释和空行
      set -a
      source "$env_file"
      set +a
      return 0
    fi
  done
  
  echo "[WARN] 未找到 .env 文件，使用系统环境变量"
}

# 优先加载 .env 文件
load_env_file

# ============================================
# 配置参数 - 请根据实际环境修改
# ============================================
CLUSTER="${ECS_CLUSTER:-trader-cluster}"
SUBNET="${ECS_SUBNET:-subnet-0307b527137ee17d9}"
SECURITY_GROUP="${ECS_SECURITY_GROUP:-sg-097cc7fbe296ee446}"
REGION="${AWS_REGION:-us-west-2}"

# 任务定义名称（支持环境变量覆盖）
DATA_PREP_TASK_DEF="${DATA_PREP_TASK_DEF:-trader-data-prep}"
AGENT_TASK_DEF="${AGENT_TASK_DEF:-trader-agent}"

# 容器名称（必须与任务定义中的containerDefinitions[].name一致）
DATA_PREP_CONTAINER_NAME="trader-data-prep"
AGENT_CONTAINER_NAME="trader-agent"

# 配置文件和日期参数
# 根据 ECS 任务定义，配置文件挂载在 /mnt/efs/configs
CONFIG_FILE=${ARGS[0]:-"configs/astock_config_hourly.json"}

# 智能路径解析：支持多种输入格式
if [ ! -f "$CONFIG_FILE" ]; then
  # 尝试 1: /mnt/efs/configs/ 前缀（ECS 挂载点）
  if [ -f "/mnt/efs/configs/$CONFIG_FILE" ]; then
    CONFIG_FILE="/mnt/efs/configs/$CONFIG_FILE"
  # 尝试 2: /mnt/efs/ 前缀
  elif [ -f "/mnt/efs/$CONFIG_FILE" ]; then
    CONFIG_FILE="/mnt/efs/$CONFIG_FILE"
  # 尝试 3: 去掉 configs/ 前缀后再试
  elif [ -f "/mnt/efs/configs/${CONFIG_FILE#configs/}" ]; then
    CONFIG_FILE="/mnt/efs/configs/${CONFIG_FILE#configs/}"
  fi
fi

INIT_DATE=${ARGS[1]:-""}
END_DATE=${ARGS[2]:-""}

# 自动检测 backtest 模式：如果未提供日期参数，从配置文件读取
# 当配置文件的 end_date 在过去时，自动使用配置中的日期（BACKTEST 模式）
if [ -z "$INIT_DATE" ] && [ -z "$END_DATE" ]; then
  # 尝试多个路径读取配置文件
  _cfg_path="$CONFIG_FILE"
  if [ ! -f "$_cfg_path" ]; then
    _cfg_path="/mnt/efs/ai-trader/$CONFIG_FILE"
  fi
  
  if [ -f "$_cfg_path" ] && command -v jq &> /dev/null; then
    _cfg_init=$(jq -r '.date_range.init_date // empty' "$_cfg_path" 2>/dev/null)
    _cfg_end=$(jq -r '.date_range.end_date // empty' "$_cfg_path" 2>/dev/null)
    
    if [ -n "$_cfg_init" ] && [ -n "$_cfg_end" ]; then
      # 提取日期部分（去掉可能的时间后缀）用于比较
      _end_date_only=$(echo "$_cfg_end" | cut -d' ' -f1)
      _today=$(date +%Y-%m-%d)
      
      if [[ "$_end_date_only" < "$_today" ]]; then
        INIT_DATE="$_cfg_init"
        END_DATE="$_cfg_end"
        echo "[INFO] 📅 自动检测到回测模式 (end_date=$_cfg_end 在过去)"
        echo "[INFO] 📅 使用配置文件日期: $INIT_DATE ~ $END_DATE"
      fi
    fi
  fi
fi

# Agent Signature 列表将从配置文件动态读取
SIGNATURES=()

# 脚本执行日志路径（EFS 持久化）
LOG_DIR="/mnt/efs/logs/scheduler"
LOG_FILE="$LOG_DIR/aws_ecs_run_$(date +%Y%m%d_%H%M%S).log"

# 创建日志目录
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ============================================
# 颜色输出（同时记录到日志文件）
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_message() {
  local level="$1"
  local message="$2"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  # 记录到文件（无颜色）
  echo "[$timestamp] [$level] $message" >> "$LOG_FILE" 2>/dev/null || true
}

echo_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
  log_message "INFO" "$1"
}

echo_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
  log_message "SUCCESS" "$1"
}

echo_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
  log_message "WARN" "$1"
}

echo_error() {
  echo -e "${RED}[ERROR]${NC} $1"
  log_message "ERROR" "$1"
}

# ============================================
# 检查必要的环境配置
# ============================================
check_prerequisites() {
  echo_info "检查前置条件..."
  
  # 检查 AWS CLI
  if ! command -v aws &> /dev/null; then
    echo_error "AWS CLI 未安装，请先安装 AWS CLI"
    exit 1
  fi
  
  # 检查 jq（用于解析 JSON 配置）
  if ! command -v jq &> /dev/null; then
    echo_error "jq 未安装，请先安装 jq (yum install jq 或 apt-get install jq)"
    exit 1
  fi
  
  # 检查配置文件是否存在
  if [ ! -f "$CONFIG_FILE" ]; then
    echo_error "配置文件不存在: $CONFIG_FILE"
    exit 1
  fi
  
  # 检查 AWS 认证
  if ! aws sts get-caller-identity &> /dev/null; then
    echo_error "AWS 认证失败，请配置 AWS 凭证"
    exit 1
  fi
  
  # 检查 ECS 集群是否存在
  if ! aws ecs describe-clusters --clusters "$CLUSTER" --region "$REGION" &> /dev/null; then
    echo_error "ECS 集群 '$CLUSTER' 不存在"
    exit 1
  fi
  
  echo_success "前置条件检查通过"
}

# ============================================
# 从配置文件加载 Agent 列表
# ============================================
load_agents_from_config() {
  echo_info "从配置文件加载 Agent 列表..."
  
  # 在宿主机上读取配置时，优先使用 EFS 路径
  local config_path="$CONFIG_FILE"
  if [ ! -f "$config_path" ] && [ -f "/mnt/efs/ai-trader/$CONFIG_FILE" ]; then
    config_path="/mnt/efs/ai-trader/$CONFIG_FILE"
    echo_info "  从 EFS 读取配置: $config_path"
  fi
  
  # 读取配置文件中所有 enabled=true 的 models
  local agents=$(jq -r '.models[] | select(.enabled == true) | .signature' "$config_path" 2>/dev/null)
  
  if [ -z "$agents" ]; then
    echo_error "配置文件中未找到启用的 Agent (enabled=true)"
    exit 1
  fi
  
  # 转换为数组
  while IFS= read -r sig; do
    SIGNATURES+=("$sig")
  done <<< "$agents"
  
  echo_success "找到 ${#SIGNATURES[@]} 个启用的 Agent:"
  for sig in "${SIGNATURES[@]}"; do
    echo_info "  - $sig"
  done
  
  # 如果指定了 --agent，过滤只保留指定的 Agent
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
      echo_info "🎯 已过滤，只运行: $AGENT_FILTER"
    else
      echo_error "Agent '$AGENT_FILTER' 未在配置文件中找到或未启用"
      echo_info "可用的 Agent:"
      for sig in "${SIGNATURES[@]}"; do
        echo_info "  - $sig"
      done
      exit 1
    fi
  fi
}

# ============================================
# 运行数据准备任务
# ============================================
run_data_preparation() {
  echo ""
  echo_info "=========================================="
  echo_info "Step 1: 运行数据准备任务"
  echo_info "=========================================="
  echo_info "配置文件: $CONFIG_FILE"
  echo_info "任务定义: $DATA_PREP_TASK_DEF"
  
  # 构建环境变量覆盖（data-prep使用entryPoint，通过环境变量传递日期）
  local ENV_OVERRIDES="[]"
  
  # 提取配置文件的相对路径（去掉 /mnt/efs/ 前缀）
  local DATA_PREP_CONFIG_FILE="${CONFIG_FILE#/mnt/efs/}"
  # 如果配置文件没有 configs/ 前缀，添加它
  if [[ "$DATA_PREP_CONFIG_FILE" != configs/* ]]; then
    DATA_PREP_CONFIG_FILE="configs/${DATA_PREP_CONFIG_FILE##*/}"
  fi
  
  if [ -n "$INIT_DATE" ] && [ -n "$END_DATE" ]; then
    echo_info "运行模式: MANUAL (回测/手动同步)"
    echo_info "日期范围: $INIT_DATE 到 $END_DATE"
    ENV_OVERRIDES="[{\"name\":\"CONFIG_FILE\",\"value\":\"$DATA_PREP_CONFIG_FILE\"},{\"name\":\"START_DATE\",\"value\":\"$INIT_DATE\"},{\"name\":\"END_DATE\",\"value\":\"$END_DATE\"}]"
  else
    echo_info "运行模式: LIVE (实时交易)"
    echo_info "将自动获取历史数据"
    ENV_OVERRIDES="[{\"name\":\"CONFIG_FILE\",\"value\":\"$DATA_PREP_CONFIG_FILE\"}]"
  fi
  
  # 运行任务
  local TASK_ARN=$(aws ecs run-task \
    --cluster "$CLUSTER" \
    --task-definition "$DATA_PREP_TASK_DEF" \
    --launch-type FARGATE \
    --region "$REGION" \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
    --overrides "{\"containerOverrides\":[{\"name\":\"$DATA_PREP_CONTAINER_NAME\",\"environment\":$ENV_OVERRIDES}]}" \
    --query 'tasks[0].taskArn' \
    --output text)
  
  if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
    echo_error "数据准备任务启动失败"
    exit 1
  fi
  
  echo_success "数据准备任务已启动"
  echo_info "Task ARN: $TASK_ARN"
  echo_info "等待数据准备完成..."
  
  # 等待任务完成
  aws ecs wait tasks-stopped \
    --cluster "$CLUSTER" \
    --tasks "$TASK_ARN" \
    --region "$REGION"
  
  # 检查任务退出码
  local EXIT_CODE=$(aws ecs describe-tasks \
    --cluster "$CLUSTER" \
    --tasks "$TASK_ARN" \
    --region "$REGION" \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)
  
  if [ "$EXIT_CODE" != "0" ]; then
    echo_error "数据准备任务失败，退出码: $EXIT_CODE"
    echo_error "请检查 CloudWatch 日志: /ecs/$DATA_PREP_TASK_DEF"
    exit 1
  fi
  
  echo_success "数据准备任务完成！"
}

# ============================================
# 并行运行所有 Agent 任务
# ============================================
run_agent_tasks() {
  echo ""
  echo_info "=========================================="
  echo_info "Step 2: 启动所有 Agent 策略"
  echo_info "=========================================="
  echo_info "任务定义: $AGENT_TASK_DEF"
  echo_info "将并行运行 ${#SIGNATURES[@]} 个策略"
  
  local TASK_ARNS=()
  
  # 并行启动所有 Agent
  for SIGNATURE in "${SIGNATURES[@]}"; do
    echo_info "启动 Agent: $SIGNATURE"
    
    # 提取配置文件的相对路径（去掉 /mnt/efs/ 前缀）
    local AGENT_CONFIG_FILE="${CONFIG_FILE#/mnt/efs/}"
    # 如果配置文件没有 configs/ 前缀，添加它
    if [[ "$AGENT_CONFIG_FILE" != configs/* ]]; then
      AGENT_CONFIG_FILE="configs/${AGENT_CONFIG_FILE##*/}"
    fi
    
    echo_info "  配置文件: $AGENT_CONFIG_FILE"
    
    local TASK_ARN=$(aws ecs run-task \
      --cluster "$CLUSTER" \
      --task-definition "$AGENT_TASK_DEF" \
      --launch-type FARGATE \
      --region "$REGION" \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
      --overrides "{\"containerOverrides\":[{\"name\":\"$AGENT_CONTAINER_NAME\",\"command\":[\"$AGENT_CONFIG_FILE\",\"--signature\",\"$SIGNATURE\"]}]}" \
      --query 'tasks[0].taskArn' \
      --output text)
    
    if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
      echo_error "Agent $SIGNATURE 启动失败"
      continue
    fi
    
    TASK_ARNS+=("$SIGNATURE:$TASK_ARN")
    echo_success "Agent $SIGNATURE 已启动"
    echo_info "  Task ARN: $TASK_ARN"
  done
  
  if [ ${#TASK_ARNS[@]} -eq 0 ]; then
    echo_error "没有 Agent 成功启动"
    exit 1
  fi
  
  echo ""
  echo_info "等待所有 Agent 完成..."
  echo_info "已启动 ${#TASK_ARNS[@]} 个任务，请耐心等待..."
  
  # 等待所有任务完成
  for TASK_INFO in "${TASK_ARNS[@]}"; do
    local SIGNATURE="${TASK_INFO%%:*}"
    local TASK_ARN="${TASK_INFO#*:}"
    
    echo_info "等待 $SIGNATURE 完成..."
    aws ecs wait tasks-stopped \
      --cluster "$CLUSTER" \
      --tasks "$TASK_ARN" \
      --region "$REGION"
  done
  
  echo_success "所有 Agent 任务已完成"
  
  # ============================================
  # 检查所有任务结果
  # ============================================
  echo ""
  echo_info "=========================================="
  echo_info "检查 Agent 任务结果"
  echo_info "=========================================="
  
  local ALL_SUCCESS=true
  local SUCCESS_COUNT=0
  local FAILED_COUNT=0
  
  for TASK_INFO in "${TASK_ARNS[@]}"; do
    local SIGNATURE="${TASK_INFO%%:*}"
    local TASK_ARN="${TASK_INFO#*:}"
    
    local EXIT_CODE=$(aws ecs describe-tasks \
      --cluster "$CLUSTER" \
      --tasks "$TASK_ARN" \
      --region "$REGION" \
      --query 'tasks[0].containers[0].exitCode' \
      --output text)
    
    if [ "$EXIT_CODE" = "0" ]; then
      echo_success "✓ $SIGNATURE - 成功完成"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
      echo_error "✗ $SIGNATURE - 失败 (退出码: $EXIT_CODE)"
      echo_error "  查看日志: aws logs tail /ecs/$AGENT_TASK_DEF --follow --filter-pattern \"$SIGNATURE\""
      FAILED_COUNT=$((FAILED_COUNT + 1))
      ALL_SUCCESS=false
    fi
  done
  
  echo ""
  echo_info "=========================================="
  echo_info "执行摘要"
  echo_info "=========================================="
  echo_info "总任务数: ${#TASK_ARNS[@]}"
  echo_success "成功: $SUCCESS_COUNT"
  
  if [ $FAILED_COUNT -gt 0 ]; then
    echo_error "失败: $FAILED_COUNT"
  fi
  
  if [ "$ALL_SUCCESS" = true ]; then
    echo ""
    echo_success "🎉 所有交易 Agent 执行成功！"
    return 0
  else
    echo ""
    echo_warn "⚠️  部分 Agent 执行失败，请检查 CloudWatch 日志"
    return 1
  fi
}

# ============================================
# 显示使用帮助
# ============================================
show_usage() {
  cat << EOF
用法: $0 [CONFIG_FILE] [INIT_DATE] [END_DATE] [--local] [--agent SIGNATURE] [--skip-data-prep]

参数:
  CONFIG_FILE  配置文件路径（默认: configs/astock_config_hourly.json）
  INIT_DATE    起始日期 YYYY-MM-DD（可选，用于回测）
  END_DATE     结束日期 YYYY-MM-DD（可选，用于回测）

选项:
  --local              本地 Docker 容器测试模式
  --agent SIGNATURE    只运行指定的 Agent（默认运行所有 enabled=true 的 Agent）
  --skip-data-prep     跳过数据准备步骤（数据已就绪时使用）

示例:
  # 实时交易模式（LIVE）
  $0
  $0 configs/astock_config_hourly.json

  # 回测模式（MANUAL）
  $0 configs/astock_config_hourly.json 2025-01-01 2025-01-21

  # 本地只运行指定 Agent
  $0 configs/astock_config_hourly_260202.json --local --agent DS_pick_monk_260202

  # 跳过数据准备，只运行指定 Agent
  $0 configs/astock_config_hourly_260202.json --local --agent DS_pick_monk_260202 --skip-data-prep

环境变量:
  ECS_CLUSTER            ECS 集群名称（默认: trader-cluster）
  ECS_SUBNET             子网 ID（默认: subnet-0307b527137ee17d9）
  ECS_SECURITY_GROUP     安全组 ID（默认: sg-097cc7fbe296ee446）
  AWS_REGION             AWS 区域（默认: us-west-2）
  DATA_PREP_TASK_DEF     数据准备任务定义（默认: trader-data-prep）
  AGENT_TASK_DEF         Agent 任务定义（默认: trader-agent）

注意:
  1. 请确保已配置 AWS 凭证（AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY）
  2. 需要安装 jq 工具用于解析配置文件（yum install jq）
  3. 安全组需要允许访问 EFS (端口 2049) 和 Internet
  4. 子网需要有 NAT 网关或公网访问能力
  5. 数据准备任务完成后才会启动 Agent 任务
  6. 所有 Agent 并行执行，互不干扰
  7. Agent 列表从配置文件中自动读取（enabled=true）
  8. 任务定义需要提前创建（trader-data-preparation 和 trader-agent）

EOF
}

# ============================================
# 本地 Docker 容器测试模式
# ============================================
run_local_docker_test() {
  echo_info "=========================================" 
  echo_info "💻 本地 Docker 容器测试模式"
  echo_info "=========================================="
  echo_info "配置文件: $CONFIG_FILE"
  echo_info "日期范围: $INIT_DATE ~ $END_DATE"
  echo_info "镜像: ai-trader:latest"
  echo ""
  
  # 提取日期后缀（用于数据隔离）
  local DATE_SUFFIX=""
  if [[ $CONFIG_FILE =~ _([0-9]{8})\.json$ ]]; then
    DATE_SUFFIX="${BASH_REMATCH[1]}"
    echo_info "📅 检测到日期后缀: $DATE_SUFFIX"
  else
    # 从 init_date 提取
    DATE_SUFFIX=$(echo "$INIT_DATE" | tr -d '- :'| cut -c1-8)
    echo_info "📅 从 init_date 生成日期后缀: $DATE_SUFFIX"
  fi
  
  # 检查 Docker 镜像
  if ! sudo docker images ai-trader:latest | grep -q "ai-trader"; then
    echo_error "Docker 镜像 ai-trader:latest 不存在，请先构建镜像"
    echo_info "执行: cd /home/ec2-user/AI-Trader && sudo docker build -t ai-trader:latest -f Dockerfile ."
    exit 1
  fi
  
  # 清理旧容器
  echo_info "🧹 清理旧容器..."
  sudo docker rm -f trader-data-prep-local 2>/dev/null || true
  sudo docker ps -a | grep "trader-agent-" | awk '{print $1}' | xargs -r sudo docker rm -f 2>/dev/null || true
  
  # Step 1: 运行数据准备（在容器内执行）
  if [ "$SKIP_DATA_PREP" = true ]; then
    echo ""
    echo_info "========================================="
    echo_info "Step 1: 跳过数据准备 (--skip-data-prep)"
    echo_info "=========================================="
  else
    echo ""
    echo_info "========================================="
    echo_info "Step 1: 运行数据准备"
    echo_info "=========================================="
      
    # 挂载 EFS，但保留镜像中的脚本
    # EFS 的 configs、data、logs、docs 会覆盖镜像中的对应目录
    sudo docker run --rm \
      --name trader-data-prep-local \
      -v /mnt/efs/ai-trader/configs:/home/ec2-user/AI-Trader/configs \
      -v /mnt/efs/ai-trader/data:/home/ec2-user/AI-Trader/data \
      -v /mnt/efs/ai-trader/logs:/home/ec2-user/AI-Trader/logs \
      -v /mnt/efs/ai-trader/docs:/home/ec2-user/AI-Trader/docs \
      -w /home/ec2-user/AI-Trader \
      -e DATE_SUFFIX="$DATE_SUFFIX" \
      ai-trader:latest \
      bash scripts/data_preparation_entrypoint.sh \
        "configs/${CONFIG_FILE##*/}" "$INIT_DATE" "$END_DATE"
      
    if [ $? -ne 0 ]; then
      echo_error "数据准备失败"
      exit 1
    fi
        
    echo_success "数据准备完成！"
  fi
    
  # Step 2: 运行 Trader Agent（容器内自动启动 MCP 服务）
  echo ""
  echo_info "=========================================" 
  echo_info "Step 2: 运行 Trader Agent（并行模式）"
  echo_info "=========================================="
  echo_info "注意：MCP 服务会在容器内自动启动"
  
  # 从配置文件加载 Agent 列表
  load_agents_from_config
  
  echo_info "开始并行启动 ${#SIGNATURES[@]} 个 Agent..."
  
  # 存储后台进程 PID
  declare -a AGENT_PIDS=()
  
  # 并行启动所有 Agent
  for SIGNATURE in "${SIGNATURES[@]}"; do
    echo_info "启动 Agent: $SIGNATURE (后台运行)"
    
    # 挂载 EFS 的数据目录，保留镜像中的代码
    sudo docker run --rm \
      --name "trader-agent-$SIGNATURE" \
      --network host \
      -v /mnt/efs/ai-trader/configs:/home/ec2-user/AI-Trader/configs \
      -v /mnt/efs/ai-trader/data:/home/ec2-user/AI-Trader/data \
      -v /mnt/efs/ai-trader/logs:/home/ec2-user/AI-Trader/logs \
      -v /mnt/efs/ai-trader/docs:/home/ec2-user/AI-Trader/docs \
      -w /home/ec2-user/AI-Trader \
      -e DATE_SUFFIX="$DATE_SUFFIX" \
      ai-trader:latest \
      bash scripts/container_entrypoint.sh "configs/${CONFIG_FILE##*/}" --signature "$SIGNATURE" &
    
    # 记录 PID
    AGENT_PIDS+=("$!")
    echo_info "✅ $SIGNATURE 已启动 (PID: $!)"
  done
  
  echo ""
  echo_info "等待所有 Agent 完成..."
  
  # 等待所有后台进程完成，并记录结果
  local ALL_SUCCESS=true
  local SUCCESS_COUNT=0
  local FAILED_COUNT=0
  local idx=0
  
  for pid in "${AGENT_PIDS[@]}"; do
    SIGNATURE="${SIGNATURES[$idx]}"
    echo_info "等待 $SIGNATURE (PID: $pid) 完成..."
    
    if wait "$pid"; then
      echo_success "✓ $SIGNATURE - 成功完成"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
      echo_error "✗ $SIGNATURE - 失败"
      FAILED_COUNT=$((FAILED_COUNT + 1))
      ALL_SUCCESS=false
    fi
    
    idx=$((idx + 1))
  done
  
  # 显示结果
  echo ""
  echo_info "=========================================="
  echo_info "执行摘要"
  echo_info "=========================================="
  echo_info "总任务数: ${#SIGNATURES[@]}"
  echo_success "成功: $SUCCESS_COUNT"
  
  if [ $FAILED_COUNT -gt 0 ]; then
    echo_error "失败: $FAILED_COUNT"
  fi
  
  if [ "$ALL_SUCCESS" = true ]; then
    echo ""
    echo_success "🎉 所有交易 Agent 执行成功！"
    return 0
  else
    echo ""
    echo_warn "⚠️  部分 Agent 执行失败，请检查日志"
    return 1
  fi
}

# ============================================
# 主函数
# ============================================
main() {
  # 显示帮助
  if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage
    exit 0
  fi
  
  # 本地测试模式
  if [ "$RUN_MODE" = "local" ]; then
    echo_info "=========================================="
    echo_info "💻 AI-Trader 本地容器测试"
    echo_info "=========================================="
    echo_info "配置文件: $CONFIG_FILE"
    if [ -n "$INIT_DATE" ] && [ -n "$END_DATE" ]; then
      echo_info "日期范围: $INIT_DATE ~ $END_DATE (BACKTEST)"
    else
      echo_info "模式: LIVE (实时交易)"
    fi
    echo ""
    
    # 检查配置文件
    if [ ! -f "$CONFIG_FILE" ] && [ ! -f "/mnt/efs/ai-trader/$CONFIG_FILE" ]; then
      echo_error "配置文件不存在: $CONFIG_FILE"
      exit 1
    fi
    
    # 执行本地测试
    if run_local_docker_test; then
      exit 0
    else
      exit 1
    fi
  fi
  
  # ECS 模式
  echo_info "=========================================="
  echo_info "AWS ECS AI-Trader 批量执行脚本"
  echo_info "=========================================="
  echo_info "集群: $CLUSTER"
  echo_info "区域: $REGION"
  echo_info "子网: $SUBNET"
  echo_info "安全组: $SECURITY_GROUP"
  echo_info "数据准备任务: $DATA_PREP_TASK_DEF"
  echo_info "Agent 任务: $AGENT_TASK_DEF"
  echo_info "执行日志: $LOG_FILE"
  echo ""
  
  # 检查前置条件
  check_prerequisites
  
  # 从配置文件加载 Agent 列表
  load_agents_from_config
  
  # 运行数据准备
  run_data_preparation
  
  # 运行 Agent 任务
  if run_agent_tasks; then
    echo ""
    echo_success "=========================================="
    echo_success "所有任务执行完成！"
    echo_success "=========================================="
    exit 0
  else
    echo ""
    echo_error "=========================================="
    echo_error "部分任务执行失败"
    echo_error "=========================================="
    exit 1
  fi
}

# 执行主函数
main "$@"
