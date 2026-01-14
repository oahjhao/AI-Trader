# Webhook 推送模块使用说明

## 功能介绍

该模块实现了定时向钉钉群推送 A 股小时级仓位信息的功能，支持：

- ✅ 自动读取 `astock_config_hourly.json` 中配置的所有启用模型
- ✅ 从每个模型的 `position/position.jsonl` 文件中获取最新仓位信息
- ✅ 将多个模型的仓位信息聚合为一条消息推送
- ✅ 支持可配置的推送时间（每日或仅工作日）
- ✅ 支持钉钉机器人加签验证
- ✅ 提供命令行工具便于测试和使用

## 目录结构

```
webhook/
├── dingtalk_webhook.py    # 核心推送模块
├── cli.py                 # 命令行工具
└── README.md             # 使用说明

configs/
└── webhook_config.json    # Webhook 配置文件示例
```

## 快速开始

### 1. 配置钉钉机器人

1. 在钉钉群中添加自定义机器人
2. 获取 Webhook URL 和加签密钥（Secret）
3. 可选：设置安全验证（IP白名单或加签）

### 2. 设置环境变量

方法一：使用环境变量（推荐）
```bash
export DINGTALK_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
export DINGTALK_SECRET="YOUR_SECRET_KEY"  # 可选
export REPORT_SCHEDULE_TIME="15:00"       # 推送时间
export REPORT_SCHEDULE_TYPE="weekdays"    # daily 或 weekdays
```

方法二：修改配置文件
编辑 `configs/webhook_config.json`：
```json
{
  "dingtalk": {
    "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
    "secret": "YOUR_SECRET_KEY"
  },
  "schedule": {
    "type": "weekdays",
    "time": "15:00"
  }
}
```

### 3. 安装依赖

```bash
pip3 install requests schedule
```

### 4. 使用命令行工具

#### 预览报告内容（不发送）
```bash
python3 webhook/cli.py show
```

#### 立即发送报告
```bash
python3 webhook/cli.py send --webhook-url "YOUR_WEBHOOK_URL"
```

#### 启动定时服务
```bash
# 工作日 15:00 推送（默认）
python3 webhook/cli.py schedule --webhook-url "YOUR_WEBHOOK_URL"

# 每日 09:30 推送
python3 webhook/cli.py schedule --webhook-url "YOUR_WEBHOOK_URL" --time "09:30" --type "daily"
```

### 5. 使用启动脚本

```bash
./scripts/start_webhook.sh
```

## 命令行参数详解

### 基本命令
```bash
python3 webhook/cli.py {send|show|schedule} [选项]
```

### 参数说明

**必选参数：**
- `send`: 立即发送报告
- `show`: 显示报告预览（不发送）
- `schedule`: 启动定时推送服务

**可选参数：**
- `--webhook-url URL`: 钉钉 Webhook URL
- `--secret SECRET`: 钉钉加签密钥
- `--config PATH`: 配置文件路径（默认：`./configs/astock_config_hourly.json`）
- `--time HH:MM`: 推送时间（默认：`15:00`）
- `--type {daily,weekdays}`: 推送频率（默认：`weekdays`）

## 报告格式示例

推送的消息格式如下：

```
📈 DS_pick_nuts_260112 仓位报告
📅 时间: 2026-01-14 14:55:00
💰 现金余额: ¥985,600.50

📊 持仓详情:
  • 600036: 1,000 股
  • 600519: 500 股

📝 最新操作: 买入 600036 100 股

---

📈 DS_pick_normal_260112 仓位报告
📅 时间: 2026-01-14 14:55:00
💰 现金余额: ¥992,300.00

📊 持仓详情:
  • 600519: 300 股

📝 最新操作: 卖出 600036 200 股
```

## 定时任务配置

### 工作日推送（推荐）
```bash
python3 webhook/cli.py schedule --webhook-url "YOUR_URL" --type "weekdays" --time "15:00"
```

### 每日推送
```bash
python3 webhook/cli.py schedule --webhook-url "YOUR_URL" --type "daily" --time "09:30"
```

## 故障排除

### 1. Webhook URL 错误
```
❌ 钉钉消息发送失败: {"errcode": 300001, "errmsg": "token is not exist"}
```
**解决方法：** 检查 Webhook URL 是否正确

### 2. 加签验证失败
```
❌ 钉钉消息发送失败: {"errcode": 310001, "errmsg": "signature error"}
```
**解决方法：** 
- 确保提供了正确的 Secret
- 检查服务器时间是否准确

### 3. 权限问题
```
PermissionError: [Errno 13] Permission denied
```
**解决方法：**
```bash
chmod +x scripts/start_webhook.sh
```

### 4. 依赖缺失
```
ModuleNotFoundError: No module named 'requests'
```
**解决方法：**
```bash
pip3 install requests schedule
```

## 最佳实践

1. **安全性**：建议使用加签验证而非 IP 白名单
2. **时间设置**：建议设置在交易时段结束后（如 15:00）
3. **监控**：定期检查推送日志确保服务正常运行
4. **备份**：保留重要的仓位报告记录

## 注意事项

- 该模块会读取 `astock_config_hourly.json` 中所有 `enabled=true` 的模型
- 推送的内容来自各模型目录下的 `position.jsonl` 文件的最后一行
- 定时服务需要保持运行状态才能正常推送
- 建议在生产环境中使用进程管理工具（如 systemd、supervisor）管理服务