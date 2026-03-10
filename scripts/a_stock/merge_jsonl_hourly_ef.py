import json
import os
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def convert_a_stock_to_jsonl(
    csv_path: str = "A_stock_hourly.csv",
    output_path: str = "merged_hourly.jsonl",
    stock_name_csv: str = "sse_pick.csv",
) -> None:
    """Convert A-share CSV data to JSONL format compatible with the trading system.

    The output format matches the Alpha Vantage format used for NASDAQ data:
    - Each line is a JSON object for one stock
    - Contains "Meta Data" and "Time Series (Daily)" fields
    - Uses "1. buy price" (open), "2. high", "3. low", "4. sell price" (close), "5. volume"
    - Includes stock name from sse_50_weight.csv for better AI understanding

    Args:
        csv_path: Path to the A-share daily price CSV file
        output_path: Path to output JSONL file
        stock_name_csv: Path to SSE 50 weight CSV containing stock names
    """
    csv_path = Path(csv_path)
    output_path = Path(output_path)
    stock_name_csv = Path(stock_name_csv)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return

    print(f"Reading CSV file: {csv_path}")

    # Read CSV data
    df = pd.read_csv(csv_path)

    # Read stock name mapping
    stock_name_map = {}
    if stock_name_csv.exists():
        print(f"Reading stock names from: {stock_name_csv}")
        name_df = pd.read_csv(stock_name_csv)
        # Create mapping from con_code (stock_code) to stock_name
        stock_name_map = dict(zip(name_df["stock_name"], name_df["con_code"]))
        print(f"Loaded {len(stock_name_map)} stock names")
    else:
        print(f"Warning: Stock name file not found: {stock_name_csv}")

    print(f"Total records: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Group by stock symbol
    grouped = df.groupby("stock_code")

    print(f"Processing {len(grouped)} stocks...")

    with open(output_path, "w", encoding="utf-8") as fout:
        for stock_code, group_df in grouped:
            # Sort by date ascending
            group_df = group_df.sort_values("trade_date", ascending=True)

            # Get stock name from mapping
            stock_name = str(group_df["stock_name"].max())
            stock_code_all = stock_name_map.get(stock_name, "Unknown")

            # Get latest date for Meta Data
            latest_date = str(group_df["trade_date"].max())
            #latest_date_formatted = f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:]}"
            latest_date_formatted = f"{latest_date}"

            # Build Time Series (Daily) data
            time_series = {}

            for idx, row in group_df.iterrows():
                date_str = str(row["trade_date"])
                #date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                date_formatted = f"{date_str}"

                # For the latest date, only include buy price (to prevent future information leakage)
                time_series[date_formatted] = {
                    "1. buy price": str(row["open"]),
                    "2. high": str(row["high"]),
                    "3. low": str(row["low"]),
                    "4. sell price": str(row["close"]),
                    "5. volume": (
                        str(int(row["volume"] * 100)) if pd.notna(row["volume"]) else "0"
                    ),  # Convert to shares (vol is in 手, 1手=100股)
                    "6. pct_chg": str(row["pct_chg"]),
                    "7. pct_w": str(row["pct_w"]),
                    "8. amount": str(row["amount"]),
                    "9. amount_chg": str(row["amount_chg"]),
                    "10. exchg": str(row["exchg"]),
                }
            
            # Build complete JSON object
            json_obj = {
                "Meta Data": {
                    "1. Information": "Daily Prices (buy price, high, low, sell price) and Volumes",
                    "2. Symbol": stock_code_all,
                    "2.1. Name": stock_name,
                    "3. Last Refreshed": latest_date_formatted,
                    "4. Output Size": "Full",
                    "5. Time Zone": "Asia/Shanghai",
                },
                "Time Series (60min)": time_series,
            }

            # Write to JSONL file
            fout.write(json.dumps(json_obj, ensure_ascii=False) + "\n")

    print(f"✅ Data conversion completed: {output_path}")
    print(f"✅ Total stocks: {len(grouped)}")
    print(f"✅ File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    import argparse
    
    # 数据目录：项目根目录下的 data/A_stock
    DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "A_stock"
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='A-Share小时线数据转JSONL格式')
    parser.add_argument('--date-suffix', type=str, default='', help='日期后缀 (YYYYMMDD)')
    parser.add_argument('--csv-path', type=str, default='A_stock_hourly.csv', help='CSV文件名')
    parser.add_argument('--output-path', type=str, default='merged_hourly.jsonl', help='输出JSONL文件名')
    parser.add_argument('--stock-list', type=str, default='sse_pick.csv', help='股票列表CSV')
    
    args = parser.parse_args()
    
    # 根据日期后缀构建文件名
    csv_name = args.csv_path
    output_name = args.output_path
    stock_list_name = args.stock_list
    
    if args.date_suffix:
        # 如果文件名不包含后缀，添加后缀
        if args.date_suffix not in args.csv_path:
            base = args.csv_path.rsplit('.', 1)[0]
            ext = args.csv_path.rsplit('.', 1)[1] if '.' in args.csv_path else 'csv'
            csv_name = f"{base}_{args.date_suffix}.{ext}"
        
        if args.date_suffix not in args.output_path:
            base = args.output_path.rsplit('.', 1)[0]
            ext = args.output_path.rsplit('.', 1)[1] if '.' in args.output_path else 'jsonl'
            output_name = f"{base}_{args.date_suffix}.{ext}"
        
        if args.date_suffix not in args.stock_list:
            base = args.stock_list.rsplit('.', 1)[0]
            ext = args.stock_list.rsplit('.', 1)[1] if '.' in args.stock_list else 'csv'
            stock_list_name = f"{base}_{args.date_suffix}.{ext}"
        
        print(f"📁 使用日期后缀: {args.date_suffix}")
        print(f"📁 CSV: {csv_name}, 输出: {output_name}, 股票列表: {stock_list_name}")
    
    # 构建完整路径
    csv_path = DATA_DIR / csv_name
    output_path = DATA_DIR / output_name
    stock_list = DATA_DIR / stock_list_name
    
    print(f"📂 数据目录: {DATA_DIR}")
    
    # Convert A-share data to JSONL format
    print("="*60)
    print("A-Share Data Converter")
    print("="*60)
    convert_a_stock_to_jsonl(
        csv_path=str(csv_path),
        output_path=str(output_path),
        stock_name_csv=str(stock_list)
    )
    print("="*60)
