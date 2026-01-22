# Frontend 容器挂载配置与脚本调整总结

## ✅ 已完成的修改

### 1. ECS 任务配置优化 ([task_trader_frontend.json](file:///home/ec2-user/AI-Trader/configs/task_trader_frontend.json))

#### 修改内容
- **移除了有问题的挂载**：`/usr/share/nginx/html` ← `/ai-trader/docs`
  - 原因：这个挂载会覆盖镜像中的静态 HTML 文件（index.html 等）
- **调整配置文件权限**：`/mnt/efs/configs` 改为只读（`readOnly: true`）
  - 原因：脚本只需读取配置，不需要写权限

#### 最终挂载配置
```json
{
  "mountPoints": [
    {
      "sourceVolume": "efs-data",
      "containerPath": "/usr/share/nginx/html/data",
      "readOnly": false
    },
    {
      "sourceVolume": "efs-configs",
      "containerPath": "/mnt/efs/configs",
      "readOnly": true
    },
    {
      "sourceVolume": "efs-logs",
      "containerPath": "/mnt/efs/logs",
      "readOnly": false
    }
  ],
  "volumes": [
    {
      "name": "efs-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-0b84c5c74e468c34b",
        "rootDirectory": "/ai-trader/data"
      }
    },
    {
      "name": "efs-configs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-0b84c5c74e468c34b",
        "rootDirectory": "/ai-trader/configs"
      }
    },
    {
      "name": "efs-logs",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-0b84c5c74e468c34b",
        "rootDirectory": "/ai-trader/logs"
      }
    }
  ]
}
```

---

### 2. 脚本路径解析优化 ([aws_ecs_run_all.sh](file:///home/ec2-user/AI-Trader/scripts/aws_ecs_run_all.sh))

#### 智能路径解析逻辑
支持多种配置文件输入格式，自动匹配到正确的 EFS 路径：

```bash
# 输入示例 1: configs/astock_config_hourly.json
# → 解析为: /mnt/efs/configs/configs/astock_config_hourly.json (如果存在)
# → 或: /mnt/efs/configs/astock_config_hourly.json

# 输入示例 2: astock_config_hourly.json
# → 解析为: /mnt/efs/configs/astock_config_hourly.json

# 输入示例 3: /mnt/efs/configs/astock_config_hourly.json
# → 直接使用绝对路径
```

#### 路径解析优先级
1. 检查输入路径是否存在
2. 尝试 `/mnt/efs/configs/` 前缀（ECS 挂载点）
3. 尝试 `/mnt/efs/` 前缀（兼容性）
4. 去掉 `configs/` 前缀后重试

---

### 3. 日志持久化增强

#### 新增功能
- **自动创建日志目录**：`/mnt/efs/logs/scheduler/`
- **日志文件命名**：`aws_ecs_run_YYYYMMDD_HHMMSS.log`
- **双输出机制**：同时输出到终端和日志文件

#### 日志示例
```bash
# 终端输出（带颜色）
[INFO] 集群: trader-cluster
[SUCCESS] 数据准备任务完成！

# 日志文件（无颜色，带时间戳）
[2026-01-22 15:30:01] [INFO] 集群: trader-cluster
[2026-01-22 15:35:42] [SUCCESS] 数据准备任务完成！
```

#### 日志位置
```
/mnt/efs/logs/
├── scheduler/
│   ├── aws_ecs_run_20260122_093000.log
│   ├── aws_ecs_run_20260122_153000.log
│   └── ...
└── agent_data_astock/
    └── (Agent 执行日志)
```

---

### 4. 新增测试脚本 ([test_efs_mounts.sh](file:///home/ec2-user/AI-Trader/scripts/test_efs_mounts.sh))

#### 功能
- 验证所有 EFS 挂载点是否正确
- 检查工具依赖（AWS CLI、jq、bash）
- 测试配置文件路径解析逻辑
- 检查环境变量配置
- 验证日志目录写权限

#### 使用方法
```bash
# 在容器内执行
docker exec trader-frontend test_efs_mounts.sh

# 或者从宿主机执行
docker exec trader-frontend /bin/sh /usr/local/bin/test_efs_mounts.sh
```

#### 测试输出示例
```
==========================================
EFS 挂载点测试
==========================================

==========================================
1. 配置文件挂载点
==========================================
测试: 配置文件目录 ... ✓ 存在

可用的配置文件:
  - /mnt/efs/configs/astock_config_hourly.json
  - /mnt/efs/configs/astock_config.json

==========================================
2. 数据目录挂载点
==========================================
测试: 数据目录 (EFS) ... ✓ 存在
测试: 数据目录 (Nginx) ... ✓ 存在

==========================================
3. 日志目录挂载点
==========================================
测试: 日志目录 ... ✓ 存在
测试日志目录写权限 ... ✓ 可写

==========================================
5. 工具和脚本检查
==========================================
AWS CLI ... ✓ 已安装 (aws-cli/2.x.x)
jq ... ✓ 已安装 (jq-1.x)
bash ... ✓ 已安装 (GNU bash, version 5.x)
调度脚本 ... ✓ 存在
.env 环境变量文件 ... ✓ 存在

==========================================
6. 配置文件路径解析测试
==========================================
输入: configs/astock_config_hourly.json
  ✓ 解析成功: /mnt/efs/configs/astock_config_hourly.json

输入: astock_config_hourly.json
  ✓ 解析成功: /mnt/efs/configs/astock_config_hourly.json

==========================================
测试完成
==========================================
```

---

### 5. Dockerfile.frontend 更新

#### 新增内容
- 复制测试脚本到镜像
- 设置脚本执行权限

```dockerfile
# Copy orchestration scripts
COPY scripts/aws_ecs_run_all.sh /usr/local/bin/aws_ecs_run_all.sh
COPY scripts/test_efs_mounts.sh /usr/local/bin/test_efs_mounts.sh
RUN chmod +x /usr/local/bin/aws_ecs_run_all.sh /usr/local/bin/test_efs_mounts.sh
```

---

## 📊 挂载路径映射表

| 用途 | 容器内路径 | EFS 路径 | 权限 | 说明 |
|------|-----------|---------|------|------|
| **配置文件** | `/mnt/efs/configs` | `/ai-trader/configs` | 只读 | 脚本读取交易配置 |
| **数据目录（Nginx）** | `/usr/share/nginx/html/data` | `/ai-trader/data` | 读写 | Web UI 展示数据 |
| **日志目录** | `/mnt/efs/logs` | `/ai-trader/logs` | 读写 | Agent 日志 + 调度日志 |

---

## 🎯 脚本执行示例

### 1. 基本用法
```bash
# 使用默认配置
docker exec trader-frontend aws_ecs_run_all.sh

# 指定配置文件（支持多种格式）
docker exec trader-frontend aws_ecs_run_all.sh configs/astock_config_hourly.json
docker exec trader-frontend aws_ecs_run_all.sh astock_config_hourly.json
docker exec trader-frontend aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json

# 回测模式
docker exec trader-frontend aws_ecs_run_all.sh configs/astock_config.json 2025-01-01 2025-01-21
```

### 2. 查看执行日志
```bash
# 查看最新日志
docker exec trader-frontend ls -lt /mnt/efs/logs/scheduler/ | head -5

# 实时查看日志
docker exec trader-frontend tail -f /mnt/efs/logs/scheduler/aws_ecs_run_*.log
```

### 3. 验证挂载配置
```bash
# 运行测试脚本
docker exec trader-frontend test_efs_mounts.sh
```

---

## ⚠️ 注意事项

### 1. 配置文件位置
- **EFS 路径**：配置文件应放在 EFS 的 `/ai-trader/configs/` 目录
- **容器路径**：映射到 `/mnt/efs/configs/`
- **脚本支持**：自动解析多种输入格式，无需担心路径问题

### 2. 日志持久化
- 调度日志自动保存到 `/mnt/efs/logs/scheduler/`
- 文件名包含时间戳，便于追溯
- 日志同时输出到终端和文件

### 3. 静态文件保护
- **已移除**：`/usr/share/nginx/html` 的 EFS 挂载
- **原因**：避免覆盖镜像中的 index.html 等静态文件
- **数据展示**：`/usr/share/nginx/html/data` 仍然挂载 EFS，用于动态数据

### 4. 权限设置
- 配置目录：只读（`readOnly: true`）- 脚本只需读取
- 日志目录：读写（`readOnly: false`）- 需要写入日志
- 数据目录：读写（`readOnly: false`）- Agent 写入，Web UI 读取

---

## 🔧 部署步骤

### 1. 更新 ECS 任务定义
```bash
# 注册新的任务定义
aws ecs register-task-definition \
  --cli-input-json file://configs/task_trader_frontend.json \
  --region us-west-2

# 更新服务（如果已部署）
aws ecs update-service \
  --cluster trader-cluster \
  --service trader-frontend \
  --task-definition trader-frontend:latest \
  --force-new-deployment \
  --region us-west-2
```

### 2. 重新构建镜像
```bash
# 确保 .env 文件已配置
cp .env.example .env
vim .env

# 构建镜像
docker build -f Dockerfile.frontend -t trader-frontend:latest .

# 推送到 ECR
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 648104168728.dkr.ecr.us-west-2.amazonaws.com
docker tag trader-frontend:latest 648104168728.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-frontend:latest
docker push 648104168728.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-frontend:latest
```

### 3. 验证部署
```bash
# 1. 检查任务状态
aws ecs list-tasks --cluster trader-cluster --service-name trader-frontend

# 2. 进入容器测试
TASK_ID=$(aws ecs list-tasks --cluster trader-cluster --service-name trader-frontend --query 'taskArns[0]' --output text)

# 3. 运行测试脚本
aws ecs execute-command \
  --cluster trader-cluster \
  --task $TASK_ID \
  --container trader-frontend \
  --command "test_efs_mounts.sh" \
  --interactive

# 4. 测试脚本执行
aws ecs execute-command \
  --cluster trader-cluster \
  --task $TASK_ID \
  --container trader-frontend \
  --command "aws_ecs_run_all.sh --help" \
  --interactive
```

---

## ✅ 修改总结

| 文件 | 修改内容 | 影响 |
|------|---------|------|
| [task_trader_frontend.json](file:///home/ec2-user/AI-Trader/configs/task_trader_frontend.json) | 移除 `/usr/share/nginx/html` 挂载<br>配置目录改为只读 | ✅ 保护静态文件<br>✅ 提高安全性 |
| [aws_ecs_run_all.sh](file:///home/ec2-user/AI-Trader/scripts/aws_ecs_run_all.sh) | 智能路径解析<br>日志持久化 | ✅ 支持多种路径格式<br>✅ 调度日志可追溯 |
| [test_efs_mounts.sh](file:///home/ec2-user/AI-Trader/scripts/test_efs_mounts.sh) | 新增测试脚本 | ✅ 快速验证配置 |
| [Dockerfile.frontend](file:///home/ec2-user/AI-Trader/Dockerfile.frontend) | 复制测试脚本 | ✅ 测试工具内置 |

所有修改已完成，配置已针对实际挂载情况优化！
