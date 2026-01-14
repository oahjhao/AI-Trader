# 交易操作即时推送功能说明

## 功能概述

在 `tool_trade.py` 中的 `buy` 和 `sell` 函数中增加了即时推送功能。每当执行成功的买卖操作后，会立即向钉钉群推送交易通知。

## 推送内容格式

推送消息采用与现有仓位报告相同的格式：

```
📈 **MODEL_SIGNATURE 交易通知**  

📅 时间: 2026-01-14 15:30:00  

💰 现金余额: ¥950,000.00  

  
📝 交易操作:  

  • 买入 平安银行(000001.SZ) 100 股  

  
📊 当前持仓:  

  • 平安银行(000001.SZ): 100 股  
  • 招商银行(600036.SH): 200 股  
```

## 配置要求

### 环境变量配置

需要在 `.env` 文件中配置以下环境变量：

```bash
# 钉钉 Webhook URL（必需）
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN

# 钉钉加签密钥（可选，但推荐）
DINGTALK_SECRET=YOUR_SECRET_KEY
```

### 或者使用通用变量名：

```bash
WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
DINGTALK_SECRET=YOUR_SECRET_KEY
```

## 功能特点

1. **自动触发**：每次成功执行 `buy` 或 `sell` 操作后自动推送
2. **实时通知**：操作完成后立即发送，无需等待
3. **格式统一**：与现有仓位报告保持一致的格式和风格
4. **容错处理**：即使推送失败也不会影响交易操作的正常执行
5. **可选配置**：如果没有配置 Webhook，则静默跳过推送功能

## 技术实现

### 核心函数

`_send_trade_notification()` 函数负责构建和发送推送消息：

```python
def _send_trade_notification(signature: str, action: str, symbol: str, amount: int, position_data: Dict[str, Any]):
    """
    发送交易操作推送通知
    
    Args:
        signature: 模型签名
        action: 操作类型 ("buy" 或 "sell")
        symbol: 股票代码
        amount: 数量
        position_data: 仓位数据
    """
```

### 在 buy/sell 函数中的集成

在 `buy` 和 `sell` 函数的成功执行路径中添加了推送调用：

```python
# buy 函数中
position_record = {
    "date": today_date,
    "id": current_action_id + 1,
    "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
    "positions": new_position,
}
_send_trade_notification(signature, "buy", symbol, amount, position_record)

# sell 函数中
position_record = {
    "date": today_date,
    "id": current_action_id + 1,
    "this_action": {"action": "sell", "symbol": symbol, "amount": amount},
    "positions": new_position,
}
_send_trade_notification(signature, "sell", symbol, amount, position_record)
```

## 测试验证

可以通过以下方式测试推送功能：

```bash
# 运行测试脚本
python3 test_trade_push.py
```

## 注意事项

1. **依赖关系**：需要确保 `webhook/dingtalk_webhook.py` 文件存在且可导入
2. **网络要求**：需要能够访问钉钉 Webhook 服务
3. **权限配置**：钉钉机器人需要有相应的发送消息权限
4. **关键词设置**：如果钉钉机器人设置了关键词过滤，推送内容需要包含相应关键词

## 故障排除

### 常见错误及解决方案

1. **"推送通知模块不可用"**
   - 确保 `webhook/dingtalk_webhook.py` 文件存在
   - 检查 Python 路径配置

2. **"未配置 Webhook URL"**
   - 检查 `.env` 文件中的 `DINGTALK_WEBHOOK_URL` 或 `WEBHOOK_URL` 配置

3. **"钉钉消息发送失败"**
   - 检查 Webhook URL 是否正确
   - 验证加签密钥是否正确
   - 确认网络连接正常
   - 检查钉钉机器人权限设置

4. **推送内容格式问题**
   - 确保股票代码映射文件存在（用于显示中文名称）
   - 检查 Markdown 格式是否正确