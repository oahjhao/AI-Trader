#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
钉钉机器人 Webhook 推送模块
支持定时推送 A 股小时级仓位信息
"""

import os
import json
import hashlib
import hmac
import base64
import time
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import requests
import schedule
import asyncio
import pandas as pd


class DingTalkWebhook:
    """钉钉机器人 Webhook 客户端"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        """
        初始化钉钉 Webhook 客户端
        
        Args:
            webhook_url: 钉钉机器人的 Webhook URL
            secret: 钉钉机器人的加签密钥 (可选)
        """
        self.webhook_url = webhook_url
        self.secret = secret
    
    def _gen_sign(self, timestamp: int) -> str:
        """
        生成签名
        
        Args:
            timestamp: 时间戳
            
        Returns:
            签名字符串
        """
        if not self.secret:
            return ""
        
        string_to_sign = f'{timestamp}\n{self.secret}'
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign
    
    def send_message(self, content: str, msg_type: str = "text") -> bool:
        """
        发送消息到钉钉群
        
        Args:
            content: 消息内容
            msg_type: 消息类型 ("text", "markdown")
            
        Returns:
            是否发送成功
        """
        try:
            timestamp = int(round(time.time() * 1000))
            
            payload = {
                "msgtype": msg_type,
                "timestamp": timestamp
            }
            
            if msg_type == "text":
                payload["text"] = {"content": content}
            elif msg_type == "markdown":
                payload["markdown"] = {"title": "仓位报告", "text": content}
            
            # 添加签名
            if self.secret:
                sign = self._gen_sign(timestamp)
                payload["sign"] = sign
            
            headers = {'Content-Type': 'application/json'}
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers=headers,
                timeout=10
            )
            
            result = response.json()
            if result.get("errcode") == 0:
                print("✅ 钉钉消息发送成功")
                return True
            else:
                print(f"❌ 钉钉消息发送失败: {result}")
                return False
                
        except Exception as e:
            print(f"❌ 发送钉钉消息异常: {e}")
            return False


    def format_position_message(self, signature: str, position_data: Dict[str, Any]) -> str:
        """
        格式化仓位信息为推送消息
        
        Args:
            signature: 模型签名
            position_data: 仓位数据
            
        Returns:
            格式化后的消息字符串
        """
        date = position_data.get("date", "未知日期")
        positions = position_data.get("positions", {})
        this_action = position_data.get("this_action", {})
        
        # 提取现金余额
        cash_balance = positions.get("CASH", 0)
        
        # 提取持仓股票（非零持仓）
        holdings = {k: v for k, v in positions.items() if k != "CASH" and v > 0}
        
        # 格式化消息
        message_lines = [
            f"📈 **{signature} 仓位报告**",
            f"📅 时间: {date}",
            f"💰 现金余额: ¥{cash_balance:,.2f}",
            ""
        ]
        
        if holdings:
            message_lines.append("📊 持仓详情:")
            for symbol, amount in sorted(holdings.items()):
                display_name = self._get_stock_display_name(symbol)
                message_lines.append(f"  • {display_name}: {amount:,} 股")
        else:
            message_lines.append("📊 当前无持仓")
        
        # 添加操作信息
        if this_action:
            action = this_action.get("action", "")
            symbol = this_action.get("symbol", "")
            amount = this_action.get("amount", 0)
            if action and symbol:
                action_text = "买入" if action == "buy" else "卖出" if action == "sell" else action
                display_name = self._get_stock_display_name(symbol)
                message_lines.append("")
                message_lines.append(f"📝 最新操作: {action_text} {display_name} {amount:,} 股")
        
        return "\n".join(message_lines)
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def get_latest_position(self, signature: str) -> Optional[Dict[str, Any]]:
        """
        获取指定模型的最新仓位信息
        
        Args:
            signature: 模型签名
            
        Returns:
            最新的仓位记录，如果不存在则返回 None
        """
        position_file = self.base_data_path / signature / "position" / "position.jsonl"
        
        if not position_file.exists():
            print(f"⚠️ 仓位文件不存在: {position_file}")
            return None
        
        latest_record = None
        try:
            with open(position_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            # 更新最新记录（假设文件是按时间顺序写的）
                            latest_record = record
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"❌ 读取仓位文件失败 {position_file}: {e}")
            return None
        
        return latest_record
    
    def format_position_message(self, signature: str, position_data: Dict[str, Any]) -> str:
        """
        格式化仓位信息为推送消息
        
        Args:
            signature: 模型签名
            position_data: 仓位数据
            
        Returns:
            格式化后的消息字符串
        """
        date = position_data.get("date", "未知日期")
        positions = position_data.get("positions", {})
        this_action = position_data.get("this_action", {})
        
        # 提取现金余额
        cash_balance = positions.get("CASH", 0)
        
        # 提取持仓股票（非零持仓）
        holdings = {k: v for k, v in positions.items() if k != "CASH" and v > 0}
        
        # 格式化消息
        message_lines = [
            f"📈 **{signature} 仓位报告**",
            f"📅 时间: {date}",
            f"💰 现金余额: ¥{cash_balance:,.2f}",
            ""
        ]
        
        if holdings:
            message_lines.append("📊 持仓详情:")
            for symbol, amount in sorted(holdings.items()):
                message_lines.append(f"  • {symbol}: {amount:,} 股")
        else:
            message_lines.append("📊 当前无持仓")
        
        # 添加操作信息
        if this_action:
            action = this_action.get("action", "")
            symbol = this_action.get("symbol", "")
            amount = this_action.get("amount", 0)
            if action and symbol:
                action_text = "买入" if action == "buy" else "卖出" if action == "sell" else action
                message_lines.append("")
                message_lines.append(f"📝 最新操作: {action_text} {symbol} {amount:,} 股")
        
        return "\n".join(message_lines)
    
    def generate_report(self) -> List[str]:
        """
        生成所有启用模型的仓位报告
        
        Returns:
            格式化后的消息列表
        """
        try:
            config = self.load_config()
            enabled_models = [model for model in config.get("models", []) if model.get("enabled", True)]
            
            messages = []
            for model in enabled_models:
                signature = model.get("signature")
                if not signature:
                    continue
                
                position_data = self.get_latest_position(signature)
                if position_data:
                    message = self.format_position_message(signature, position_data)
                    messages.append(message)
                else:
                    messages.append(f"⚠️ {signature}: 无仓位数据")
            
            return messages
            
        except Exception as e:
            print(f"❌ 生成报告失败: {e}")
            return [f"❌ 报告生成失败: {str(e)}"]


class WebhookScheduler:
    """Webhook 定时调度器"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None, config_path: str = "./configs/astock_config_hourly.json"):
        """
        初始化调度器
        
        Args:
            webhook_url: 钉钉 Webhook URL
            secret: 钉钉加签密钥
            config_path: 配置文件路径
        """
        self.dingtalk = DingTalkWebhook(webhook_url, secret)
        self.reporter = PositionReporter(config_path)
        self.is_running = False
    
    def send_report(self):
        """发送仓位报告"""
        print(f"[{datetime.now()}] 开始发送仓位报告...")
        messages = self.reporter.generate_report()
        
        if not messages:
            print("⚠️ 没有可发送的报告")
            return
        
        # 合并所有消息
        full_message = "\n\n---\n\n".join(messages)
        
        # 发送到钉钉
        success = self.dingtalk.send_message(full_message, msg_type="markdown")
        
        if success:
            print("✅ 仓位报告发送完成")
        else:
            print("❌ 仓位报告发送失败")
    
    def schedule_daily(self, time_str: str = "15:00"):
        """
        设置每日定时任务
        
        Args:
            time_str: 执行时间，格式 "HH:MM"
        """
        schedule.every().day.at(time_str).do(self.send_report)
        print(f"✅ 已设置每日 {time_str} 发送仓位报告")
    
    def schedule_weekdays(self, time_str: str = "15:00"):
        """
        设置工作日定时任务
        
        Args:
            time_str: 执行时间，格式 "HH:MM"
        """
        schedule.every().monday.at(time_str).do(self.send_report)
        schedule.every().tuesday.at(time_str).do(self.send_report)
        schedule.every().wednesday.at(time_str).do(self.send_report)
        schedule.every().thursday.at(time_str).do(self.send_report)
        schedule.every().friday.at(time_str).do(self.send_report)
        print(f"✅ 已设置工作日 {time_str} 发送仓位报告")
    
    def run_scheduler(self):
        """运行调度器"""
        print("🚀 启动 Webhook 调度器...")
        self.is_running = True
        
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 正在停止调度器...")
            self.is_running = False
        except Exception as e:
            print(f"❌ 调度器运行异常: {e}")
            self.is_running = False


def main():
    """主函数 - 示例用法"""
    # 从环境变量读取配置
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL")
    secret = os.getenv("DINGTALK_SECRET")
    schedule_time = os.getenv("REPORT_SCHEDULE_TIME", "15:00")
    schedule_type = os.getenv("REPORT_SCHEDULE_TYPE", "weekdays")  # daily 或 weekdays
    
    if not webhook_url:
        print("❌ 请设置环境变量 DINGTALK_WEBHOOK_URL")
        return
    
    # 创建调度器
    scheduler = WebhookScheduler(webhook_url, secret)
    
    # 设置定时任务
    if schedule_type == "daily":
        scheduler.schedule_daily(schedule_time)
    else:
        scheduler.schedule_weekdays(schedule_time)
    
    # 立即发送一次测试报告
    print("📤 发送测试报告...")
    scheduler.send_report()
    
    # 运行调度器
    scheduler.run_scheduler()


if __name__ == "__main__":
    main()