#!/bin/bash
# EFS 挂载点测试脚本 - 用于验证 frontend 容器中的挂载配置
# 用法: docker exec trader-frontend /bin/sh /scripts/test_efs_mounts.sh

set -e

echo "=========================================="
echo "EFS 挂载点测试"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

test_mount() {
  local path="$1"
  local description="$2"
  
  echo -n "测试: $description ... "
  if [ -d "$path" ]; then
    echo -e "${GREEN}✓ 存在${NC}"
    ls -lh "$path" | head -5
    echo ""
    return 0
  else
    echo -e "${RED}✗ 不存在${NC}"
    return 1
  fi
}

test_file() {
  local path="$1"
  local description="$2"
  
  echo -n "测试: $description ... "
  if [ -f "$path" ]; then
    echo -e "${GREEN}✓ 存在${NC}"
    echo "  路径: $path"
    echo "  大小: $(du -h "$path" | cut -f1)"
    echo ""
    return 0
  else
    echo -e "${RED}✗ 不存在${NC}"
    return 1
  fi
}

# 1. 测试配置文件挂载
echo "=========================================="
echo "1. 配置文件挂载点"
echo "=========================================="
test_mount "/mnt/efs/configs" "配置文件目录"

# 列出配置文件
if [ -d "/mnt/efs/configs" ]; then
  echo "可用的配置文件:"
  find /mnt/efs/configs -name "*.json" -type f | while read -r file; do
    echo "  - $file"
  done
  echo ""
fi

# 2. 测试数据挂载
echo "=========================================="
echo "2. 数据目录挂载点"
echo "=========================================="
test_mount "/mnt/efs/data" "数据目录 (EFS)"
test_mount "/usr/share/nginx/html/data" "数据目录 (Nginx)"

# 3. 测试日志挂载
echo "=========================================="
echo "3. 日志目录挂载点"
echo "=========================================="
test_mount "/mnt/efs/logs" "日志目录"

# 检查是否可写
echo -n "测试日志目录写权限 ... "
if touch /mnt/efs/logs/test_write_$$.tmp 2>/dev/null; then
  rm /mnt/efs/logs/test_write_$$.tmp
  echo -e "${GREEN}✓ 可写${NC}"
else
  echo -e "${RED}✗ 不可写${NC}"
fi
echo ""

# 4. 测试 Nginx HTML 挂载
echo "=========================================="
echo "4. Nginx HTML 挂载点"
echo "=========================================="
test_mount "/usr/share/nginx/html" "Nginx HTML 目录"

# 检查是否覆盖了镜像内容
if [ -d "/usr/share/nginx/html" ]; then
  echo "Nginx HTML 目录内容:"
  ls -lh /usr/share/nginx/html/ | head -10
  echo ""
  
  if [ ! -f "/usr/share/nginx/html/index.html" ]; then
    echo -e "${YELLOW}⚠️  警告: index.html 不存在，EFS 挂载可能覆盖了镜像内容${NC}"
  fi
fi

# 5. 测试工具和脚本
echo "=========================================="
echo "5. 工具和脚本检查"
echo "=========================================="

echo -n "AWS CLI ... "
if command -v aws &> /dev/null; then
  echo -e "${GREEN}✓ 已安装 ($(aws --version))${NC}"
else
  echo -e "${RED}✗ 未安装${NC}"
fi

echo -n "jq ... "
if command -v jq &> /dev/null; then
  echo -e "${GREEN}✓ 已安装 ($(jq --version))${NC}"
else
  echo -e "${RED}✗ 未安装${NC}"
fi

echo -n "bash ... "
if command -v bash &> /dev/null; then
  echo -e "${GREEN}✓ 已安装 ($(bash --version | head -1))${NC}"
else
  echo -e "${RED}✗ 未安装${NC}"
fi

test_file "/usr/local/bin/aws_ecs_run_all.sh" "调度脚本"
test_file "/.env" ".env 环境变量文件"

# 6. 测试配置文件路径解析
echo "=========================================="
echo "6. 配置文件路径解析测试"
echo "=========================================="

test_config_path() {
  local input="$1"
  echo "输入: $input"
  
  # 模拟脚本中的路径解析逻辑
  CONFIG_FILE="$input"
  
  if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "/mnt/efs/configs/$CONFIG_FILE" ]; then
      CONFIG_FILE="/mnt/efs/configs/$CONFIG_FILE"
    elif [ -f "/mnt/efs/$CONFIG_FILE" ]; then
      CONFIG_FILE="/mnt/efs/$CONFIG_FILE"
    elif [ -f "/mnt/efs/configs/${CONFIG_FILE#configs/}" ]; then
      CONFIG_FILE="/mnt/efs/configs/${CONFIG_FILE#configs/}"
    fi
  fi
  
  if [ -f "$CONFIG_FILE" ]; then
    echo -e "  ${GREEN}✓ 解析成功: $CONFIG_FILE${NC}"
  else
    echo -e "  ${RED}✗ 解析失败${NC}"
  fi
  echo ""
}

test_config_path "configs/astock_config_hourly.json"
test_config_path "astock_config_hourly.json"
test_config_path "/mnt/efs/configs/astock_config_hourly.json"

# 7. 环境变量检查
echo "=========================================="
echo "7. 环境变量检查"
echo "=========================================="

check_env() {
  local var_name="$1"
  echo -n "$var_name ... "
  if [ -n "${!var_name}" ]; then
    echo -e "${GREEN}✓ ${!var_name}${NC}"
  else
    echo -e "${YELLOW}⚠️  未设置${NC}"
  fi
}

check_env "AWS_REGION"
check_env "ECS_CLUSTER"
check_env "ECS_SUBNET"
check_env "ECS_SECURITY_GROUP"
check_env "DATA_PREP_TASK_DEF"
check_env "AGENT_TASK_DEF"

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
