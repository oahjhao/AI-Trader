# Frontend 容器定时任务功能 - 更改总结

## 📅 更新日期
2026-01-22

## 🎯 目标
在 Frontend 容器中实现定时任务功能，自动触发 ECS 数据准备和交易 Agent 任务。

## 📝 更改内容

### 1. Dockerfile.frontend 更新

**新增依赖**：
- `dcron` - Alpine Linux 的 cron 守护进程

**新增脚本**：
- `test_ecs_task_trigger.sh` - 用于容器内测试 ECS 任务触发

**新增配置**：
- **Cron 定时任务**（第 43-49 行）：
  - 周一至周五 10:30
  - 周一至周五 11:30
  - 周一至周五 14:00
  - 周一至周五 15:00
  - 配置文件：`/mnt/efs/configs/astock_config_hourly.json`
  - 日志输出：`/var/log/cron-trader.log`

- **Crond 启动脚本**（第 52-56 行）：
  - 位置：`/docker-entrypoint.d/99-start-cron.sh`
  - 功能：在 Nginx 启动时自动启动 crond
  - 日志级别：2（详细）

### 2. 新增文件

#### scripts/test_ecs_task_trigger.sh
- **用途**：容器内手动测试 ECS 任务触发
- **功能**：
  - 检查运行环境（工具、脚本、EFS）
  - 验证 AWS 认证
  - 确认后执行 ECS 任务
  - 记录执行日志

#### scripts/deploy_frontend_with_cron.sh
- **用途**：一键部署带定时任务的 Frontend 容器
- **功能**：
  - 构建 Docker 镜像
  - 验证镜像内容（脚本、cron 配置）
  - 推送到 ECR（可选）
  - 本地测试（可选）
  - 提供 ECS 更新命令

#### docs/ECS_CRON_SETUP_GUIDE.md
- **用途**：完整的部署和使用文档
- **内容**：
  - 架构说明
  - 详细部署步骤
  - 测试验证方法
  - 日志管理
  - 故障排查
  - 监控建议

#### docs/ECS_CRON_QUICK_REFERENCE.md
- **用途**：快速参考卡片
- **内容**：
  - 常用命令速查
  - 测试命令
  - 监控命令
  - 故障排查步骤

## 🏗️ 架构变化

### 之前
```
Frontend 容器
└── Nginx (静态文件服务)
```

### 之后
```
Frontend 容器
├── Nginx (静态文件服务)
├── Crond (定时任务调度)
├── 预置脚本
│   ├── aws_ecs_run_all.sh - ECS 任务编排
│   ├── test_ecs_task_trigger.sh - 测试工具
│   ├── test_efs_mounts.sh - EFS 验证
│   └── verify_env.sh - 环境验证
└── 定时任务
    ├── 10:30 - 数据准备 + 所有 Agent
    ├── 11:30 - 数据准备 + 所有 Agent
    ├── 14:00 - 数据准备 + 所有 Agent
    └── 15:00 - 数据准备 + 所有 Agent
```

## 📋 使用流程

### 快速部署
```bash
# 1. 构建并验证
cd /home/ec2-user/AI-Trader
bash scripts/deploy_frontend_with_cron.sh

# 2. 推送到 ECR（根据提示选择）
# 3. 更新 ECS 服务
aws ecs update-service \
  --cluster trader-cluster \
  --service trader-frontend-service \
  --force-new-deployment \
  --region us-west-2
```

### 容器内测试
```bash
# 进入容器
docker exec -it trader-frontend /bin/bash

# 运行测试（会确认后执行）
test_ecs_task_trigger.sh

# 查看 cron 配置
cat /etc/crontabs/root

# 查看进程
ps aux | grep crond

# 查看日志
tail -f /var/log/cron-trader.log
```

## 🔧 技术细节

### Cron 时区处理
- 容器时区：`Asia/Shanghai` (UTC+8)
- Cron 使用容器本地时区
- 时间配置：`30 10 * * 1-5` = 周一至周五 10:30 CST

### 启动顺序
1. Nginx 官方镜像的 entrypoint 执行
2. 自动运行 `/docker-entrypoint.d/` 中的所有脚本
3. `99-start-cron.sh` 启动 crond（后台模式）
4. Nginx 主进程启动（前台模式）

### 日志管理
- **Cron 日志**：`/var/log/cron-trader.log`（容器内）
- **调度日志**：`/mnt/efs/logs/scheduler/`（EFS 持久化）
- **格式**：时间戳 + 级别 + 消息

### ECS 任务触发流程
```
Cron 触发
  ↓
aws_ecs_run_all.sh
  ↓
1. 读取配置文件（/mnt/efs/configs/astock_config_hourly.json）
  ↓
2. 启动数据准备任务（trader-data-prep）
  ↓
3. 等待数据准备完成
  ↓
4. 并行启动所有启用的 Agent 任务（trader-agent）
  ↓
5. 等待所有 Agent 完成
  ↓
6. 记录结果和日志
```

## ⚠️ 注意事项

1. **环境变量必需**：
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `ECS_CLUSTER`
   - `ECS_SUBNET`
   - `ECS_SECURITY_GROUP`

2. **网络要求**：
   - 容器需要访问 AWS API
   - 安全组需要允许 EFS（端口 2049）
   - ECS 任务需要能访问外网（获取数据）

3. **成本考虑**：
   - 每天执行 4 次（工作日）
   - 每次执行启动 1 个数据准备任务 + N 个 Agent 任务
   - 注意 Fargate 成本

4. **时区一致性**：
   - 所有时间使用 Asia/Shanghai (UTC+8)
   - Cron 配置时间为中国时间

5. **EFS 依赖**：
   - 配置文件必须在 `/mnt/efs/configs/`
   - 修改配置文件会在下次执行时生效
   - 日志持久化到 `/mnt/efs/logs/`

## 🧪 测试检查清单

- [ ] 镜像构建成功
- [ ] 脚本预置到 `/usr/local/bin/`
- [ ] Cron 配置正确写入 `/etc/crontabs/root`
- [ ] Crond 启动脚本可执行
- [ ] 容器启动后 crond 进程运行
- [ ] AWS 认证配置正确
- [ ] EFS 挂载成功
- [ ] 配置文件可访问
- [ ] 手动触发任务成功
- [ ] 日志正常写入

## 📚 相关文档

- [ECS 定时任务完整指南](docs/ECS_CRON_SETUP_GUIDE.md)
- [快速参考卡片](docs/ECS_CRON_QUICK_REFERENCE.md)
- [ECS 配置文档](AWS_ECS_CONFIGURATION.md)
- [AWS ECS 工作流](AWS_STEP_FUNCTIONS_WORKFLOW.json)

## 🔄 后续优化建议

1. **监控告警**：
   - CloudWatch 告警（任务失败、执行超时）
   - 钉钉通知集成

2. **日志轮转**：
   - 定期清理旧日志
   - 日志大小限制

3. **健康检查**：
   - 添加 ECS 任务健康检查
   - 失败自动重试机制

4. **配置动态化**：
   - 从 EFS 读取 cron 配置
   - 支持热更新定时时间

5. **性能优化**：
   - 任务执行时间监控
   - 并发控制优化

---

**维护者**：AI-Trader Team  
**更新日期**：2026-01-22  
**版本**：v1.0
