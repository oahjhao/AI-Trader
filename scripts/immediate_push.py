#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即时推送脚本
立即执行钉钉推送
使用 .env 中的配置变量
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / '.env')

def get_python_executable():
    """获取Python可执行文件路径（支持虚拟环境和容器环境）"""
    # 优先使用当前运行的 Python 解释器
    if sys.executable:
        return sys.executable
        
    # 回退逻辑
    venv_path = project_root / 'venv'
    if os.name == 'nt':  # Windows
        python_exe = venv_path / 'Scripts' / 'python.exe'
    else:  # Linux/Mac
        python_exe = venv_path / 'bin' / 'python3'
    
    if python_exe.exists():
        return str(python_exe)
        
    # 最后尝试直接使用 python3 或 python
    return "python3" if os.name != 'nt' else "python"

def send_push_notification(config_path=None, signature=None):
    """发送即时推送通知"""
    print(f"[{datetime.now()}] 开始执行即时推送...")
    
    try:
        # 获取配置
        webhook_url = os.getenv("DINGTALK_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
        if not webhook_url:
            print("❌ 未配置 Webhook URL，请在 .env 文件中设置 DINGTALK_WEBHOOK_URL 或 WEBHOOK_URL")
            return False
        
        secret = os.getenv("DINGTALK_SECRET")
        
        # 构建命令
        python_exe = get_python_executable()
        cmd = [
            python_exe,
            str(project_root / "webhook" / "cli.py"),
            "send",
            "--webhook-url", webhook_url
        ]
        
        if secret:
            cmd.extend(["--secret", secret])
        
        if config_path:
            cmd.extend(["--config", config_path])
            
        if signature:
            cmd.extend(["--signature", signature])
        
        # 执行推送
        print(f"📤 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root))
        
        if result.returncode == 0:
            print("✅ 即时推送成功")
            if result.stdout:
                print(f"输出: {result.stdout}")
            return True
        else:
            print("❌ 即时推送失败")
            print(f"错误: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 执行即时推送时发生异常: {e}")
        return False


def prepare_push_content():
    """准备推送内容（检查配置）"""
    try:
        # 检查必要配置是否存在
        webhook_url = os.getenv("DINGTALK_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
        if not webhook_url:
            print("❌ 未配置 Webhook URL")
            return False
        
        print("✅ 推送配置检查通过")
        return True
            
    except Exception as e:
        print(f"❌ 检查推送配置时发生异常: {e}")
        return False

# 即时推送不需要定时功能

def main():
    """主函数 - 立即执行推送"""
    import argparse
    parser = argparse.ArgumentParser(description="即时推送脚本")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--signature", help="仅推送指定 signature 的持仓")
    args = parser.parse_args()

    print("🚀 执行即时推送服务")
    print(f"📅 当前时间: {datetime.now()}")
    
    # 检查推送配置
    print("\n📝 检查推送配置...")
    if not prepare_push_content():
        return
    
    # 立即发送推送
    print("\n📤 发送即时推送...")
    success = send_push_notification(config_path=args.config, signature=args.signature)
    
    if success:
        print("\n✅ 即时推送执行完成")
    else:
        print("\n❌ 即时推送执行失败")

if __name__ == "__main__":
    main()