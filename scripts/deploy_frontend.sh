#!/bin/bash
# Frontend 部署脚本 - 构建镜像并更新 ECS 任务定义
# 用法: ./deploy_frontend.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

echo_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

echo_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================
# 配置参数
# ============================================
REGION="us-west-2"
ECR_REPO="648104168728.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-frontend"
IMAGE_TAG="latest"
TASK_DEFINITION_FILE="configs/task_trader_frontend.json"
CLUSTER_NAME="trader-cluster"
SERVICE_NAME="trader-frontend"

echo_info "=========================================="
echo_info "Frontend 部署脚本"
echo_info "=========================================="
echo_info "区域: $REGION"
echo_info "ECR 仓库: $ECR_REPO"
echo_info "镜像标签: $IMAGE_TAG"
echo_info "任务定义: $TASK_DEFINITION_FILE"
echo ""

# ============================================
# Step 1: 检查前置条件
# ============================================
echo_info "Step 1: 检查前置条件..."

# 检查 Docker
if ! command -v docker &> /dev/null; then
  echo_error "Docker 未安装"
  exit 1
fi

# 检查 AWS CLI
if ! command -v aws &> /dev/null; then
  echo_error "AWS CLI 未安装"
  exit 1
fi

# 检查 .env 文件
if [ ! -f ".env" ]; then
  echo_error ".env 文件不存在"
  exit 1
fi

# 检查 Dockerfile.frontend
if [ ! -f "Dockerfile.frontend" ]; then
  echo_error "Dockerfile.frontend 不存在"
  exit 1
fi

# 检查任务定义文件
if [ ! -f "$TASK_DEFINITION_FILE" ]; then
  echo_error "任务定义文件不存在: $TASK_DEFINITION_FILE"
  exit 1
fi

echo_success "前置条件检查通过"
echo ""

# ============================================
# Step 2: 构建 Frontend 镜像
# ============================================
echo_info "=========================================="
echo_info "Step 2: 构建 Frontend 镜像"
echo_info "=========================================="

echo_info "开始构建镜像..."
if docker build -f Dockerfile.frontend -t trader-frontend:$IMAGE_TAG .; then
  echo_success "镜像构建成功"
else
  echo_error "镜像构建失败"
  exit 1
fi

echo ""

# ============================================
# Step 3: 登录 ECR
# ============================================
echo_info "=========================================="
echo_info "Step 3: 登录 ECR"
echo_info "=========================================="

echo_info "获取 ECR 登录凭证..."
if sudo -u ec2-user aws ecr get-login-password --region $REGION | \
   docker login --username AWS --password-stdin 648104168728.dkr.ecr.$REGION.amazonaws.com; then
  echo_success "ECR 登录成功"
else
  echo_error "ECR 登录失败"
  exit 1
fi

echo ""

# ============================================
# Step 4: 标记并推送镜像
# ============================================
echo_info "=========================================="
echo_info "Step 4: 推送镜像到 ECR"
echo_info "=========================================="

echo_info "标记镜像..."
docker tag trader-frontend:$IMAGE_TAG $ECR_REPO:$IMAGE_TAG

echo_info "推送镜像到 ECR..."
if docker push $ECR_REPO:$IMAGE_TAG; then
  echo_success "镜像推送成功"
  
  # 获取镜像 digest
  IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' $ECR_REPO:$IMAGE_TAG | cut -d'@' -f2)
  echo_info "镜像 Digest: $IMAGE_DIGEST"
else
  echo_error "镜像推送失败"
  exit 1
fi

echo ""

# ============================================
# Step 5: 注册新的任务定义
# ============================================
echo_info "=========================================="
echo_info "Step 5: 注册 ECS 任务定义"
echo_info "=========================================="

echo_info "注册任务定义: $TASK_DEFINITION_FILE"
TASK_DEF_ARN=$(sudo -u ec2-user aws ecs register-task-definition \
  --cli-input-json file://$TASK_DEFINITION_FILE \
  --region $REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

if [ -n "$TASK_DEF_ARN" ]; then
  echo_success "任务定义注册成功"
  echo_info "任务定义 ARN: $TASK_DEF_ARN"
else
  echo_error "任务定义注册失败"
  exit 1
fi

echo ""

# ============================================
# Step 6: 更新 ECS 服务（可选）
# ============================================
echo_info "=========================================="
echo_info "Step 6: 更新 ECS 服务"
echo_info "=========================================="

echo_warn "是否更新 ECS 服务 '$SERVICE_NAME'? (y/n)"
read -r response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
  echo_info "更新服务: $SERVICE_NAME"
  
  # 提取任务定义的 family:revision
  TASK_DEF_REVISION=$(echo $TASK_DEF_ARN | grep -oP 'task-definition/\K.*')
  
  if sudo -u ec2-user aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $TASK_DEF_REVISION \
    --region $REGION \
    --query 'service.serviceName' \
    --output text > /dev/null 2>&1; then
    echo_success "服务更新成功，正在滚动部署..."
    echo_info "新任务定义: $TASK_DEF_REVISION"
    echo_info "可以通过以下命令查看部署状态:"
    echo_info "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION"
  else
    echo_warn "服务更新失败或服务不存在"
    echo_info "如果服务不存在，请手动创建服务或使用新的任务定义启动任务"
  fi
else
  echo_info "跳过服务更新"
  echo_info "您可以手动更新服务:"
  TASK_DEF_REVISION=$(echo $TASK_DEF_ARN | grep -oP 'task-definition/\K.*')
  echo_info "  aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --task-definition $TASK_DEF_REVISION --region $REGION"
fi

echo ""

# ============================================
# 完成
# ============================================
echo_success "=========================================="
echo_success "部署完成！"
echo_success "=========================================="
echo ""
echo_info "摘要:"
echo_info "  - 镜像: $ECR_REPO:$IMAGE_TAG"
echo_info "  - 任务定义: $TASK_DEF_ARN"
echo_info "  - 区域: $REGION"
echo ""
echo_info "后续操作:"
echo_info "  1. 查看服务状态: aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION"
echo_info "  2. 查看任务: aws ecs list-tasks --cluster $CLUSTER_NAME --service-name $SERVICE_NAME --region $REGION"
echo_info "  3. 查看日志: aws logs tail /ecs/trader-frontend --follow --region $REGION"
echo ""
