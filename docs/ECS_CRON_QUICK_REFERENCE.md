# ECS 定时任务快速参考

## 🚀 快速开始

```bash
# 1. 构建并部署
cd /home/ec2-user/AI-Trader
bash scripts/deploy_frontend_with_cron.sh

# 2. 更新 ECS 服务
aws ecs update-service \
  --cluster trader-cluster \
  --service trader-frontend-service \
  --force-new-deployment \
  --region us-west-2
```

## ⏰ 定时执行时间

| 时间 | 说明 |
|------|------|
| 10:30 | 市场开盘前 |
| 11:30 | 上午交易中期 |
| 14:00 | 下午开盘 |
| 15:00 | 收盘前决策 |

> 周一至周五执行，周末自动跳过

## 🧪 容器内测试命令

```bash
# 进入容器
docker exec -it trader-frontend /bin/bash

# 或 ECS
aws ecs execute-command \
  --cluster trader-cluster \
  --task <TASK_ID> \
  --container trader-frontend \
  --interactive \
  --command "/bin/bash"

# 运行测试（会询问确认后才执行真实任务）
test_ecs_task_trigger.sh

# 手动执行任务（立即执行）
/usr/local/bin/aws_ecs_run_all.sh /mnt/efs/configs/astock_config_hourly.json

# 查看 cron 配置
cat /etc/crontabs/root

# 查看 cron 进程
ps aux | grep crond

# 实时查看日志
tail -f /var/log/cron-trader.log
```

## 📊 监控命令

```bash
# 查看 ECS 运行中的任务
aws ecs list-tasks --cluster trader-cluster --desired-status RUNNING

# 查看 CloudWatch 日志
aws logs tail /ecs/trader-data-prep --follow
aws logs tail /ecs/trader-agent --follow

# 查看调度日志
ls -lt /mnt/efs/logs/scheduler/
tail -f /mnt/efs/logs/scheduler/aws_ecs_run_*.log
```

## 🔧 故障排查

```bash
# 1. 检查 crond 运行
ps aux | grep crond

# 2. 验证 AWS 认证
aws sts get-caller-identity

# 3. 测试 EFS 挂载
test_efs_mounts.sh
ls -lh /mnt/efs/configs/

# 4. 查看最近错误
tail -50 /var/log/cron-trader.log | grep ERROR
```

## 📝 日志位置

| 类型 | 路径 |
|------|------|
| Cron 日志 | `/var/log/cron-trader.log` |
| 调度日志 | `/mnt/efs/logs/scheduler/` |
| Nginx 日志 | `/var/log/nginx/` |

## 🔄 修改定时时间

编辑 `Dockerfile.frontend` 第 40-43 行，然后重新构建部署：

```dockerfile
# 示例：改为 9:00 和 15:00
echo '0 9 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh ...' >> /etc/crontabs/root
echo '0 15 * * 1-5 /usr/local/bin/aws_ecs_run_all.sh ...' >> /etc/crontabs/root
```

## 📚 相关文件

- **详细文档**: [docs/ECS_CRON_SETUP_GUIDE.md](ECS_CRON_SETUP_GUIDE.md)
- **部署脚本**: [scripts/deploy_frontend_with_cron.sh](../scripts/deploy_frontend_with_cron.sh)
- **测试脚本**: [scripts/test_ecs_task_trigger.sh](../scripts/test_ecs_task_trigger.sh)
- **编排脚本**: [scripts/aws_ecs_run_all.sh](../scripts/aws_ecs_run_all.sh)

## ⚠️ 注意事项

1. **成本控制**：每次执行启动多个 Fargate 任务，注意 AWS 账单
2. **时区配置**：容器时区为 Asia/Shanghai (UTC+8)
3. **网络依赖**：需要访问外网和 AWS API
4. **配置生效**：修改 `/mnt/efs/configs/` 下次执行时生效

---

📖 完整文档: [docs/ECS_CRON_SETUP_GUIDE.md](ECS_CRON_SETUP_GUIDE.md)
