#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 消息推送客户端

通过 OpenClaw CLI 发送钉钉消息，替代直接使用 Webhook
容器内运行时会自动跳过（因为容器内没有 openclaw CLI）
"""

import subprocess
import os
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path

# 钉钉用户 ID（郝海皎）
DINGTALK_USER_ID = os.getenv("DINGTALK_USER_ID", "01443329476136537748")


def _is_in_container() -> bool:
    """检测是否在容器内运行"""
    # 检查 Docker 特征文件
    if Path("/.dockerenv").exists():
        return True
    # 检查 cgroup
    try:
        with open("/proc/1/cgroup", "r") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except:
        pass
    return False


def _openclaw_available() -> bool:
    """检查 openclaw 命令是否可用"""
    return shutil.which("openclaw") is not None


def send_notification(message: str, user_id: str = None) -> bool:
    """
    通过 OpenClaw CLI 发送钉钉消息
    
    Args:
        message: 消息内容
        user_id: 钉钉用户 ID，默认使用环境变量
    
    Returns:
        bool: 发送是否成功
    """
    # 容器内或 openclaw 不可用时，跳过通知
    if _is_in_container() or not _openclaw_available():
        print(f"📨 [容器内跳过通知] {message[:50]}...")
        return True  # 返回 True 避免上层报错
    
    target = user_id or DINGTALK_USER_ID
    
    try:
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "dingtalk",
             "--target", target,
             "--message", message],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True
        else:
            print(f"⚠️ 消息发送失败: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⚠️ 消息发送超时")
        return False
    except FileNotFoundError:
        print("⚠️ openclaw 命令未找到")
        return False
    except Exception as e:
        print(f"⚠️ 消息发送异常: {e}")
        return False


def send_agent_start_notification(
    signature: str,
    market: str,
    init_date: str,
    end_date: str,
    stock_count: int = 0,
    basemodel: str = "deepseek-chat"
) -> bool:
    """
    发送 Agent 启动通知
    """
    market_name = "A股" if market == "cn" else "美股"
    
    message = f"""🚀 AI-Trader Agent 启动

📌 签名: {signature}
🌍 市场: {market_name}
📅 日期范围: {init_date} ~ {end_date}
📊 股票数量: {stock_count}
🤖 模型: {basemodel}
⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    return send_notification(message)


def send_no_trade_notification(
    signature: str,
    today_date: str,
    market: str = "cn"
) -> bool:
    """
    发送无交易通知
    """
    market_name = "A股" if market == "cn" else "美股"
    
    message = f"""📭 无交易日报告

📌 签名: {signature}
🌍 市场: {market_name}
📅 日期: {today_date}
💤 今日无交易信号"""
    
    return send_notification(message)


def send_session_position_report(
    signature: str,
    today_date: str,
    positions: list = None,
    cash: float = 0,
    total_value: float = 0,
    market: str = "cn"
) -> bool:
    """
    发送持仓报告
    """
    market_name = "A股" if market == "cn" else "美股"
    positions = positions or []
    
    position_str = ""
    if positions:
        for p in positions[:5]:  # 最多显示5个
            symbol = p.get("symbol", "N/A")
            qty = p.get("quantity", 0)
            price = p.get("current_price", 0)
            pnl = p.get("unrealized_pnl", 0)
            position_str += f"\n  • {symbol}: {qty}股 @ ¥{price:.2f} (盈亏: ¥{pnl:.2f})"
        if len(positions) > 5:
            position_str += f"\n  ... 及其他 {len(positions) - 5} 个持仓"
    else:
        position_str = "\n  空仓"
    
    message = f"""📊 持仓日报

📌 签名: {signature}
🌍 市场: {market_name}
📅 日期: {today_date}

💰 现金: ¥{cash:,.2f}
📈 总资产: ¥{total_value:,.2f}

📦 持仓明细:{position_str}"""
    
    return send_notification(message)


class ImmediatePusher:
    """
    即时消息推送器
    用于在交易执行时立即发送通知
    """
    
    def __init__(self, signature: str, market: str = "cn"):
        self.signature = signature
        self.market = market
        self.market_name = "A股" if market == "cn" else "美股"
    
    def push_trade(
        self,
        action: str,
        symbol: str,
        quantity: int,
        price: float,
        reason: str = ""
    ) -> bool:
        """推送交易通知"""
        action_emoji = "🔴" if action.lower() == "sell" else "🟢"
        action_text = "卖出" if action.lower() == "sell" else "买入"
        
        message = f"""{action_emoji} 交易执行

📌 签名: {self.signature}
🌍 市场: {self.market_name}

{action_text} {symbol}
📊 数量: {quantity}股
💵 价格: ¥{price:.2f}
💰 金额: ¥{quantity * price:,.2f}

📝 原因: {reason or '策略信号'}
⏰ 时间: {datetime.now().strftime('%H:%M:%S')}"""
        
        return send_notification(message)
    
    def push_error(self, error_msg: str) -> bool:
        """推送错误通知"""
        message = f"""❌ 交易错误

📌 签名: {self.signature}
🌍 市场: {self.market_name}

⚠️ 错误信息:
{error_msg}

⏰ 时间: {datetime.now().strftime('%H:%M:%S')}"""
        
        return send_notification(message)


class PositionReporter:
    """
    持仓报告器
    用于定期发送持仓汇总
    """
    
    def __init__(self, signature: str, market: str = "cn"):
        self.signature = signature
        self.market = market
    
    def send_daily_report(
        self,
        today_date: str,
        positions: list = None,
        cash: float = 0,
        total_value: float = 0
    ) -> bool:
        """发送日报"""
        return send_session_position_report(
            signature=self.signature,
            today_date=today_date,
            positions=positions,
            cash=cash,
            total_value=total_value,
            market=self.market
        )
