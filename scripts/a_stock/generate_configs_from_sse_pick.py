#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 sse_pick_2025.csv 自动生成配置文件
为每个唯一日期生成一个 astock_config_daily_YYYYMMDD.json 和对应的 sse_pick_YYYYMMDD.csv
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta


def generate_configs_from_sse_pick():
    """从 sse_pick_2025.csv 生成配置文件和对应的股票列表"""
    
    # 当前脚本目录
    script_dir = Path(__file__).parent
    
    # 读取 sse_pick_2025.csv
    csv_path = script_dir / "sse_pick_2025.csv"
    
    if not csv_path.exists():
        print(f"❌ 未找到文件: {csv_path}")
        return
    
    print(f"📖 读取股票列表: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # 按日期分组
    grouped = df.groupby('date')
    
    # 配置文件模板
    config_template = {
        "agent_type": "BaseAgentAStock",
        "market": "cn",
        "date_range": {
            "init_date": "",
            "end_date": ""
        },
        "models": [
            {
                "name": "Test_nuts_{date_short}",
                "basemodel": "deepseek-chat",
                "signature": "Test_nuts_{date_short}",
                "enabled": True
            },
            {
                "name": "Test_monk_{date_short}",
                "basemodel": "deepseek-chat",
                "signature": "Test_monk_{date_short}",
                "enabled": True
            },
            {
                "name": "Test_tech_{date_short}",
                "basemodel": "deepseek-chat",
                "signature": "Test_tech_{date_short}",
                "enabled": True
            },
            {
                "name": "Test_balanced_{date_short}",
                "basemodel": "deepseek-chat",
                "signature": "Test_balanced_{date_short}",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 30,
            "max_retries": 3,
            "base_delay": 1.0,
            "initial_cash": 1000000.0
        },
        "log_config": {
            "log_path": "./data/agent_data_astock"
        }
    }
    
    # 统计
    total_dates = len(grouped)
    generated_configs = 0
    generated_csvs = 0
    
    print(f"\n🔄 开始生成配置文件，共 {total_dates} 个日期")
    print("=" * 60)
    
    # 为每个日期生成配置文件
    for date_str, group_df in grouped:
        # 转换日期格式: 20250103 -> 2025-01-03
        try:
            date_obj = datetime.strptime(str(date_str), "%Y%m%d")
        except ValueError as e:
            print(f"⚠️ 跳过无效日期: {date_str} ({e})")
            continue
        
        init_date = date_obj.strftime("%Y-%m-%d")
        end_date = (date_obj + timedelta(days=7)).strftime("%Y-%m-%d")
        
        # 生成配置文件
        config = json.loads(json.dumps(config_template))  # Deep copy
        config["date_range"]["init_date"] = init_date
        config["date_range"]["end_date"] = end_date
        
        # 更新 model names 中的日期（6位短格式: 250103）
        date_short = date_obj.strftime("%y%m%d")
        for model in config["models"]:
            model["name"] = model["name"].format(date_short=date_short)
            model["signature"] = model["signature"].format(date_short=date_short)
        
        # 保存配置文件到 configs/
        config_filename = f"astock_config_daily_{date_str}.json"
        config_path = script_dir.parent.parent / "configs" / config_filename
        config_path.parent.mkdir(exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        generated_configs += 1
        print(f"✅ 配置: {config_filename}")
        
        # 生成对应的 sse_pick_YYYYMMDD.csv
        sse_pick_filename = f"sse_pick_{date_str}.csv"
        sse_pick_path = script_dir / sse_pick_filename
        
        # 只保留 con_code 和 stock_name 列
        group_df[["con_code", "stock_name"]].to_csv(
            sse_pick_path, index=False, encoding='utf-8-sig'
        )
        
        generated_csvs += 1
        print(f"✅ 股票列表: {sse_pick_filename} ({len(group_df)} 只股票)")
        print("-" * 60)
    
    print(f"\n🎉 生成完成！")
    print(f"📊 统计信息:")
    print(f"  - 总日期数: {total_dates}")
    print(f"  - 生成配置: {generated_configs}")
    print(f"  - 生成股票列表: {generated_csvs}")
    print(f"\n📂 输出位置:")
    print(f"  - 配置文件: {config_path.parent}/")
    print(f"  - 股票列表: {script_dir}/")


if __name__ == "__main__":
    generate_configs_from_sse_pick()
