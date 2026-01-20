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
import asyncio
import pandas as pd

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


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


class PositionReporter:
    """仓位报告生成器"""
    
    def __init__(self, config_path: str = "./configs/astock_config_hourly.json"):
        """
        初始化仓位报告器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        
        # 根据配置文件确定数据路径
        self.base_data_path = PROJECT_ROOT / "data" / "agent_data_astock"
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                market = config.get("market", "cn")
                agent_type = config.get("agent_type", "")
                
                if market == "crypto" or agent_type == "BaseAgentCrypto":
                    self.base_data_path = PROJECT_ROOT / "data" / "agent_data_crypto"
                elif market == "us":
                    self.base_data_path = PROJECT_ROOT / "data" / "agent_data"
                else:
                    self.base_data_path = PROJECT_ROOT / "data" / "agent_data_astock"
        except Exception as e:
            print(f"⚠️ 读取配置文件以确定数据路径失败: {e}，将使用默认路径")
            
        self.stock_name_map = self._load_stock_name_mapping()
    
    def _load_stock_name_mapping(self) -> Dict[str, str]:
        """
        加载股票代码到中文名称的映射
        
        Returns:
            股票代码到名称的字典映射
        """
        mapping = {}
        csv_path = PROJECT_ROOT / "data" / "A_stock" / "sse_pick.csv"
        
        if not csv_path.exists():
            print(f"⚠️ 股票名称映射文件不存在: {csv_path}")
            return mapping
        
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
            for _, row in df.iterrows():
                code = row['con_code']
                name = row['stock_name']
                mapping[code] = name
        except Exception as e:
            print(f"❌ 读取股票名称映射文件失败: {e}")
        
        return mapping
    
    def _get_stock_display_name(self, stock_code: str) -> str:
        """
        获取股票的显示名称（中文名+代码）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            显示名称，格式为 "中文名(代码)" 或 "代码"
        """
        if stock_code in self.stock_name_map:
            return f"{self.stock_name_map[stock_code]}({stock_code})"
        return stock_code
    
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
    
    def _count_trade_operations(self, signature: str) -> Dict[str, int]:
        """
        统计指定模型的买卖操作次数
        
        Args:
            signature: 模型签名
            
        Returns:
            包含买入和卖出次数的字典 {"buy": count, "sell": count}
        """
        position_file = self.base_data_path / signature / "position" / "position.jsonl"
        
        if not position_file.exists():
            return {"buy": 0, "sell": 0}
        
        buy_count = 0
        sell_count = 0
        
        try:
            with open(position_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            action = record.get("this_action", {}).get("action", "")
                            if action == "buy":
                                buy_count += 1
                            elif action == "sell":
                                sell_count += 1
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"❌ 统计交易操作失败 {position_file}: {e}")
        
        return {"buy": buy_count, "sell": sell_count}
    
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
        
        # 提取现金余额
        cash_balance = positions.get("CASH", 0)
        
        # 提取持仓股票（非零持仓）
        holdings = {k: v for k, v in positions.items() if k != "CASH" and v > 0}
        
        # 统计买卖操作次数
        trade_stats = self._count_trade_operations(signature)
        
        # 格式化消息 - 使用钉钉Markdown换行语法
        message_lines = [
            f"📈 **{signature} 仓位报告**  \n\n",
            f"📅 时间: {date}  \n\n",
            f"💰 现金余额: ¥{cash_balance:,.2f}  \n\n",
            f"📊 交易统计: 买入{trade_stats['buy']}次, 卖出{trade_stats['sell']}次  \n\n",
            "  \n\n"
        ]
        
        if holdings:
            message_lines.append("📦 持仓详情:  \n\n")
            for symbol, amount in sorted(holdings.items()):
                display_name = self._get_stock_display_name(symbol)
                # 每支股票后换行，使格式更美观
                message_lines.append(f"  • {display_name}: {amount:,} 股  \n\n")
        else:
            message_lines.append("📦 当前无持仓  \n\n")
        
        return "".join(message_lines)
    
    def generate_report(self, filter_signature: Optional[str] = None) -> List[str]:
        """
        生成所有启用模型的仓位报告
        
        Args:
            filter_signature: 可选，仅为指定的 signature 生成报告
            
        Returns:
            格式化后的消息列表
        """
        try:
            config = self.load_config()
            enabled_models = [model for model in config.get("models", []) if model.get("enabled", True)]
            
            # 如果指定了 signature，则只保留匹配的
            if filter_signature:
                enabled_models = [model for model in enabled_models if model.get("signature") == filter_signature]
                if not enabled_models:
                    print(f"⚠️ 未在配置中找到启用的 signature: {filter_signature}")
            
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


class ImmediatePusher:
    """立即推送器 - 仅支持即时推送"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None, config_path: str = "./configs/astock_config_hourly.json"):
        """
        初始化推送器
        
        Args:
            webhook_url: 钉钉 Webhook URL
            secret: 钉钉加签密钥
            config_path: 配置文件路径
        """
        self.dingtalk = DingTalkWebhook(webhook_url, secret)
        self.reporter = PositionReporter(config_path)
    
    def send_report(self, signature: Optional[str] = None):
        """
        立即发送仓位报告
        
        Args:
            signature: 可选，仅发送指定 signature 的报告
        """
        print(f"[{datetime.now()}] 开始发送仓位报告...")
        messages = self.reporter.generate_report(filter_signature=signature)
        
        if not messages:
            print("⚠️ 没有可发送的报告")
            return False
        
        # 合并所有消息并在开头添加 position 关键字
        full_message = "position\n\n" + "\n\n---\n\n".join(messages)
        
        # 发送到钉钉
        success = self.dingtalk.send_message(full_message, msg_type="markdown")
        
        if success:
            print("✅ 仓位报告发送完成")
        else:
            print("❌ 仓位报告发送失败")
        
        return success


def send_no_trade_notification(signature: str, today_date: str, positions: Dict[str, Any]):
    """
    发送无交易操作推送通知
    
    Args:
        signature: 模型签名
        today_date: 当前日期
        positions: 仓位数据
    """
    try:
        # 从环境变量获取推送配置
        webhook_url = os.getenv("DINGTALK_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
        secret = os.getenv("DINGTALK_SECRET")
        
        if not webhook_url:
            print("⚠️ 未配置 Webhook URL，跳过推送")
            return
        
        # 创建推送器
        dingtalk = DingTalkWebhook(webhook_url, secret)
        reporter = PositionReporter()
        
        cash_balance = positions.get("CASH", 0)
        
        # 提取持仓股票（非零持仓）
        holdings = {k: v for k, v in positions.items() if k != "CASH" and v > 0}
        
        # 构建消息
        message_lines = [
            f"📈 **{signature} position 无交易通知**  \n\n",
            f"📅 时间: {today_date}  \n\n",
            "  \n\n",
            f"📝 决策建议: 维持当前仓位，无交易操作  \n\n",
            "  \n\n",
            f"💰 当前现金: ¥{cash_balance:,.2f}  \n\n"
        ]
        
        if holdings:
            message_lines.append("📦 当前持仓:  \n\n")
            for symbol, amount in sorted(holdings.items()):
                display_name = reporter._get_stock_display_name(symbol)
                message_lines.append(f"  • {display_name}: {amount:,} 股  \n\n")
        else:
            message_lines.append("📦 当前无持仓  \n\n")
        
        message_content = "".join(message_lines)
        
        # 发送推送
        success = dingtalk.send_message(message_content, msg_type="markdown")
        if success:
            print(f"✅ 无交易推送成功: {signature}")
        else:
            print(f"❌ 无交易推送失败: {signature}")
            
    except Exception as e:
        print(f"❌ 发送无交易推送时出错: {e}")


def main():
    """主函数 - 立即推送示例"""
    # 从环境变量读取配置
    webhook_url = os.getenv("DINGTALK_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
    secret = os.getenv("DINGTALK_SECRET")
    
    if not webhook_url:
        print("❌ 请设置环境变量 DINGTALK_WEBHOOK_URL 或 WEBHOOK_URL")
        return
    
    # 创建推送器
    pusher = ImmediatePusher(webhook_url, secret)
    
    # 立即发送报告
    print("📤 发送即时报告...")
    pusher.send_report()


if __name__ == "__main__":
    main()