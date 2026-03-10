#!/usr/bin/env python3
"""
中证 1000 数据增量更新脚本
- 首次运行：拉取 550 天历史数据作为存量
- 后续运行：只拉取最新数据追加到 JSONL

Usage:
    # 首次全量拉取
    python incremental_update.py --full
    
    # 增量更新（默认）
    python incremental_update.py
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

load_dotenv()

# 容器内数据目录（通过 volume mount 挂载持久化数据）
DATA_DIR = Path("/home/ec2-user/AI-Trader/data/A_stock")
PRICE_DATA_PATH = DATA_DIR / "zz1000_merged.jsonl"
BACKUP_PATH = DATA_DIR / "zz1000_merged.jsonl.backup"
TOKEN = os.getenv("TUSHARE_TOKEN")
INDEX_CODE = "000852.SH"  # 中证 1000

# Tushare API 限制：每分钟最多请求 50 次
REQUESTS_PER_MINUTE = 45
BATCH_SIZE = 50  # 每批请求的股票数量


def get_constituents() -> List[str]:
    """获取中证 1000 成分股列表"""
    pro = ts.pro_api(TOKEN)
    today = datetime.now()
    end_date = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
    
    print(f"📊 获取中证 1000 成分股...")
    df = pro.index_weight(index_code=INDEX_CODE, start_date=start_date, end_date=end_date)
    
    if df.empty:
        # 尝试最近一个月
        end_date = today.strftime("%Y%m%d")
        start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.index_weight(index_code=INDEX_CODE, start_date=start_date, end_date=end_date)
    
    constituents = df['con_code'].unique().tolist()
    print(f"✅ 获取到 {len(constituents)} 只成分股")
    return constituents


def load_existing_data() -> dict:
    """加载现有的 JSONL 数据"""
    if not PRICE_DATA_PATH.exists():
        return {}
    
    data = {}
    with open(PRICE_DATA_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                symbol = record.get('symbol')
                if symbol:
                    data[symbol] = record
            except json.JSONDecodeError:
                continue
    
    return data


def fetch_stock_data(pro, symbol: str, start_date: str, end_date: str, max_retries=3) -> Optional[dict]:
    """获取单只股票的历史数据"""
    for attempt in range(1, max_retries + 1):
        try:
            df = pro.daily(ts_code=symbol, start_date=start_date, end_date=end_date)
            if df.empty:
                return None
            
            # 转换为所需格式
            time_series = {}
            for _, row in df.iterrows():
                trade_date = row['trade_date']
                time_series[trade_date] = {
                    "1. buy price": float(row['close']),
                    "2. high": float(row['high']),
                    "3. low": float(row['low']),
                    "4. sell price": float(row['close']),
                    "5. volume": int(row['vol'])
                }
            
            return {
                "Meta Data": {
                    "1. Information": "Daily Prices and Volumes",
                    "2. Symbol": symbol,
                    "3. Last Refreshed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "4. Interval": "1day",
                    "5. Output Size": "Full size",
                    "6. Time Zone": "US/Eastern"
                },
                "Time Series (1day)": time_series
            }
        except Exception as e:
            if attempt < max_retries:
                wait_time = 5 * attempt
                print(f"⚠️ 获取 {symbol} 失败 (尝试 {attempt}/{max_retries})，等待 {wait_time} 秒...")
                time.sleep(wait_time)
            else:
                print(f"❌ 获取 {symbol} 失败：{str(e)[:100]}")
                return None
    
    return None


def incremental_update(days_to_fetch: int = 30):
    """增量更新：只获取最近 N 天的数据"""
    pro = ts.pro_api(TOKEN)
    
    # 获取成分股
    constituents = get_constituents()
    
    # 加载现有数据
    existing_data = load_existing_data()
    print(f"📂 现有数据：{len(existing_data)} 只股票")
    
    # 计算日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_to_fetch)
    start_date_str = start_date.strftime("%Y%m%d")
    end_date_str = end_date.strftime("%Y%m%d")
    
    print(f"📅 增量更新范围：{start_date_str} - {end_date_str}")
    
    # 分批获取数据
    new_count = 0
    updated_count = 0
    error_count = 0
    
    for i in range(0, len(constituents), BATCH_SIZE):
        batch = constituents[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(constituents) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n📦 处理批次 {batch_num}/{total_batches} ({len(batch)} 只股票)...")
        
        for symbol in batch:
            stock_data = fetch_stock_data(pro, symbol, start_date_str, end_date_str)
            
            if stock_data:
                if symbol in existing_data:
                    # 合并数据
                    existing_series = existing_data[symbol].get("Time Series (1day)", {})
                    new_series = stock_data.get("Time Series (1day)", {})
                    
                    # 只添加新日期
                    for date, data in new_series.items():
                        if date not in existing_series:
                            existing_series[date] = data
                            updated_count += 1
                    
                    existing_data[symbol]["Time Series (1day)"] = existing_series
                    existing_data[symbol]["Meta Data"]["3. Last Refreshed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # 新股票
                    existing_data[symbol] = stock_data
                    new_count += 1
            else:
                error_count += 1
        
        # 限速控制
        if i + BATCH_SIZE < len(constituents):
            sleep_time = 60 - (time.time() % 60)
            print(f"⏱️  限速控制，等待 {sleep_time:.0f} 秒...")
            time.sleep(sleep_time)
    
    # 保存数据
    print(f"\n💾 保存数据到 {PRICE_DATA_PATH}...")
    with open(PRICE_DATA_PATH, 'w', encoding='utf-8') as f:
        for symbol, data in existing_data.items():
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    print(f"\n✅ 增量更新完成！")
    print(f"   新增股票：{new_count}")
    print(f"   更新记录：{updated_count}")
    print(f"   失败股票：{error_count}")
    print(f"   总计股票：{len(existing_data)}")


def full_update():
    """全量更新：拉取 550 天历史数据"""
    pro = ts.pro_api(TOKEN)
    
    # 获取成分股
    constituents = get_constituents()
    
    # 计算日期范围（550 天）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=550)
    start_date_str = start_date.strftime("%Y%m%d")
    end_date_str = end_date.strftime("%Y%m%d")
    
    print(f"📅 全量更新范围：{start_date_str} - {end_date_str}")
    print(f"⚠️  预计耗时：约 {len(constituents) // BATCH_SIZE * 2} 分钟")
    
    all_data = {}
    error_symbols = []
    
    for i in range(0, len(constituents), BATCH_SIZE):
        batch = constituents[i:i+BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(constituents) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n📦 处理批次 {batch_num}/{total_batches} ({len(batch)} 只股票)...")
        
        for symbol in batch:
            stock_data = fetch_stock_data(pro, symbol, start_date_str, end_date_str)
            
            if stock_data:
                all_data[symbol] = stock_data
            else:
                error_symbols.append(symbol)
        
        # 限速控制
        if i + BATCH_SIZE < len(constituents):
            sleep_time = 60 - (time.time() % 60)
            print(f"⏱️  限速控制，等待 {sleep_time:.0f} 秒...")
            time.sleep(sleep_time)
    
    # 保存数据
    print(f"\n💾 保存数据到 {PRICE_DATA_PATH}...")
    with open(PRICE_DATA_PATH, 'w', encoding='utf-8') as f:
        for symbol, data in all_data.items():
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    # 保存错误列表
    if error_symbols:
        error_path = PRICE_DATA_PATH.parent / "fetch_errors.txt"
        with open(error_path, 'w') as f:
            f.write('\n'.join(error_symbols))
        print(f"⚠️  失败股票已保存到 {error_path}")
    
    print(f"\n✅ 全量更新完成！")
    print(f"   成功股票：{len(all_data)}")
    print(f"   失败股票：{len(error_symbols)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="中证 1000 数据更新脚本")
    parser.add_argument("--full", action="store_true", help="全量更新（首次运行）")
    parser.add_argument("--days", type=int, default=30, help="增量更新天数（默认 30 天）")
    
    args = parser.parse_args()
    
    if args.full:
        full_update()
    else:
        incremental_update(days_to_fetch=args.days)
