#!/bin/bash
# AWS ECS Run All - 按照 docker-compose 逻辑顺序执行 ECS 任务
# 用法: ./aws_ecs_run_all.sh [CONFIG_FILE] [INIT_DATE] [END_DATE]
# 示例: ./aws_ecs_run_all.sh configs/astock_config_hourly.json 2025-01-01 2025-01-21

set -e

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
SUBNET="${ECS_SUBNET:-subnet-xxx}"
SECURITY_GROUP="${ECS_SECURITY_GROUP:-sg-xxx}"
REGION="${AWS_REGION:-us-east-1}"

# 任务定义名称（支持环境变量覆盖）
DATA_PREP_TASK_DEF="${DATA_PREP_TASK_DEF:-trader-data-prep}"
AGENT_TASK_DEF="${AGENT_TASK_DEF:-trader-agent}"

# 配置文件和日期参数
# 根据 ECS 任务定义，配置文件挂载在 /mnt/efs/configs
CONFIG_FILE=${1:-"configs/astock_config_hourly.json"}

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

INIT_DATE=${2:-""}
END_DATE=${3:-""}

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
  
  # 读取配置文件中所有 enabled=true 的 models
  local agents=$(jq -r '.models[] | select(.enabled == true) | .signature' "$CONFIG_FILE" 2>/dev/null)
  
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
  
  # 构建 command 参数
  local COMMAND_JSON="[\"$CONFIG_FILE\"]"
  
  if [ -n "$INIT_DATE" ] && [ -n "$END_DATE" ]; then
    echo_info "运行模式: MANUAL (回测/手动同步)"
    echo_info "日期范围: $INIT_DATE 到 $END_DATE"
    COMMAND_JSON="[\"$CONFIG_FILE\",\"$INIT_DATE\",\"$END_DATE\"]"
  else
    echo_info "运行模式: LIVE (实时交易)"
    echo_info "将自动获取历史数据"
  fi
  
  # 运行任务
  local TASK_ARN=$(aws ecs run-task \
    --cluster "$CLUSTER" \
    --task-definition "$DATA_PREP_TASK_DEF" \
    --launch-type FARGATE \
    --region "$REGION" \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
    --overrides "{\"containerOverrides\":[{\"name\":\"data-prep\",\"command\":$COMMAND_JSON}]}" \
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
    
    local TASK_ARN=$(aws ecs run-task \
      --cluster "$CLUSTER" \
      --task-definition "$AGENT_TASK_DEF" \
      --launch-type FARGATE \
      --region "$REGION" \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
      --overrides "{\"containerOverrides\":[{\"name\":\"agent\",\"command\":[\"$CONFIG_FILE\",\"--signature\",\"$SIGNATURE\"]}]}" \
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
用法: $0 [CONFIG_FILE] [INIT_DATE] [END_DATE]

参数:
  CONFIG_FILE  配置文件路径（默认: configs/astock_config_hourly.json）
  INIT_DATE    起始日期 YYYY-MM-DD（可选，用于回测）
  END_DATE     结束日期 YYYY-MM-DD（可选，用于回测）

示例:
  # 实时交易模式（LIVE）
  $0
  $0 configs/astock_config_hourly.json

  # 回测模式（MANUAL）
  $0 configs/astock_config_hourly.json 2025-01-01 2025-01-21

环境变量:
  ECS_CLUSTER            ECS 集群名称（默认: trader-cluster）
  ECS_SUBNET             子网 ID（默认: subnet-xxx）
  ECS_SECURITY_GROUP     安全组 ID（默认: sg-xxx）
  AWS_REGION             AWS 区域（默认: us-east-1）
  DATA_PREP_TASK_DEF     数据准备任务定义（默认: trader-data-preparation）
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
# 主函数
# ============================================
main() {
  # 显示帮助
  if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage
    exit 0
  fi
  
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
