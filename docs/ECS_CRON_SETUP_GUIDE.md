# ECS 定时任务配置指南

本文档说明如何在 frontend 容器中配置和使用定时任务来触发 ECS 数据准备和交易任务。

## 📋 概述

Frontend 容器现在包含以下功能：
- **Nginx 静态文件服务**：提供 Web UI
- **ECS 任务编排脚本**：`aws_ecs_run_all.sh` 用于触发数据准备和所有 Agent 任务
- **Crond 定时调度**：自动在交易时间执行任务
- **测试工具**：验证环境和手动触发任务

## 🏗️ 架构说明

```
Frontend 容器 (trader-frontend)
├── Nginx (端口 80/8888) - Web UI 服务
├── Crond - 定时任务调度器
├── 预置脚本 (/usr/local/bin/)
│   ├── aws_ecs_run_all.sh - ECS 任务编排主脚本
│   ├── test_ecs_task_trigger.sh - 测试脚本
│   ├── test_efs_mounts.sh - EFS 挂载验证
│   └── verify_env.sh - 环境变量验证
└── EFS 挂载 (/mnt/efs/)
    ├── configs/ - 配置文件
    ├── data/ - 交易数据
    └── logs/ - 日志文件
```

## ⏰ 定时任务时间表

任务将在以下时间自动执行（中国时间 UTC+8）：

| 时间 | 说明 |
|------|------|
| 周一至周五 10:30 | 市场开盘前数据准备 |
| 周一至周五 11:30 | 上午交易中期 |
| 周一至周五 14:00 | 下午开盘 |
| 周一至周五 15:00 | 收盘前决策 |

> **注意**：周末和节假日不会执行任务。

## 🚀 部署步骤

### 第一步：重新构建镜像

```bash
# 在项目根目录执行
cd /home/ec2-user/AI-Trader

# 确保 .env 文件存在并包含必要的 AWS 凭证
cat .env | grep -E "AWS_|ECS_"

# 构建新的 frontend 镜像
docker build -f Dockerfile.frontend -t trader-frontend:latest .

# 推送到 ECR（替换为你的 ECR 地址）
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/trader-frontend"

# 登录 ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO

# 打标签并推送
docker tag trader-frontend:latest $ECR_REPO:latest
docker tag trader-frontend:latest $ECR_REPO:cron-$(date +%Y%m%d)
docker push $ECR_REPO:latest
docker push $ECR_REPO:cron-$(date +%Y%m%d)
```

### 第二步：更新 ECS 任务定义

如果使用 ECS，需要更新任务定义以使用新镜像并确保环境变量正确配置。

**必需的环境变量**：
```json
{
  "name": "AWS_ACCESS_KEY_ID",
  "value": "YOUR_ACCESS_KEY"
},
{
  "name": "AWS_SECRET_ACCESS_KEY",
  "value": "YOUR_SECRET_KEY"
},
{
  "name": "AWS_REGION",
  "value": "us-west-2"
},
{
  "name": "ECS_CLUSTER",
  "value": "trader-cluster"
},
{
  "name": "ECS_SUBNET",
  "value": "subnet-0307b527137ee17d9"
},
{
  "name": "ECS_SECURITY_GROUP",
  "value": "sg-097cc7fbe296ee446"
}
```

### 第三步：重启容器服务

```bash
# 在 ECS 控制台或 CLI 中强制新部署
aws ecs update-service \
  --cluster trader-cluster \
  --service trader-frontend-service \
  --force-new-deployment \
  --region us-west-2
```

## 🧪 测试验证

### 1. 进入容器

```bash
# 获取容器 ID
docker ps | grep trader-frontend

# 或通过 ECS
TASK_ID=$(aws ecs list-tasks --cluster trader-cluster --service-name trader-frontend-service --query 'taskArns[0]' --output text)
aws ecs execute-command \
  --cluster trader-cluster \
  --task $TASK_ID \
  --container trader-frontend \
  --interactive \
  --command "/bin/bash"
```

### 2. 运行测试脚本

```bash
# 在容器内执行
test_ecs_task_trigger.sh

# 或指定配置文件
test_ecs_task_trigger.sh /mnt/efs/configs/astock_config_hourly.json
```

测试脚本会：
1. ✅ 检查环境和工具
2. ✅ 验证 EFS 挂载
3. ✅ 测试 AWS 认证
4. 🔄 询问是否执行真实任务
5. 📊 执行并记录日志

### 3. 检查 Cron 状态

```bash
# 查看 cron 配置
cat /etc/crontabs/root

# 查看 crond 进程
ps aux | grep crond

# 查看 cron 日志
tail -f /var/log/cron-trader.log

# 手动测试 cron 任务（不等待定时）
/usr/local/bin/aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json
```

### 4. 验证 EFS 挂载

```bash
# 运行 EFS 挂载测试
test_efs_mounts.sh

# 查看配置文件
ls -lh /mnt/efs/configs/

# 查看数据文件
ls -lh /mnt/efs/data/
```

## 📝 日志管理

### 日志位置

| 日志类型 | 路径 | 说明 |
|---------|------|------|
| Cron 执行日志 | `/var/log/cron-trader.log` | 所有定时任务输出 |
| ECS 调度日志 | `/mnt/efs/logs/scheduler/` | 脚本执行详细日志 |
| Nginx 访问日志 | `/var/log/nginx/access.log` | Web UI 访问记录 |
| Nginx 错误日志 | `/var/log/nginx/error.log` | Nginx 错误信息 |

### 查看日志

```bash
# 实时查看 cron 执行日志
tail -f /var/log/cron-trader.log

# 查看最近的调度日志
ls -lt /mnt/efs/logs/scheduler/ | head -5
tail -f /mnt/efs/logs/scheduler/aws_ecs_run_*.log

# 查看 nginx 日志
tail -f /var/log/nginx/access.log
```

### 日志清理

```bash
# 清理旧的调度日志（保留最近 30 天）
find /mnt/efs/logs/scheduler/ -name "aws_ecs_run_*.log" -mtime +30 -delete

# 清理 cron 日志（保留最近 100MB）
tail -c 100M /var/log/cron-trader.log > /var/log/cron-trader.log.tmp
mv /var/log/cron-trader.log.tmp /var/log/cron-trader.log
```

## 🔧 故障排查

### 问题 1：Cron 任务未执行

**检查步骤**：
```bash
# 1. 确认 crond 运行
ps aux | grep crond

# 2. 检查 cron 配置
cat /etc/crontabs/root

# 3. 手动运行脚本测试
/usr/local/bin/aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json

# 4. 查看系统日志
tail -50 /var/log/cron-trader.log
```

**常见原因**：
- Crond 进程未启动
- 时区配置错误
- 脚本权限问题
- 环境变量缺失

### 问题 2：AWS 认证失败

**检查步骤**：
```bash
# 验证 AWS 凭证
aws sts get-caller-identity

# 检查环境变量
env | grep AWS

# 检查 .env 文件
cat /.env | grep AWS
```

**解决方案**：
- 确保 AWS_ACCESS_KEY_ID 和 AWS_SECRET_ACCESS_KEY 正确
- 检查 IAM 权限是否包含 ECS 操作权限
- 验证 AWS_REGION 配置正确

### 问题 3：EFS 挂载失败

**检查步骤**：
```bash
# 测试 EFS 挂载
test_efs_mounts.sh

# 检查挂载点
df -h | grep efs
mount | grep efs

# 检查配置文件
ls -lh /mnt/efs/configs/
```

**解决方案**：
- 确保 ECS 任务定义中配置了 EFS 卷
- 检查安全组是否允许 NFS (端口 2049)
- 验证 EFS 文件系统 ID 正确

### 问题 4：任务启动失败

**检查步骤**：
```bash
# 查看 ECS 集群状态
aws ecs describe-clusters --clusters trader-cluster

# 查看任务定义
aws ecs describe-task-definition --task-definition trader-data-prep
aws ecs describe-task-definition --task-definition trader-agent

# 查看最近的任务失败记录
aws ecs list-tasks --cluster trader-cluster --desired-status STOPPED | head -5
```

**解决方案**：
- 确认 ECS 集群、任务定义、子网、安全组配置正确
- 检查 CloudWatch 日志查看详细错误
- 验证网络配置允许外网访问（拉取数据需要）

## 📊 监控建议

### CloudWatch 告警

建议配置以下 CloudWatch 告警：

1. **任务失败告警**
   - 监控指标：ECS Task Exit Code != 0
   - 触发条件：任何任务失败
   - 通知：SNS 或 Email

2. **Cron 执行告警**
   - 监控指标：CloudWatch Logs
   - 过滤模式：`[ERROR]`
   - 触发条件：日志中出现 ERROR
   - 通知：钉钉 Webhook

3. **容器健康检查**
   - 监控指标：ECS Container Health
   - 触发条件：容器重启超过 3 次/小时
   - 通知：SNS

### 手动监控命令

```bash
# 查看当前运行的任务
aws ecs list-tasks --cluster trader-cluster --desired-status RUNNING

# 查看任务详情
aws ecs describe-tasks --cluster trader-cluster --tasks <TASK_ARN>

# 查看 CloudWatch 日志
aws logs tail /ecs/trader-data-prep --follow
aws logs tail /ecs/trader-agent --follow --filter-pattern "ERROR"
```

## 🔄 修改定时任务

如果需要修改执行时间，需要重新构建镜像：

1. 编辑 `Dockerfile.frontend` 中的 cron 配置：

```dockerfile
# 示例：修改为每天 9:00 和 15:00 执行
RUN echo '0 9 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json >> /var/log/cron-trader.log 2>&1' >> /etc/crontabs/root && \
    echo '0 15 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json >> /var/log/cron-trader.log 2>&1' >> /etc/crontabs/root
```

2. 重新构建并部署镜像（参考部署步骤）

## 📚 相关文档

- [AWS ECS 配置指南](../AWS_ECS_CONFIGURATION.md)
- [ECS 工作流说明](../AWS_STEP_FUNCTIONS_WORKFLOW.json)
- [配置文件指南](../CONFIG_GUIDE.md)

## ⚠️ 注意事项

1. **时区配置**：容器已配置为 Asia/Shanghai 时区，cron 时间为中国时间
2. **网络依赖**：任务需要访问外网（获取数据）和 AWS API
3. **成本考虑**：每次执行会启动多个 Fargate 任务，请关注 AWS 成本
4. **配置变更**：修改 `/mnt/efs/configs/` 中的配置文件会在下次执行时生效
5. **日志管理**：定期清理日志文件避免占用过多存储空间
6. **安全性**：.env 文件包含敏感信息，确保权限正确设置

## 🆘 获取帮助

如有问题，请检查：
1. 📖 本文档的故障排查章节
2. 📝 CloudWatch 日志
3. 📋 /var/log/cron-trader.log
4. 🔍 EFS 挂载状态

---

**最后更新**：2026-01-22
