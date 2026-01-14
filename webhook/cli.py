#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webhook 推送命令行工具
"""

import argparse
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from webhook.dingtalk_webhook import ImmediatePusher, PositionReporter


def send_immediate_report(webhook_url: str, secret: str = None, config_path: str = "./configs/astock_config_hourly.json"):
    """立即发送仓位报告"""
    print("📤 立即发送仓位报告...")
    
    pusher = ImmediatePusher(webhook_url, secret, config_path)
    return pusher.send_report()


def show_report(config_path: str = "./configs/astock_config_hourly.json"):
    """显示仓位报告内容（不发送）"""
    print("📄 显示仓位报告预览...")
    
    reporter = PositionReporter(config_path)
    messages = reporter.generate_report()
    
    print("\n" + "="*50)
    print("仓位报告预览")
    print("="*50)
    
    for msg in messages:
        print(msg)
        print("-" * 30)


def main():
    parser = argparse.ArgumentParser(description="Webhook 推送工具")
    parser.add_argument("action", choices=["send", "show"], 
                       help="执行动作: send(立即发送), show(显示预览)")
    parser.add_argument("--webhook-url", help="钉钉 Webhook URL")
    parser.add_argument("--secret", help="钉钉加签密钥")
    parser.add_argument("--config", default="./configs/astock_config_hourly.json",
                       help="配置文件路径")
    
    args = parser.parse_args()
    
    if args.action == "send":
        if not args.webhook_url:
            print("❌ 发送报告需要提供 --webhook-url 参数")
            sys.exit(1)
        success = send_immediate_report(args.webhook_url, args.secret, args.config)
        sys.exit(0 if success else 1)
    
    elif args.action == "show":
        show_report(args.config)


if __name__ == "__main__":
    main()