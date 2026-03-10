#!/usr/bin/env python3
"""
分批全量更新脚本
每批处理指定数量的股票，避免单次运行时间过长
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
TOKEN = os.getenv("TUSHARE_TOKEN")
INDEX_CODE = "000852.SH"
BATCH_SIZE = 50
REQUESTS_PER_MINUTE = 45


def get_constituents() -> List[str]:
    """获取中证 1000 成分股列表"""
    pro = ts.pro_api(TOKEN)
    today = datetime.now()
    end_date = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
    
    print(f"📊 获取中证 1000 成分股...")
    df = pro.index_weight(index_code=INDEX_CODE, start_date=start_date, end_date=end_date)
    
    if df.empty:
        end_date = today.strftime("%Y%m%d")
        start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
        df = pro.index_weight(index_code=INDEX_CODE, start_date=start_date, end_date=end_date)
    
    constituents = sorted(df['con_code'].unique().tolist())
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


def batch_update(batch_num: int = 1, batch_size: int = 50):
    """执行指定批次的数据更新"""
    pro = ts.pro_api(TOKEN)
    constituents = get_constituents()
    
    # 计算批次
    total_batches = (len(constituents) + batch_size - 1) // batch_size
    
    if batch_num < 1 or batch_num > total_batches:
        print(f"❌ 批次号无效：{batch_num} (有效范围：1-{total_batches})")
        sys.exit(1)
    
    start_idx = (batch_num - 1) * batch_size
    end_idx = min(start_idx + batch_size, len(constituents))
    batch_stocks = constituents[start_idx:end_idx]
    
    # 加载现有数据
    existing_data = load_existing_data()
    print(f"📂 现有数据：{len(existing_data)} 只股票")
    
    # 计算日期范围（550 天）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=550)
    start_date_str = start_date.strftime("%Y%m%d")
    end_date_str = end_date.strftime("%Y%m%d")
    
    print(f"\n📦 批次 {batch_num}/{total_batches}")
    print(f"📊 股票范围：{start_idx+1}-{end_idx} / {len(constituents)}")
    print(f"📅 日期范围：{start_date_str} - {end_date_str}")
    print(f"⏱️  预计耗时：约 {batch_size // 50 * 2} 分钟\n")
    
    success_count = 0
    error_symbols = []
    
    for i, symbol in enumerate(batch_stocks, 1):
        stock_data = fetch_stock_data(pro, symbol, start_date_str, end_date_str)
        
        if stock_data:
            existing_data[symbol] = stock_data
            success_count += 1
            if i % 10 == 0:
                print(f"  进度：{i}/{len(batch_stocks)} (成功：{success_count})")
        else:
            error_symbols.append(symbol)
        
        # 限速控制（每 50 次请求等待 60 秒）
        if i % 50 == 0 and i < len(batch_stocks):
            sleep_time = 65
            print(f"⏱️  API 限速，等待 {sleep_time} 秒...")
            time.sleep(sleep_time)
    
    # 保存数据
    print(f"\n💾 保存数据...")
    with open(PRICE_DATA_PATH, 'w', encoding='utf-8') as f:
        for symbol, data in existing_data.items():
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    # 保存进度标记
    progress_file = PRICE_DATA_PATH.parent / "batch_progress.json"
    with open(progress_file, 'w') as f:
        json.dump({
            "last_batch": batch_num,
            "total_batches": total_batches,
            "total_stocks": len(existing_data),
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    
    print(f"\n✅ 批次 {batch_num} 完成！")
    print(f"   本批成功：{success_count}/{len(batch_stocks)}")
    print(f"   本批失败：{len(error_symbols)}")
    print(f"   累计股票：{len(existing_data)}")
    
    if error_symbols:
        error_path = PRICE_DATA_PATH.parent / f"batch{batch_num}_errors.txt"
        with open(error_path, 'w') as f:
            f.write('\n'.join(error_symbols))
        print(f"⚠️  失败股票已保存到 {error_path}")
    
    if batch_num < total_batches:
        print(f"\n📌 下一批：python3 batch_full_update.py --batch {batch_num + 1}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="分批全量更新")
    parser.add_argument("--batch", type=int, default=1, help="批次号（从 1 开始）")
    parser.add_argument("--batch-size", type=int, default=50, help="每批股票数量")
    
    args = parser.parse_args()
    batch_update(batch_num=args.batch, batch_size=args.batch_size)
