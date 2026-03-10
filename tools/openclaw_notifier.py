# coding=utf-8
"""
AI-Trader OpenClaw 通知模块
通过 OpenClaw Gateway 发送交易通知到 DingTalk 单聊
"""

import json
import os
import sys
from typing import Optional
import urllib.request
import urllib.error
from datetime import datetime


class OpenClawNotifier:
    """OpenClaw 消息通知器"""
    
    DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789"
    DEFAULT_TARGET = "agent:main:dingtalk:direct:01443329476136537748"
    
    def __init__(
        self,
        gateway_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
        target: Optional[str] = None
    ):
        self.gateway_url = gateway_url or os.getenv(
            "OPENCLAW_GATEWAY_URL", 
            self.DEFAULT_GATEWAY_URL
        )
        self.gateway_token = gateway_token or os.getenv(
            "OPENCLAW_GATEWAY_TOKEN",
            "0549b991371eada2b8060109e4d79524c81a115c3e6d9e68136fb69411c19760"
        )
        self.target = target or os.getenv(
            "OPENCLAW_TARGET",
            self.DEFAULT_TARGET
        )
    
    def send_message(
        self,
        content: str,
        title: str = "AI-Trader",
        msg_type: str = "markdown"
    ) -> bool:
        """
        发送消息
        
        Args:
            content: 消息内容
            title: 消息标题
            msg_type: 消息类型 (markdown 或 text)
            
        Returns:
            bool: 是否发送成功
        """
        if msg_type == "markdown":
            full_content = f"## {title}\n\n{content}"
        else:
            full_content = f"{title}\n\n{content}"
        
        payload = {
            "target": self.target,
            "message": {
                "type": msg_type,
                "content": full_content
            }
        }
        
        url = f"{self.gateway_url}/api/v1/message"
        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Content-Type": "application/json"
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status in (200, 202):
                    print(f"[OpenClaw] 消息发送成功")
                    return True
                else:
                    print(f"[OpenClaw] 消息发送失败 (HTTP {response.status})")
                    return False
                    
        except Exception as e:
            print(f"[OpenClaw] 发送失败: {e}")
            return False
    
    def send_trade_notification(
        self,
        strategy: str,
        action: str,
        symbol: str,
        quantity: float,
        price: float,
        reason: str = ""
    ) -> bool:
        """
        发送交易执行通知
        
        Args:
            strategy: 策略名称
            action: 操作 (BUY/SELL/HOLD)
            symbol: 交易标的
            quantity: 数量
            price: 价格
            reason: 交易原因
            
        Returns:
            bool: 是否发送成功
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        amount = quantity * price
        
        content = f"""**策略**: {strategy}
**时间**: {timestamp}
**操作**: {action}
**标的**: {symbol}
**数量**: {quantity}
**价格**: ${price:.2f}
**金额**: ${amount:.2f}
**原因**: {reason or "N/A"}
"""
        
        return self.send_message(
            content=content,
            title=f"🤖 交易执行通知 - {action}",
            msg_type="markdown"
        )
    
    def send_daily_report(
        self,
        strategy: str,
        portfolio_value: float,
        cash: float,
        positions: dict,
        pnl: float = 0.0
    ) -> bool:
        """
        发送每日持仓报告
        
        Args:
            strategy: 策略名称
            portfolio_value: 组合总价值
            cash: 现金
            positions: 持仓字典
            pnl: 当日盈亏
            
        Returns:
            bool: 是否发送成功
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建持仓列表
        pos_lines = []
        for symbol, qty in positions.items():
            pos_lines.append(f"- {symbol}: {qty}")
        
        pos_str = "\n".join(pos_lines) if pos_lines else "- 无持仓"
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        
        content = f"""**策略**: {strategy}
**时间**: {timestamp}

**组合价值**: ${portfolio_value:.2f}
**现金**: ${cash:.2f}
**当日盈亏**: {pnl_emoji} ${pnl:.2f}

**持仓**:
{pos_str}
"""
        
        return self.send_message(
            content=content,
            title="📊 每日持仓报告",
            msg_type="markdown"
        )


# 全局通知器实例
_notifier: Optional[OpenClawNotifier] = None


def get_notifier() -> OpenClawNotifier:
    """获取全局通知器实例"""
    global _notifier
    if _notifier is None:
        _notifier = OpenClawNotifier()
    return _notifier


def send_trade_notification(*args, **kwargs) -> bool:
    """快捷函数：发送交易通知"""
    return get_notifier().send_trade_notification(*args, **kwargs)


def send_daily_report(*args, **kwargs) -> bool:
    """快捷函数：发送每日报告"""
    return get_notifier().send_daily_report(*args, **kwargs)


def send_message(*args, **kwargs) -> bool:
    """快捷函数：发送自定义消息"""
    return get_notifier().send_message(*args, **kwargs)


if __name__ == "__main__":
    # 测试
    print("测试 OpenClaw 通知模块...")
    notifier = OpenClawNotifier()
    
    # 测试普通消息
    notifier.send_message("这是测试消息", "测试")
    
    # 测试交易通知
    notifier.send_trade_notification(
        strategy="test-strategy",
        action="BUY",
        symbol="AAPL",
        quantity=100,
        price=150.0,
        reason="测试交易通知"
    )
