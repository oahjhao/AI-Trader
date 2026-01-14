#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时推送脚本
按指定时间点执行真实的钉钉推送
使用 .env 中的配置变量
"""

import os
import sys
import time
import subprocess
from datetime import datetime, time as dt_time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / '.env')

def get_python_executable():
    """获取虚拟环境中的Python可执行文件路径"""
    venv_path = project_root / 'venv'
    if os.name == 'nt':  # Windows
        python_exe = venv_path / 'Scripts' / 'python.exe'
    else:  # Linux/Mac
        python_exe = venv_path / 'bin' / 'python3'
    
    if not python_exe.exists():
        raise FileNotFoundError(f"找不到Python可执行文件: {python_exe}")
    
    return str(python_exe)

def send_push_notification():
    """发送推送通知"""
    print(f"[{datetime.now()}] 开始执行推送...")
    
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
        
        # 执行推送
        print(f"📤 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root))
        
        if result.returncode == 0:
            print("✅ 推送成功")
            if result.stdout:
                print(f"输出: {result.stdout}")
            return True
        else:
            print("❌ 推送失败")
            print(f"错误: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 执行推送时发生异常: {e}")
        return False


def modify_push_content():
    """修改推送内容，在开头添加 position 关键字"""
    try:
        # 备份原始 cli.py
        cli_path = project_root / "webhook" / "cli.py"
        backup_path = project_root / "webhook" / "cli.py.backup"
        
        if not backup_path.exists():
            import shutil
            shutil.copy2(cli_path, backup_path)
            print("✅ 已备份原始 cli.py 文件")
        
        # 读取 cli.py 内容
        with open(cli_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 在适当位置添加 position 关键字
        # 查找 PositionReporter 类的 format_position_message 方法
        if 'format_position_message' in content:
            # 在返回消息前添加 position 关键字
            lines = content.split('\n')
            new_lines = []
            
            for line in lines:
                new_lines.append(line)
                # 在返回合并消息的地方添加 position 关键字
                if 'full_message = "\n\n---\n\n".join(messages)' in line:
                    new_lines.append('        # 在推送内容开头添加 position 关键字')
                    new_lines.append('        full_message = "position\n\n" + full_message')
            
            # 写回文件
            with open(cli_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            print("✅ 已修改推送内容，添加 position 关键字")
            return True
            
    except Exception as e:
        print(f"❌ 修改推送内容时发生异常: {e}")
        return False

def get_scheduled_times():
    """获取预定的推送时间点"""
    return [
        dt_time(10, 30),  # 10:30
        dt_time(11, 30),  # 11:30
        dt_time(14, 0),   # 14:00
        dt_time(15, 0),   # 15:00
        dt_time(16, 0),   # 16:00
    ]

def time_to_string(dt_time_obj):
    """将time对象转换为字符串"""
    return dt_time_obj.strftime("%H:%M")

def main():
    """主函数 - 立即执行一次推送"""
    print("🚀 执行即时推送服务")
    print(f"📅 当前时间: {datetime.now()}")
    
    # 修改推送内容添加 position 关键字
    print("\n📝 准备推送内容...")
    modify_push_content()
    
    # 立即发送推送
    print("\n📤 发送推送...")
    success = send_push_notification()
    
    if success:
        print("\n✅ 推送执行完成")
    else:
        print("\n❌ 推送执行失败")

if __name__ == "__main__":
    main()