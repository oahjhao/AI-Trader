#!/bin/bash
# 验证 .env 配置是否正确加载
# 用法: source .env && ./verify_env.sh

echo "=========================================="
echo ".env 配置验证"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_var() {
  local var_name="$1"
  local var_value="${!var_name}"
  local expected_pattern="$2"
  
  echo -n "检查 $var_name ... "
  
  if [ -z "$var_value" ]; then
    echo -e "${RED}✗ 未设置${NC}"
    return 1
  elif [ -n "$expected_pattern" ] && [[ ! "$var_value" =~ $expected_pattern ]]; then
    echo -e "${YELLOW}⚠️  值可能不正确: $var_value${NC}"
    return 1
  else
    echo -e "${GREEN}✓ $var_value${NC}"
    return 0
  fi
}

echo "=== AWS ECS 配置 ==="
check_var "AWS_REGION" "^us-"
check_var "ECS_CLUSTER" "trader-cluster"
check_var "ECS_SUBNET" "^subnet-"
check_var "ECS_SECURITY_GROUP" "^sg-"
check_var "DATA_PREP_TASK_DEF" "trader-data-preparation"
check_var "AGENT_TASK_DEF" "trader-agent"

echo ""
echo "=== API Keys ==="
check_var "OPENAI_API_BASE"
check_var "OPENAI_API_KEY" "^sk-"
check_var "ALPHAADVANTAGE_API_KEY"
check_var "JINA_API_KEY" "^jina_"
check_var "TUSHARE_TOKEN"

echo ""
echo "=== Agent 配置 ==="
check_var "AGENT_MAX_STEP" "^[0-9]+$"
check_var "RUNTIME_ENV_PATH"

echo ""
echo "=== 钉钉配置 ==="
check_var "DINGTALK_WEBHOOK_URL" "^https://oapi.dingtalk.com"
check_var "DINGTALK_SECRET"

echo ""
echo "=========================================="
echo "验证完成"
echo "=========================================="

# 测试 AWS 连接
echo ""
echo "测试 AWS 连接..."
if aws sts get-caller-identity --region "$AWS_REGION" &> /dev/null; then
  echo -e "${GREEN}✓ AWS 认证成功${NC}"
  aws sts get-caller-identity --region "$AWS_REGION" --query 'Account' --output text
else
  echo -e "${RED}✗ AWS 认证失败${NC}"
fi

# 测试 ECS 集群
echo ""
echo "测试 ECS 集群连接..."
if aws ecs describe-clusters --clusters "$ECS_CLUSTER" --region "$AWS_REGION" &> /dev/null; then
  echo -e "${GREEN}✓ ECS 集群 '$ECS_CLUSTER' 可访问${NC}"
else
  echo -e "${RED}✗ ECS 集群 '$ECS_CLUSTER' 不可访问${NC}"
fi
