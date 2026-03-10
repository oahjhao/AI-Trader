#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证1000成分股数据增量更新脚本

功能：
1. 检查本地存量数据
2. 如果存量数据不存在或异常 -> 报错退出，提示使用手动脚本
3. 如果存量数据正常 -> 计算增量日期范围，拉取新数据
4. 合并并保存更新后的数据

用法：
    python fetch_zz1000_data.py                    # 自动增量更新
    python fetch_zz1000_data.py --check-only       # 仅检查存量数据状态
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

# 数据文件路径
DATA_DIR = Path("/home/admin/.openclaw/data/ai-trader/data/A_stock")
STOCK_DATA_FILE = DATA_DIR / "zz1000_constituents.json"


def check_existing_data() -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    检查存量数据状态
    
    Returns:
        (exists: bool, last_date: str or None, data: dict or None)
    """
    if not STOCK_DATA_FILE.exists():
        return False, None, None
    
    try:
        with open(STOCK_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证数据格式
        if not isinstance(data, dict):
            print(f"❌ 存量数据格式错误: 应为字典类型，实际为 {type(data)}")
            return False, None, None
        
        if 'constituents' not in data:
            print("❌ 存量数据格式错误: 缺少 'constituents' 字段")
            return False, None, None
        
        if 'last_update' not in data:
            print("❌ 存量数据格式错误: 缺少 'last_update' 字段")
            return False, None, None
        
        last_update = data['last_update']
        
        # 验证日期格式
        try:
            datetime.strptime(last_update, '%Y-%m-%d')
        except ValueError:
            print(f"❌ 存量数据格式错误: last_update 日期格式无效 '{last_update}'")
            return False, None, None
        
        return True, last_update, data
        
    except json.JSONDecodeError as e:
        print(f"❌ 存量数据 JSON 解析错误: {e}")
        return False, None, None
    except Exception as e:
        print(f"❌ 读取存量数据时发生异常: {e}")
        return False, None, None


def fetch_zz1000_data(start_date: str, end_date: str) -> dict:
    """
    拉取指定日期范围的中证1000成分股数据
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
    
    Returns:
        拉取的数据字典
    """
    print(f"📥 拉取中证1000数据: {start_date} ~ {end_date}")
    
    # TODO: 实现实际的数据拉取逻辑
    # 这里使用模拟数据作为示例
    # 实际实现应该调用 Tushare/AKShare 等数据源
    
    # 模拟：返回空数据，实际使用时需要替换为真实的数据拉取代码
    print("⚠️  注意: 当前使用模拟数据，请替换为实际的数据拉取实现")
    
    return {
        "constituents": [],
        "start_date": start_date,
        "end_date": end_date,
        "count": 0
    }


def merge_data(existing_data: dict, new_data: dict) -> dict:
    """
    合并存量数据和新数据
    
    Args:
        existing_data: 存量数据
        new_data: 新拉取的数据
    
    Returns:
        合并后的数据
    """
    # 合并成分股列表（去重）
    existing_constituents = {c['code']: c for c in existing_data.get('constituents', [])}
    new_constituents = {c['code']: c for c in new_data.get('constituents', [])}
    
    # 新数据覆盖旧数据
    merged_constituents = {**existing_constituents, **new_constituents}
    
    merged_data = {
        "constituents": list(merged_constituents.values()),
        "start_date": existing_data.get('start_date', new_data.get('start_date')),
        "end_date": new_data.get('end_date', existing_data.get('end_date')),
        "last_update": datetime.now().strftime('%Y-%m-%d'),
        "update_history": existing_data.get('update_history', []) + [{
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "range": f"{new_data.get('start_date')} ~ {new_data.get('end_date')}",
            "count": len(new_constituents)
        }]
    }
    
    return merged_data


def save_data(data: dict) -> bool:
    """保存数据到文件"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # 先备份旧文件
        if STOCK_DATA_FILE.exists():
            backup_file = STOCK_DATA_FILE.with_suffix('.json.backup')
            STOCK_DATA_FILE.rename(backup_file)
            print(f"📦 已备份旧数据到: {backup_file}")
        
        # 保存新数据
        with open(STOCK_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"❌ 保存数据失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="中证1000成分股数据增量更新")
    parser.add_argument("--check-only", action="store_true", help="仅检查存量数据状态")
    parser.add_argument("--force", action="store_true", help="强制更新（忽略检查）")
    args = parser.parse_args()
    
    print("🔍 中证1000成分股数据增量更新")
    print("=" * 50)
    
    # 检查存量数据
    exists, last_date, existing_data = check_existing_data()
    
    if args.check_only:
        if exists:
            print(f"✅ 存量数据正常")
            print(f"   最后更新: {last_date}")
            print(f"   文件路径: {STOCK_DATA_FILE}")
            return 0
        else:
            print("❌ 存量数据不存在或异常")
            print(f"   预期文件: {STOCK_DATA_FILE}")
            return 1
    
    if not exists:
        print("\n" + "=" * 50)
        print("❌ 错误: 存量数据不存在或格式异常")
        print("\n请使用手动脚本进行首次数据拉取:")
        print("   python scripts/fetch_zz1000_manual.py --full")
        print("   或")
        print("   python scripts/fetch_zz1000_manual.py --start 2024-01-01 --end 2025-03-06")
        print("=" * 50)
        return 1
    
    print(f"✅ 存量数据检查通过")
    print(f"   最后更新: {last_date}")
    print(f"   成分股数: {len(existing_data.get('constituents', []))}")
    
    # 计算增量日期范围
    last_date_obj = datetime.strptime(last_date, '%Y-%m-%d')
    today = datetime.now()
    
    # 如果最后更新是今天，无需更新
    if last_date_obj.date() == today.date():
        print("\n✅ 数据已是最新（今天已更新），无需增量拉取")
        return 0
    
    # 计算下一个交易日（简化处理，实际应该考虑节假日）
    start_date = (last_date_obj + timedelta(days=1)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    print(f"\n📅 增量更新范围: {start_date} ~ {end_date}")
    
    # 拉取新数据
    try:
        new_data = fetch_zz1000_data(start_date, end_date)
    except Exception as e:
        print(f"\n❌ 拉取数据失败: {e}")
        return 1
    
    # 合并数据
    print("\n🔀 合并数据...")
    merged_data = merge_data(existing_data, new_data)
    
    # 保存数据
    print("💾 保存数据...")
    if save_data(merged_data):
        print(f"\n✅ 数据更新成功")
        print(f"   保存路径: {STOCK_DATA_FILE}")
        print(f"   成分股数: {len(merged_data['constituents'])}")
        print(f"   最后更新: {merged_data['last_update']}")
        return 0
    else:
        print("\n❌ 数据保存失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
