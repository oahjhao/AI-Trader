"""
选股策略主逻辑
Stock Selector - Main Logic
"""
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import sys
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

try:
    from config import SelectionConfig
    from data_loader import DataLoader
    from factor_calculator import FactorCalculator
except ImportError:
    from .config import SelectionConfig
    from .data_loader import DataLoader
    from .factor_calculator import FactorCalculator


class StockSelector:
    """选股策略执行器
    
    执行流程：
    1. 获取中证 1000 成分股
    2. 加载价格数据和指数数据
    3. 计算 5 个因子
    4. 按条件筛选（4 个条件 AND 关系）
    5. 按 10 日动量排序，选取 Top 10
    6. 输出结果 CSV（股票代码 + 中文名称）
    """
    
    def __init__(self, config: Optional[SelectionConfig] = None):
        """初始化选股器
        
        Args:
            config: 配置对象，使用默认配置如果为 None
        """
        self.config = config or SelectionConfig()
        self.data_loader = DataLoader(self.config)
        self.factor_calculator = None
        self.factor_data = None
        self.selected_stocks = None
    
    def _get_date_range(self, selection_date: str) -> Tuple[str, str]:
        """计算数据获取的日期范围
        
        需要获取足够长的历史数据来计算因子：
        - 252 日残差波动率：需要 252 个交易日（约 1 年）
        - 考虑到 A 股约有 240-250 个交易日/年，需要获取约 18 个月的数据
        
        Args:
            selection_date: 选股日期，格式 YYYY-MM-DD 或 YYYYMMDD
            
        Returns:
            (start_date, end_date) 格式 YYYYMMDD
        """
        # 统一日期格式
        if '-' in selection_date:
            selection_dt = datetime.strptime(selection_date, "%Y-%m-%d")
        else:
            selection_dt = datetime.strptime(selection_date, "%Y%m%d")
        
        end_date = selection_dt
        # 往前推 550 天（约 18 个月，确保至少 252 个交易日）
        start_date = end_date - timedelta(days=550)
        
        return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
    
    def select_stocks(self, selection_date: Optional[str] = None, 
                     use_jsonl: bool = True) -> pd.DataFrame:
        """执行选股策略
        
        Args:
            selection_date: 选股日期，默认使用今天
            use_jsonl: 是否尝试使用 JSONL 文件加载价格数据
            
        Returns:
            选股结果 DataFrame，columns: ts_code, stock_name
        """
        # 1. 确定选股日期
        if selection_date is None:
            selection_date = datetime.now().strftime("%Y-%m-%d")
        
        print("=" * 60)
        print(f"🎯 A 股选股策略执行")
        print(f"📅 选股日期：{selection_date}")
        print("=" * 60)
        
        # 2. 获取成分股列表
        constituents = self.data_loader.get_constituents(selection_date)
        
        if not constituents:
            raise ValueError("未能获取到中证 1000 成分股")
        
        # 3. 获取股票名称
        stock_names = self.data_loader.get_stock_names(constituents)
        
        # 4. 计算日期范围
        start_date, end_date = self._get_date_range(selection_date)
        print(f"📊 数据范围：{start_date} - {end_date}")
        
        # 5. 加载价格数据
        use_jsonl_data = False
        price_data = pd.DataFrame()
        
        if use_jsonl and self.config.PRICE_DATA_PATH.exists():
            print("📂 尝试使用 JSONL 文件加载价格数据...")
            price_data, coverage_ok = self.data_loader.load_price_data_from_jsonl(
                required_stocks=constituents
            )
            if coverage_ok and len(price_data) > 0:
                use_jsonl_data = True
                print(f"✅ 使用 JSONL 数据")
            else:
                print(f"⚠️ JSONL 数据不足，切换到 Tushare API")
        
        if not use_jsonl_data:
            print("📡 从 Tushare API 获取价格数据（这可能需要几分钟）...")
            price_data = self.data_loader.load_price_data(constituents, start_date, end_date)
        
        # 6. 加载基准指数数据
        benchmark_data = self.data_loader.load_benchmark_data(start_date, end_date)
        
        # 7. 初始化因子计算器
        self.factor_calculator = FactorCalculator(price_data, benchmark_data)
        
        # 8. 计算所有因子
        self.factor_data = self.factor_calculator.calculate_all_factors(
            constituents, verbose=self.config.VERBOSE
        )
        
        # 9. 执行筛选
        self.selected_stocks = self._apply_filters(selection_date, stock_names)
        
        # 10. 保存结果
        output_path = self.config.get_output_path(selection_date)
        self._save_results(output_path)
        
        # 11. 打印详细信息
        self._print_details()
        
        return self.selected_stocks
    
    def _apply_filters(self, selection_date: str, stock_names: dict) -> pd.DataFrame:
        """应用筛选条件
        
        筛选条件（AND 关系）：
        1. 252 日残差波动率：前 50%（越低越好）
        2. 5 日换手率：前 50%（越高越好）
        3. 5 日动量：前 30%（越高越好）
        4. 20 日 Beta：前 30%（越高越好）
        
        最终排序：
        - 按 10 日动量排序（越低越好），选取 Top 10
        
        Args:
            selection_date: 选股日期
            stock_names: 股票名称字典
            
        Returns:
            筛选后的 DataFrame
        """
        df = self.factor_data.copy()
        
        print("\n" + "=" * 60)
        print("🔍 执行筛选")
        print("=" * 60)
        
        initial_count = len(df)
        print(f"初始股票数量：{initial_count}")
        
        # 统计 NaN 情况
        nan_counts = df.isna().sum()
        print(f"因子 NaN 统计:")
        for col in ['residual_vol_252d', 'turnover_5d', 'momentum_5d', 'beta_20d', 'momentum_10d']:
            if col in nan_counts.index:
                print(f"  {col}: {nan_counts[col]} 只股票数据不足")
        
        # 移除 NaN 值
        df = df.dropna(subset=['residual_vol_252d', 'turnover_5d', 'momentum_5d', 'beta_20d', 'momentum_10d'])
        after_dropna = len(df)
        print(f"\n去除 NaN 后：{after_dropna} ({initial_count - after_dropna} 只股票数据不足)")
        
        if after_dropna == 0:
            print("⚠️ 所有股票数据不足，无法进行筛选")
            return pd.DataFrame(columns=['ts_code', 'stock_name'])
        
        # 筛选条件 1: 252 日残差波动率 - 前 50%（越低越好）
        threshold_vol = df['residual_vol_252d'].quantile(self.config.RESIDUAL_VOL_PERCENTILE)
        df = df[df['residual_vol_252d'] <= threshold_vol]
        print(f"\n残差波动率 ≤ {threshold_vol:.4f} (前{int(self.config.RESIDUAL_VOL_PERCENTILE*100)}%): {len(df)} 只")
        
        if len(df) == 0:
            print("⚠️ 筛选后无股票")
            return pd.DataFrame(columns=['ts_code', 'stock_name'])
        
        # 筛选条件 2: 5 日换手率 - 前 50%（越高越好）
        threshold_turnover = df['turnover_5d'].quantile(1 - self.config.TURNOVER_PERCENTILE)
        df = df[df['turnover_5d'] >= threshold_turnover]
        print(f"5 日换手率 ≥ {threshold_turnover:.0f} (前{int(self.config.TURNOVER_PERCENTILE*100)}%): {len(df)} 只")
        
        if len(df) == 0:
            print("⚠️ 筛选后无股票")
            return pd.DataFrame(columns=['ts_code', 'stock_name'])
        
        # 筛选条件 3: 5 日动量 - 前 30%（越高越好）
        threshold_mom5 = df['momentum_5d'].quantile(1 - self.config.MOMENTUM_PERCENTILE)
        df = df[df['momentum_5d'] >= threshold_mom5]
        print(f"5 日动量 ≥ {threshold_mom5:.4f} (前{int((1-self.config.MOMENTUM_PERCENTILE)*100)}%): {len(df)} 只")
        
        if len(df) == 0:
            print("⚠️ 筛选后无股票")
            return pd.DataFrame(columns=['ts_code', 'stock_name'])
        
        # 筛选条件 4: 20 日 Beta - 前 30%（越高越好）
        threshold_beta = df['beta_20d'].quantile(1 - self.config.BETA_PERCENTILE)
        df = df[df['beta_20d'] >= threshold_beta]
        print(f"20 日 Beta ≥ {threshold_beta:.4f} (前{int((1-self.config.BETA_PERCENTILE)*100)}%): {len(df)} 只")
        
        if len(df) == 0:
            print("⚠️ 筛选后无股票")
            return pd.DataFrame(columns=['ts_code', 'stock_name'])
        
        # 最终排序：按 10 日动量（越低越好），选取 Top N
        df = df.sort_values('momentum_10d', ascending=True)
        
        # 添加股票名称
        df['stock_name'] = df['ts_code'].map(stock_names)
        
        # 选取 Top N
        selected = df.head(self.config.FINAL_TOP_N).copy()
        
        print(f"\n✅ 最终选中 {len(selected)} 只股票")
        
        return selected
    
    def _save_results(self, output_path: Path):
        """保存结果到 CSV
        
        输出格式（与现有 sse_pick.csv 看齐）：
        - con_code: 股票代码（带后缀，如 600519.SH）
        - stock_name: 股票中文名称
        
        Args:
            output_path: 输出文件路径
        """
        if self.selected_stocks is None or len(self.selected_stocks) == 0:
            print("⚠️ 没有选中的股票，跳过保存")
            return
        
        # 只保留需要的列，列名改为 con_code（与 sse_pick.csv 格式一致）
        output_df = self.selected_stocks[['ts_code', 'stock_name']].copy()
        output_df.columns = ['con_code', 'stock_name']
        
        # 保存 CSV（UTF-8 with BOM，兼容 Excel）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"\n💾 结果已保存：{output_path}")
    
    def _print_details(self):
        """打印选股详细信息"""
        if self.selected_stocks is None or len(self.selected_stocks) == 0:
            print("\n⚠️ 本次选股结果为空")
            return
        
        print("\n" + "=" * 60)
        print("📋 选股结果详情")
        print("=" * 60)
        
        # 打印选中的股票及其因子值
        display_df = self.selected_stocks.copy()
        
        # 格式化数值列
        for col in ['residual_vol_252d', 'momentum_5d', 'beta_20d', 'momentum_10d']:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: '{:.4f}'.format(x) if pd.notna(x) else 'N/A')
        
        if 'turnover_5d' in display_df.columns:
            display_df['turnover_5d'] = display_df['turnover_5d'].apply(lambda x: '{:.0f}'.format(x) if pd.notna(x) else 'N/A')
        
        # 打印表格
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 20)
        
        print(display_df.to_string(index=False))
        
        print("\n" + "=" * 60)
        print("✅ 选股策略执行完成")
        print("=" * 60)


def main():
    """主函数 - 支持命令行参数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A股选股策略")
    parser.add_argument("--date", type=str, help="选股日期 YYYYMMDD 或 YYYY-MM-DD")
    args = parser.parse_args()
    
    selector = StockSelector()
    result = selector.select_stocks(selection_date=args.date)
    return result


if __name__ == "__main__":
    main()
