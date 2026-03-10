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
    """发送即时推送通知 - 使用 OpenClaw notify 模块"""
    print(f"[{datetime.now()}] 开始执行即时推送...")
    
    try:
        # 构建推送消息内容
        message = build_push_message(config_path, signature)
        
        # 使用 OpenClaw notify 脚本发送
        notify_script = "/home/admin/.openclaw/scripts/notify.sh"
        
        if not os.path.exists(notify_script):
            print(f"❌ Notify 脚本不存在: {notify_script}")
            return False
        
        # 执行推送
        print(f"📤 使用 OpenClaw notify 发送消息...")
        result = subprocess.run(
            ["bash", notify_script, message],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ 即时推送成功")
            return True
        else:
            print("❌ 即时推送失败")
            print(f"错误: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 执行即时推送时发生异常: {e}")
        return False


def build_push_message(config_path=None, signature=None):
    """构建推送消息内容"""
    from datetime import datetime
    
    msg_parts = ["📊 AI-Trader 交易报告"]
    msg_parts.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if signature:
        msg_parts.append(f"Agent: {signature}")
    
    if config_path:
        msg_parts.append(f"配置: {os.path.basename(config_path)}")
    
    # 尝试读取持仓信息
    data_dir = Path("/home/admin/.openclaw/data/ai-trader/data/agent_data_astock")
    if signature and data_dir.exists():
        # 查找最新的持仓文件
        agent_dirs = list(data_dir.glob(f"{signature}*"))
        if agent_dirs:
            agent_dir = agent_dirs[0]
            position_files = list(agent_dir.glob("*/position.json"))
            if position_files:
                try:
                    with open(position_files[-1], 'r') as f:
                        import json
                        position = json.load(f)
                        cash = position.get('cash', 0)
                        positions = position.get('positions', [])
                        total_value = position.get('total_value', 0)
                        
                        msg_parts.append(f"")
                        msg_parts.append(f"💰 总资产: ¥{total_value:,.2f}")
                        msg_parts.append(f"💵 现金: ¥{cash:,.2f}")
                        msg_parts.append(f"📈 持仓数量: {len(positions)} 只")
                except Exception as e:
                    pass
    
    return "\n".join(msg_parts)


def prepare_push_content():
    """准备推送内容（检查配置）"""
    try:
        # 检查 notify 脚本是否存在
        notify_script = "/home/admin/.openclaw/scripts/notify.sh"
        if not os.path.exists(notify_script):
            print(f"❌ Notify 脚本不存在: {notify_script}")
            return False
        
        print("✅ 推送配置检查通过 (使用 OpenClaw notify)")
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