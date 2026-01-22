# ECS Fargate 定时任务配置指南

本文档说明如何在 **trader-frontend 容器**中通过 cron 定时任务触发 ECS Fargate 任务执行交易策略。

## 架构说明

```
ECS Service: trader-frontend (Nginx + AWS CLI)
    ↓ (crond 定时触发)
aws_ecs_run_all.sh (从 .env 加载配置)
    ↓
ECS Fargate: trader-data-preparation (数据准备)
    ↓ (完成后)
ECS Fargate: trader-agent × N (并行执行多个策略)
    ↓
EFS 共享存储 (数据 & 日志)
```

**重要变更**：
- ✅ 脚本现在在 **trader-frontend 容器**中运行
- ✅ 所有环境变量从 **/.env** 文件加载（已打包到镜像）
- ✅ 无需在 EC2 上单独配置，容器内即可完成

## 前置条件

### 1. 构建包含必要工具的 Frontend 镜像

Frontend 镜像已经包含：
- ✅ AWS CLI (用于调用 ECS API)
- ✅ jq (用于解析 JSON 配置)
- ✅ bash (用于运行脚本)
- ✅ aws_ecs_run_all.sh (已复制到 /usr/local/bin/)
- ✅ .env 文件 (已打包到 /.env)

**构建镜像**：
```bash
# 1. 准备 .env 文件
cp .env.example .env
vim .env  # 填写实际配置

# 2. 构建 frontend 镜像
docker build -f Dockerfile.frontend -t trader-frontend:latest .

# 或者推送到 ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_URI>
docker tag trader-frontend:latest <ECR_URI>/trader-frontend:latest
docker push <ECR_URI>/trader-frontend:latest
```

### 2. 配置 .env 文件

**在构建镜像前**，编辑项目根目录的 `.env` 文件：

```bash
# ============================================
# AWS ECS Configuration
# ============================================
AWS_REGION=us-east-1
ECS_CLUSTER=trader-cluster
ECS_SUBNET=subnet-0123456789abcdef0
ECS_SECURITY_GROUP=sg-0123456789abcdef0
DATA_PREP_TASK_DEF=trader-data-preparation
AGENT_TASK_DEF=trader-agent

# ============================================
# API Keys (可选，agent 容器需要)
# ============================================
OPENAI_API_KEY=sk-xxx
OPENAI_API_BASE=https://api.openai.com/v1
```

**重要**：
- .env 文件会打包到镜像的 `/.env` 路径
- 脚本会自动加载这个文件
- 无需在容器运行时再次配置环境变量

### 3. 配置 IAM 权限

**为 ECS Task Execution Role 添加权限**（frontend 容器需要）：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:RunTask",
        "ecs:DescribeTasks",
        "ecs:DescribeClusters",
        "ecs:ListTasks"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::*:role/ecsTaskExecutionRole",
        "arn:aws:iam::*:role/trader-task-role"
      ]
    }
  ]
}
```

### 4. 验证 ECS 任务定义

确保以下两个任务定义已创建：

```bash
# 检查任务定义
aws ecs describe-task-definition \
  --task-definition trader-data-preparation \
  --region us-east-1

aws ecs describe-task-definition \
  --task-definition trader-agent \
  --region us-east-1
```

## 在 Frontend 容器中使用脚本

### 方式 1: 进入容器手动执行

```bash
# 1. 找到 frontend 容器
docker ps | grep trader-frontend

# 2. 进入容器
docker exec -it <container_id> /bin/bash

# 或者在 ECS 中使用 ECS Exec
aws ecs execute-command \
  --cluster trader-cluster \
  --task <task_id> \
  --container trader-frontend \
  --command "/bin/bash" \
  --interactive

# 3. 执行脚本
aws_ecs_run_all.sh configs/astock_config_hourly.json

# 查看日志
tail -f /var/log/nginx/access.log
```

### 方式 2: 使用 docker exec 直接执行

```bash
# 在宿主机执行（适用于 EC2 上的 Docker）
docker exec trader-frontend aws_ecs_run_all.sh configs/astock_config_hourly.json
```

### 方式 3: 配置容器内 Crontab（推荐生产环境）

**在 frontend 容器中设置定时任务**：

```bash
# 1. 进入容器
docker exec -it trader-frontend /bin/bash

# 2. 安装 cronie（Alpine Linux）
apk add --no-cache cronie

# 3. 创建 crontab 配置
cat > /etc/crontabs/root <<'EOF'
# 每个工作日 9:00 执行小时级交易
0 9 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh configs/astock_config_hourly.json >> /var/log/trader.log 2>&1

# 每个工作日 15:30 执行日级交易  
30 15 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh configs/astock_config.json >> /var/log/trader.log 2>&1
EOF

# 4. 启动 crond
crond -l 2 -f &

# 5. 验证 cron 任务
crontab -l
```

**注意**：如果容器重启，cron 配置会丢失。建议：
- 方案 1: 在 Dockerfile.frontend 中预配置 cron
- 方案 2: 使用外部调度工具（AWS EventBridge、Jenkins 等）

### 方式 4: 使用 AWS EventBridge（推荐）

**通过 EventBridge 定时触发容器内脚本**：

1. **创建 Lambda 函数**（触发 ECS Exec）：

```python
import boto3
import json

ecs = boto3.client('ecs')

def lambda_handler(event, context):
    # 查找 frontend 任务
    response = ecs.list_tasks(
        cluster='trader-cluster',
        serviceName='trader-frontend',
        desiredStatus='RUNNING'
    )
    
    if not response['taskArns']:
        return {'statusCode': 404, 'body': 'No frontend task found'}
    
    task_arn = response['taskArns'][0]
    
    # 执行脚本
    ecs.execute_command(
        cluster='trader-cluster',
        task=task_arn,
        container='trader-frontend',
        command='/usr/local/bin/aws_ecs_run_all.sh configs/astock_config_hourly.json',
        interactive=False
    )
    
    return {'statusCode': 200, 'body': 'Script executed'}
```

2. **创建 EventBridge 规则**：

```bash
# 每个工作日 9:00 触发
aws events put-rule \
  --name trader-hourly-schedule \
  --schedule-expression "cron(0 9 ? * MON-FRI *)" \
  --state ENABLED

# 添加 Lambda 目标
aws events put-targets \
  --rule trader-hourly-schedule \
  --targets "Id"="1","Arn"="<LAMBDA_ARN>"
```

## 配置文件路径说明

脚本支持多种路径格式：

1. **相对路径**（容器内）：
   ```bash
   aws_ecs_run_all.sh configs/astock_config_hourly.json
   ```

2. **EFS 挂载路径**：
   ```bash
   aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json
   ```

3. **自动查找**：
   - 脚本会先检查相对路径
   - 如果不存在，自动尝试 `/mnt/efs/` 前缀

**EFS 挂载点示例**（在 ECS Task Definition 中配置）：
```json
{
  "volumes": [
    {
      "name": "efs-storage",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-xxxxx",
        "rootDirectory": "/"
      }
    }
  ],
  "mountPoints": [
    {
      "sourceVolume": "efs-storage",
      "containerPath": "/mnt/efs"
    }
  ]
}
```

## 环境变量说明

所有环境变量从 `/.env` 文件加载（已打包到镜像）：

```bash
# AWS 配置
AWS_REGION=us-east-1                          # AWS 区域
ECS_CLUSTER=trader-cluster                    # ECS 集群名称
ECS_SUBNET=subnet-xxx                         # 子网 ID
ECS_SECURITY_GROUP=sg-xxx                     # 安全组 ID

# 任务定义
DATA_PREP_TASK_DEF=trader-data-preparation   # 数据准备任务
AGENT_TASK_DEF=trader-agent                   # Agent 任务
```

**动态覆盖**（可选）：
```bash
# 在容器内临时修改
export ECS_CLUSTER=trader-cluster-prod
aws_ecs_run_all.sh configs/astock_config_hourly.json
```

## 监控和维护

### 1. 查看容器日志

```bash
# Docker 环境
docker logs trader-frontend
docker logs -f trader-frontend  # 实时查看

# ECS 环境
aws logs tail /ecs/trader-frontend --follow
```

### 2. 查看脚本执行日志

```bash
# 进入容器
docker exec -it trader-frontend /bin/sh

# 查看日志
tail -f /var/log/trader.log
```

### 3. 查看 ECS 任务状态

### 4. 查看 ECS 任务状态

```bash
# 列出最近运行的任务
aws ecs list-tasks \
  --cluster trader-cluster \
  --region us-east-1

# 查看任务详情
aws ecs describe-tasks \
  --cluster trader-cluster \
  --tasks <TASK_ARN> \
  --region us-east-1
```

### 5. 查看 CloudWatch 日志

```bash
# 数据准备任务日志
aws logs tail /ecs/trader-data-preparation --follow

# Agent 任务日志
aws logs tail /ecs/trader-agent --follow

# 过滤特定策略
aws logs tail /ecs/trader-agent --follow --filter-pattern "DS_pick_balanced"
```

### 6. 进入容器调试

```bash
# Docker 环境
docker exec -it trader-frontend /bin/sh

# ECS 环境（需要启用 ECS Exec）
aws ecs execute-command \
  --cluster trader-cluster \
  --task <task_id> \
  --container trader-frontend \
  --command "/bin/sh" \
  --interactive

# 测试脚本
aws_ecs_run_all.sh --help

# 检查环境变量
cat /.env
env | grep ECS
```

## 故障排查

### 1. 脚本无法执行

```bash
# 检查脚本是否存在
docker exec trader-frontend ls -l /usr/local/bin/aws_ecs_run_all.sh

# 检查 .env 文件
docker exec trader-frontend cat /.env

# 手动加载 .env
docker exec trader-frontend /bin/sh -c "source /.env && env | grep ECS"
```

### 2. AWS 认证失败

```bash
# 检查容器的 IAM Role
aws sts get-caller-identity

# 检查 Task Role（在 ECS Task Definition 中配置）
# Task Execution Role 需要包含 ecs:RunTask 等权限
```

### 3. ECS 任务启动失败

```bash
# 检查任务定义
aws ecs describe-task-definition --task-definition trader-agent

# 检查集群状态
aws ecs describe-clusters --clusters trader-cluster

# 检查子网和安全组
aws ec2 describe-subnets --subnet-ids $ECS_SUBNET
aws ec2 describe-security-groups --group-ids $ECS_SECURITY_GROUP
```

### 4. 配置文件找不到

```bash
# 检查 EFS 挂载
docker exec trader-frontend df -h | grep efs

# 检查配置文件
docker exec trader-frontend ls -l /mnt/efs/configs/

# 使用绝对路径
docker exec trader-frontend aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json
```

## 最佳实践

1. **环境隔离**: 
   - 生产环境和测试环境使用不同的 .env 文件
   - 分别构建不同的镜像标签（如 trader-frontend:prod 和 trader-frontend:dev）

2. **安全性**:
   - 不要在 .env 中硬编码敏感 API Key
   - 使用 AWS Secrets Manager 存储敏感信息
   - Task Role 权限最小化

3. **定时调度**:
   - 推荐使用 AWS EventBridge（更可靠）
   - 容器内 cron 仅用于开发测试

4. **日志管理**:
   - 配置 CloudWatch Logs 自动收集
   - 设置日志保留期限（如 30 天）

5. **成本优化**:
   - 使用 Fargate Spot 降低成本（适用于非关键任务）
   - 合理设置任务的 CPU 和内存限制

6. **监控告警**:
   - 配置 CloudWatch 告警监控任务失败率
   - 集成钉钉 Webhook 发送实时通知

## 完整部署流程

### 1. 准备阶段

```bash
# 克隆项目
git clone <repository>
cd AI-Trader

# 配置环境变量
cp .env.example .env
vim .env  # 填写实际配置

# 检查配置
cat .env | grep -E 'ECS|AWS'
```

### 2. 构建镜像

```bash
# 构建 trader-app 镜像（data-prep 和 agent 使用）
docker build -t trader-app:latest .

# 构建 trader-frontend 镜像（包含调度脚本）
docker build -f Dockerfile.frontend -t trader-frontend:latest .
```

### 3. 推送到 ECR

```bash
# 登录 ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-1.amazonaws.com

# 标记镜像
docker tag trader-app:latest <ECR_URI>/trader-app:latest
docker tag trader-frontend:latest <ECR_URI>/trader-frontend:latest

# 推送镜像
docker push <ECR_URI>/trader-app:latest
docker push <ECR_URI>/trader-frontend:latest
```

### 4. 创建 ECS 任务定义

参考 [AWS_ECS_CONFIGURATION.md](../AWS_ECS_CONFIGURATION.md)

### 5. 部署并测试

```bash
# 启动 frontend service
aws ecs update-service \
  --cluster trader-cluster \
  --service trader-frontend \
  --force-new-deployment

# 进入容器测试
TASK_ID=$(aws ecs list-tasks --cluster trader-cluster --service-name trader-frontend --query 'taskArns[0]' --output text)

aws ecs execute-command \
  --cluster trader-cluster \
  --task $TASK_ID \
  --container trader-frontend \
  --command "/bin/sh" \
  --interactive

# 在容器内测试脚本
aws_ecs_run_all.sh configs/astock_config_hourly.json
```

## 总结

通过本配置，您可以：
- ✅ 在 **trader-frontend 容器**内使用 cron 或 EventBridge 定时触发交易
- ✅ 所有配置通过 **.env 文件**集中管理，打包到镜像
- ✅ 数据准备完成后自动并行启动多个交易策略
- ✅ 从配置文件动态读取 Agent 列表
- ✅ 支持实时交易和回测两种模式
- ✅ 完整的日志记录和监控能力
- ✅ 无需在 EC2 上单独配置，容器即包含所有依赖

**关键变更总结**：
1. 脚本从 **EC2 执行** 改为 **frontend 容器内执行**
2. 环境变量从 **EC2 配置** 改为 **.env 文件打包到镜像**
3. Frontend Dockerfile 新增 **AWS CLI、jq、bash** 等工具
4. 脚本支持 **自动加载 /.env** 文件
5. 配置文件路径支持 **EFS 挂载路径自动检测**

如有问题，请查看日志文件或 CloudWatch 日志组。
