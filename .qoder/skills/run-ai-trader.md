# AI-Trader 执行脚本使用指南

## 概述

`aws_ecs_run_all.sh` 是 AI-Trader 的统一执行入口脚本，支持 **ECS 云端模式** 和 **本地 Docker 测试模式**。

**脚本位置**：
- EC2 宿主机：`/mnt/efs/ai-trader/scripts/aws_ecs_run_all.sh`
- 代码仓库：`scripts/aws_ecs_run_all.sh`

## 环境变量约束

### 必需环境变量

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `CONFIG_FILE` | 配置文件路径（data-prep 容器） | `configs/astock_config_hourly_260202.json` |
| `DATE_SUFFIX` | 日期后缀，用于数据隔离 | `20260202` |

### 可选环境变量

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `START_DATE` | 开始日期（回测模式） | `2026-02-02` |
| `END_DATE` | 结束日期（回测模式） | `2026-02-09` |

### 关键约束

1. **entrypoint 脚本只从环境变量获取参数**，不支持命令行参数
2. **缺少必需环境变量会导致容器立即退出**（exit 1）
3. `DATE_SUFFIX` 从配置文件名提取，格式 `_YYYYMMDD.json`

## 使用示例

### 1. LIVE 模式（实时交易）

```bash
# 最简形式：只指定配置文件
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json --live

# 指定单个 Agent
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json --live --agent DS_pick_tech_260202
```

### 2. BACKTEST 模式（回测）

```bash
# 指定日期范围
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json 2026-02-02 2026-02-09

# 本地 Docker 测试
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json 2026-02-02 2026-02-09 --local
```

### 3. 跳过数据准备

```bash
# 当数据已就绪时，跳过 data-prep 步骤
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json --local --skip-data-prep --agent DS_pick_tech_260202
```

### 4. ECS 云端执行

```bash
# 默认 ECS 模式（不加 --local）
./aws_ecs_run_all.sh configs/astock_config_hourly_260202.json 2026-02-02 2026-02-09
```

## 命令行选项

| 选项 | 说明 |
|------|------|
| `--local` | 本地 Docker 容器测试模式 |
| `--live` | LIVE 实时交易模式（自动更新 end_date 为当前时间） |
| `--agent SIGNATURE` | 只运行指定的 Agent |
| `--skip-data-prep` | 跳过数据准备步骤 |
| `-h, --help` | 显示帮助信息 |

## 执行流程

```
┌─────────────────────────────────────────┐
│  aws_ecs_run_all.sh                     │
├─────────────────────────────────────────┤
│  1. 解析命令行参数                        │
│  2. 从配置文件名提取 DATE_SUFFIX          │
│  3. 加载 Agent 列表 (enabled=true)       │
├─────────────────────────────────────────┤
│  Step 1: 运行 data-prep 容器             │
│    ├─ 环境变量: CONFIG_FILE, DATE_SUFFIX │
│    ├─ 环境变量: START_DATE, END_DATE     │
│    └─ 等待完成后继续                      │
├─────────────────────────────────────────┤
│  Step 2: 并行运行 trader-agent 容器       │
│    ├─ 环境变量: DATE_SUFFIX              │
│    ├─ 命令参数: config, --signature      │
│    └─ 等待所有 Agent 完成                 │
└─────────────────────────────────────────┘
```

## 配置文件命名规范

配置文件必须包含日期后缀才能正确提取 `DATE_SUFFIX`：

```
configs/astock_config_hourly_260202.json
                             ^^^^^^^^
                             DATE_SUFFIX = 260202
```

## 日志查看

### 本地模式
```bash
# 实时查看容器日志
sudo docker logs -f trader-data-prep-local
sudo docker logs -f trader-agent-DS_pick_tech_260202
```

### ECS 模式
```bash
# CloudWatch 日志
aws logs tail /ecs/trader-data-prep --follow
aws logs tail /ecs/trader-agent --follow --filter-pattern "DS_pick_tech"
```

## 常见问题

### Q: 容器启动后立即退出，日志显示 "Missing required environment variables"
**A**: 检查 `DATE_SUFFIX` 和 `CONFIG_FILE` 环境变量是否正确传递。确保配置文件名包含日期后缀（如 `_260202.json`）。

### Q: 数据文件找不到
**A**: 确认 `DATE_SUFFIX` 与数据文件后缀一致。数据文件命名格式：`merged_daily_260202.jsonl`

### Q: Agent 执行失败但 data-prep 成功
**A**: 检查 CloudWatch 日志中的具体错误信息。可能是 MCP 服务启动超时或 API Key 问题。

## 相关文件

- `scripts/data_preparation_entrypoint.sh` - 数据准备容器入口
- `scripts/container_entrypoint.sh` - Agent 容器入口
- `configs/astock_config_hourly_*.json` - A股小时级配置文件
