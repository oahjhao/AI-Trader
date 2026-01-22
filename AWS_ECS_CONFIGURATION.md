# AWS ECS 任务定义配置指南

本文档说明如何将 docker-compose.yml 中的服务转换为 AWS ECS 任务定义并执行。

## 前置条件

1. ECR 中已上传镜像：
   - `trader-app` (主应用镜像)
   - `trader-frontend` (前端镜像)
2. EFS 文件系统已创建并挂载
3. 环境变量已在 AWS Secrets Manager 或 SSM Parameter Store 中配置

## 一、数据准备任务定义 (agent-base)

### 任务定义名称
`trader-data-preparation`

### 容器定义

```json
{
  "family": "trader-data-preparation",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "data-prep",
      "image": "YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com/trader-app:latest",
      "essential": true,
      "entryPoint": ["bash", "scripts/data_preparation_entrypoint.sh"],
      "command": ["configs/astock_config_hourly.json"],
      "environment": [
        {
          "name": "TZ",
          "value": "Asia/Shanghai"
        },
        {
          "name": "START_DATE",
          "value": ""
        },
        {
          "name": "END_DATE",
          "value": ""
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "efs-configs",
          "containerPath": "/home/ec2-user/AI-Trader/configs"
        },
        {
          "sourceVolume": "efs-data",
          "containerPath": "/home/ec2-user/AI-Trader/data"
        },
        {
          "sourceVolume": "efs-logs",
          "containerPath": "/home/ec2-user/AI-Trader/logs"
        },
        {
          "sourceVolume": "efs-docs",
          "containerPath": "/home/ec2-user/AI-Trader/docs"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/trader-data-preparation",
          "awslogs-region": "YOUR_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "efs-configs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/configs",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/data",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-logs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/logs",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-docs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/docs",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

### CLI 运行命令

```bash
# 运行数据准备任务（LIVE 模式 - 自动获取历史数据）
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-data-preparation \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }"

# 运行数据准备任务（MANUAL 模式 - 指定日期范围用于回测）
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-data-preparation \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "data-prep",
      "command": ["configs/astock_config_hourly.json", "2025-01-01", "2025-01-21"]
    }]
  }'
```

## 二、交易 Agent 任务定义模板

### 任务定义名称
`trader-agent` (通用模板)

### 容器定义

```json
{
  "family": "trader-agent",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "agent",
      "image": "YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com/trader-app:latest",
      "essential": true,
      "entryPoint": ["bash", "scripts/container_entrypoint.sh"],
      "command": ["configs/astock_config_hourly.json", "--signature", "PLACEHOLDER"],
      "environment": [
        {
          "name": "TZ",
          "value": "Asia/Shanghai"
        },
        {
          "name": "RUNTIME_ENV_PATH",
          "value": "/tmp/runtime_env.json"
        }
      ],
      "secrets": [
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT:secret:trader/openai-api-key"
        },
        {
          "name": "OPENAI_API_BASE",
          "valueFrom": "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT:secret:trader/openai-api-base"
        },
        {
          "name": "DINGTALK_WEBHOOK_URL",
          "valueFrom": "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT:secret:trader/dingtalk-webhook"
        },
        {
          "name": "DINGTALK_SECRET",
          "valueFrom": "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT:secret:trader/dingtalk-secret"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "efs-configs",
          "containerPath": "/home/ec2-user/AI-Trader/configs"
        },
        {
          "sourceVolume": "efs-data",
          "containerPath": "/home/ec2-user/AI-Trader/data"
        },
        {
          "sourceVolume": "efs-logs",
          "containerPath": "/home/ec2-user/AI-Trader/logs"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/trader-agent",
          "awslogs-region": "YOUR_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "efs-configs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/configs",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/data",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-logs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/logs",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

### CLI 运行命令 - 运行各个策略

```bash
# 1. Balanced Strategy
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-agent \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "agent",
      "command": ["configs/astock_config_hourly.json", "--signature", "DS_pick_balanced_260119"]
    }]
  }'

# 2. Nuts Strategy (Aggressive)
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-agent \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "agent",
      "command": ["configs/astock_config_hourly.json", "--signature", "DS_pick_nuts_260119"]
    }]
  }'

# 3. Tech Strategy
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-agent \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "agent",
      "command": ["configs/astock_config_hourly.json", "--signature", "DS_pick_tech_260119"]
    }]
  }'

# 4. Monk Strategy
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-agent \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "agent",
      "command": ["configs/astock_config_hourly.json", "--signature", "DS_pick_monk_260119"]
    }]
  }'
```

## 三、前端服务定义 (ECS Service - 长期运行)

### 任务定义名称
`trader-frontend`

### 容器定义

```json
{
  "family": "trader-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com/trader-frontend:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8888,
          "protocol": "tcp"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "efs-data",
          "containerPath": "/usr/share/nginx/html/data",
          "readOnly": true
        },
        {
          "sourceVolume": "efs-config-yaml",
          "containerPath": "/usr/share/nginx/html/config.yaml",
          "readOnly": true
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/trader-frontend",
          "awslogs-region": "YOUR_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "efs-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/data",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "efs-config-yaml",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-XXXXXXXX",
        "rootDirectory": "/docs/config.yaml",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

### 创建 ECS Service

```bash
aws ecs create-service \
  --cluster trader-cluster \
  --service-name trader-frontend \
  --task-definition trader-frontend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:YOUR_REGION:YOUR_ACCOUNT:targetgroup/trader-frontend-tg,containerName=frontend,containerPort=8888"
```

## 四、完整执行流程脚本

### 创建 Shell 脚本来模拟 docker-compose 顺序执行

```bash
#!/bin/bash
# aws_ecs_run_all.sh - 按照 docker-compose 逻辑顺序执行 ECS 任务

set -e

CLUSTER="trader-cluster"
SUBNET="subnet-xxx"
SECURITY_GROUP="sg-xxx"
REGION="us-east-1"

echo "📊 Step 1: Running data preparation task..."
DATA_PREP_TASK=$(aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition trader-data-preparation \
  --launch-type FARGATE \
  --region $REGION \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --query 'tasks[0].taskArn' \
  --output text)

echo "✅ Data prep task started: $DATA_PREP_TASK"
echo "⏳ Waiting for data preparation to complete..."

# 等待数据准备任务完成
aws ecs wait tasks-stopped \
  --cluster $CLUSTER \
  --tasks $DATA_PREP_TASK \
  --region $REGION

# 检查任务是否成功
TASK_EXIT_CODE=$(aws ecs describe-tasks \
  --cluster $CLUSTER \
  --tasks $DATA_PREP_TASK \
  --region $REGION \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)

if [ "$TASK_EXIT_CODE" != "0" ]; then
  echo "❌ Data preparation failed with exit code: $TASK_EXIT_CODE"
  exit 1
fi

echo "✅ Data preparation completed successfully!"

echo ""
echo "🤖 Step 2: Starting all agent strategies in parallel..."

# 并行启动所有策略
SIGNATURES=("DS_pick_balanced_260119" "DS_pick_nuts_260119" "DS_pick_tech_260119" "DS_pick_monk_260119")
TASK_ARNS=()

for SIGNATURE in "${SIGNATURES[@]}"; do
  echo "🚀 Starting agent: $SIGNATURE"
  TASK_ARN=$(aws ecs run-task \
    --cluster $CLUSTER \
    --task-definition trader-agent \
    --launch-type FARGATE \
    --region $REGION \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
    --overrides "{\"containerOverrides\":[{\"name\":\"agent\",\"command\":[\"configs/astock_config_hourly.json\",\"--signature\",\"$SIGNATURE\"]}]}" \
    --query 'tasks[0].taskArn' \
    --output text)
  
  TASK_ARNS+=($TASK_ARN)
  echo "✅ Agent $SIGNATURE started: $TASK_ARN"
done

echo ""
echo "⏳ Waiting for all agents to complete..."

# 等待所有任务完成
for TASK_ARN in "${TASK_ARNS[@]}"; do
  aws ecs wait tasks-stopped \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region $REGION
done

echo ""
echo "📋 Checking agent task results..."

# 检查所有任务结果
ALL_SUCCESS=true
for i in "${!TASK_ARNS[@]}"; do
  TASK_ARN="${TASK_ARNS[$i]}"
  SIGNATURE="${SIGNATURES[$i]}"
  
  EXIT_CODE=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region $REGION \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)
  
  if [ "$EXIT_CODE" = "0" ]; then
    echo "✅ $SIGNATURE completed successfully"
  else
    echo "❌ $SIGNATURE failed with exit code: $EXIT_CODE"
    ALL_SUCCESS=false
  fi
done

if [ "$ALL_SUCCESS" = true ]; then
  echo ""
  echo "🎉 All trading agents completed successfully!"
  exit 0
else
  echo ""
  echo "⚠️ Some agents failed. Check CloudWatch logs for details."
  exit 1
fi
```

### 脚本使用方法

```bash
# 1. 修改脚本中的配置参数
vim aws_ecs_run_all.sh

# 2. 赋予执行权限
chmod +x aws_ecs_run_all.sh

# 3. 运行脚本
./aws_ecs_run_all.sh
```

## 五、环境变量配置

### 在 AWS Secrets Manager 中创建密钥

```bash
# OpenAI API Key
aws secretsmanager create-secret \
  --name trader/openai-api-key \
  --secret-string "sk-xxx"

# OpenAI API Base
aws secretsmanager create-secret \
  --name trader/openai-api-base \
  --secret-string "https://api.openai.com/v1"

# DingTalk Webhook
aws secretsmanager create-secret \
  --name trader/dingtalk-webhook \
  --secret-string "https://oapi.dingtalk.com/robot/send?access_token=xxx"

# DingTalk Secret
aws secretsmanager create-secret \
  --name trader/dingtalk-secret \
  --secret-string "SECxxx"
```

## 六、日志查看

### 查看 CloudWatch 日志

```bash
# 查看数据准备日志
aws logs tail /ecs/trader-data-preparation --follow

# 查看特定 agent 日志
aws logs tail /ecs/trader-agent --follow --filter-pattern "DS_pick_balanced"

# 查看前端日志
aws logs tail /ecs/trader-frontend --follow
```

## 七、注意事项

1. **EFS 挂载点**: 确保所有任务定义中的 EFS 文件系统 ID (`fs-XXXXXXXX`) 一致
2. **网络配置**: 安全组必须允许：
   - 出站流量访问 Internet (API 调用)
   - 入站流量访问 EFS (端口 2049)
   - 前端服务入站流量 (端口 8888)
3. **任务顺序**: 必须等待数据准备任务完成后才能启动 agent 任务
4. **并发控制**: ECS 通过 task ARN 确保每个 signature 只有一个任务实例运行
5. **资源限制**: 根据实际需求调整 CPU 和内存配置

## 八、快速参考

### 任务定义注册

```bash
# 注册数据准备任务定义
aws ecs register-task-definition --cli-input-json file://task-def-data-prep.json

# 注册 agent 任务定义
aws ecs register-task-definition --cli-input-json file://task-def-agent.json

# 注册前端任务定义
aws ecs register-task-definition --cli-input-json file://task-def-frontend.json
```

### 手动运行单个任务测试

```bash
# 测试数据准备
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-data-preparation \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"

# 测试单个 agent
aws ecs run-task \
  --cluster trader-cluster \
  --task-definition trader-agent \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"agent","command":["configs/astock_config_hourly.json","--signature","DS_pick_balanced_260119"]}]}'
```

---

## 附录：docker-compose vs ECS 映射关系

| docker-compose 元素 | ECS 对应元素 | 说明 |
|-------------------|------------|-----|
| `image` | `containerDefinitions[].image` | ECR 镜像 URI |
| `volumes` | `mountPoints` + `volumes` | EFS 挂载 |
| `environment` | `environment` / `secrets` | 环境变量/密钥 |
| `entrypoint` | `entryPoint` | 入口命令 |
| `command` | `command` | 运行参数 |
| `depends_on` | 脚本控制任务顺序 | 使用 `aws ecs wait` |
| `ports` | `portMappings` | 仅前端需要 |
| `container_name` | Task ARN | ECS 自动分配 |
