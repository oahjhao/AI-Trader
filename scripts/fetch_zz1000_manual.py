#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证1000成分股数据手动拉取脚本

用于首次拉取或补充特定时间段的数据

用法：
    # 全量拉取（首次使用）
    python fetch_zz1000_manual.py --full
    
    # 拉取特定时间段
    python fetch_zz1000_manual.py --start 2024-01-01 --end 2025-03-06
    
    # 只拉取最近N天的数据
    python fetch_zz1000_manual.py --days 252
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# 数据文件路径
DATA_DIR = Path("/home/admin/.openclaw/data/ai-trader/data/A_stock")
STOCK_DATA_FILE = DATA_DIR / "zz1000_constituents.json"


def get_zz1000_constituents(date: str) -> List[Dict]:
    """
    获取指定日期的中证1000成分股列表
    
    Args:
        date: 日期 (YYYY-MM-DD)
    
    Returns:
        成分股列表
    """
    print(f"  📥 获取 {date} 的成分股数据...")
    
    # TODO: 实现实际的数据拉取逻辑
    # 这里应该调用 Tushare/AKShare 等数据源
    # 示例使用模拟数据
    
    # 模拟中证1000成分股
    # 实际使用时需要替换为真实的数据拉取代码
    mock_constituents = []
    
    return mock_constituents


def fetch_data_range(start_date: str, end_date: str) -> Dict:
    """
    拉取指定日期范围的数据
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
    
    Returns:
        数据字典
    """
    print(f"\n📥 开始拉取数据: {start_date} ~ {end_date}")
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    all_constituents = {}
    current = start
    
    # 按月分批拉取
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        constituents = get_zz1000_constituents(date_str)
        
        # 合并成分股（以代码为key去重）
        for stock in constituents:
            code = stock.get('code')
            if code:
                all_constituents[code] = stock
        
        # 下个月
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    result = {
        "constituents": list(all_constituents.values()),
        "start_date": start_date,
        "end_date": end_date,
        "last_update": datetime.now().strftime('%Y-%m-%d'),
        "update_history": [{
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "type": "manual_full" if (end - start).days > 300 else "manual_partial",
            "range": f"{start_date} ~ {end_date}",
            "count": len(all_constituents)
        }]
    }
    
    print(f"✅ 拉取完成，共 {len(all_constituents)} 只成分股")
    return result


def save_data(data: Dict, force: bool = False) -> bool:
    """保存数据到文件"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # 检查文件是否已存在
        if STOCK_DATA_FILE.exists() and not force:
            print(f"\n⚠️  文件已存在: {STOCK_DATA_FILE}")
            response = input("是否覆盖? (y/N): ")
            if response.lower() != 'y':
                print("已取消保存")
                return False
        
        # 备份旧文件
        if STOCK_DATA_FILE.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = DATA_DIR / f"zz1000_constituents.json.backup_{timestamp}"
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
    parser = argparse.ArgumentParser(description="中证1000成分股数据手动拉取")
    
    # 日期范围选项（互斥）
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument("--full", action="store_true", help="全量拉取（2020-01-01 至今）")
    date_group.add_argument("--start", type=str, metavar="YYYY-MM-DD", help="开始日期")
    date_group.add_argument("--days", type=int, metavar="N", help="拉取最近N天的数据")
    
    parser.add_argument("--end", type=str, default=datetime.now().strftime('%Y-%m-%d'),
                        metavar="YYYY-MM-DD", help="结束日期（默认今天）")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的数据")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不保存数据")
    
    args = parser.parse_args()
    
    print("🔧 中证1000成分股数据手动拉取")
    print("=" * 50)
    
    # 确定日期范围
    if args.full:
        start_date = "2020-01-01"
        end_date = datetime.now().strftime('%Y-%m-%d')
        print(f"📅 模式: 全量拉取")
    elif args.days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
        print(f"📅 模式: 最近 {args.days} 天")
    else:
        start_date = args.start
        end_date = args.end
        print(f"📅 模式: 指定日期范围")
    
    print(f"   开始日期: {start_date}")
    print(f"   结束日期: {end_date}")
    
    # 验证日期格式
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        print("\n❌ 错误: 日期格式无效，请使用 YYYY-MM-DD 格式")
        return 1
    
    if start_date > end_date:
        print("\n❌ 错误: 开始日期不能晚于结束日期")
        return 1
    
    # 拉取数据
    try:
        data = fetch_data_range(start_date, end_date)
    except Exception as e:
        print(f"\n❌ 拉取数据失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 试运行模式
    if args.dry_run:
        print("\n🏃 试运行模式，不保存数据")
        print(f"   将保存 {len(data['constituents'])} 只成分股")
        print(f"   数据范围: {data['start_date']} ~ {data['end_date']}")
        return 0
    
    # 保存数据
    print("\n💾 保存数据...")
    if save_data(data, force=args.force):
        print(f"\n✅ 数据保存成功")
        print(f"   保存路径: {STOCK_DATA_FILE}")
        print(f"   成分股数: {len(data['constituents'])}")
        print(f"   数据范围: {data['start_date']} ~ {data['end_date']}")
        print(f"   最后更新: {data['last_update']}")
        
        # 后续使用提示
        print("\n" + "=" * 50)
        print("📋 后续使用:")
        print("   增量更新: python scripts/fetch_zz1000_data.py")
        print("   检查状态: python scripts/fetch_zz1000_data.py --check-only")
        print("=" * 50)
        
        return 0
    else:
        print("\n❌ 数据保存失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
