#!/usr/bin/env python3
"""
A 股选股策略执行脚本
Stock Selection Runner for AI-Trader

用法:
    python run_stock_selection.py [--date YYYY-MM-DD] [--no-jsonl]

说明:
    - 默认使用今天作为选股日期
    - 默认从 merged.jsonl 加载价格数据（更快）
    - 输出文件：output/sse_pick_YYYYMMDD.csv
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data.A_stock.stock_selection import StockSelector, SelectionConfig


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='A 股选股策略 - 中证 1000 成分股筛选',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 使用今天日期执行选股
    python run_stock_selection.py
    
    # 指定选股日期
    python run_stock_selection.py --date 2026-03-03
    
    # 不使用 JSONL 文件，直接从 Tushare API 获取数据
    python run_stock_selection.py --no-jsonl
    
    # 自定义配置（在代码中修改 SelectionConfig）
        """
    )
    
    parser.add_argument(
        '--date', '-d',
        type=str,
        default=None,
        help='选股日期，格式：YYYY-MM-DD 或 YYYYMMDD (默认：今天)'
    )
    
    parser.add_argument(
        '--no-jsonl',
        action='store_true',
        help='不使用 JSONL 文件，直接从 Tushare API 获取价格数据'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=True,
        help='显示详细信息 (默认：开启)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='静默模式，只输出结果文件路径'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 创建配置
    config = SelectionConfig()
    config.VERBOSE = not args.quiet
    
    # 创建选股器
    selector = StockSelector(config)
    
    try:
        # 执行选股
        result = selector.select_stocks(
            selection_date=args.date,
            use_jsonl=not args.no_jsonl
        )
        
        # 输出结果
        if args.quiet:
            # 静默模式：只输出文件路径
            output_path = config.get_output_path(args.date or datetime.now().strftime("%Y-%m-%d"))
            print(str(output_path))
        else:
            # 正常模式：输出选中股票
            if result is not None and len(result) > 0:
                print(f"\n📊 选中 {len(result)} 只股票:")
                for _, row in result.iterrows():
                    print(f"   {row['ts_code']} - {row['stock_name']}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 选股执行失败：{e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
