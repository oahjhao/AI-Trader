"""
因子计算器
Factor Calculator for Stock Selection
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Optional


class FactorCalculator:
    """因子计算器
    
    计算选股所需的 5 个因子：
    1. 252 日残差收益波动率（越低越好）
    2. 5 日评价换手率（越高越好）
    3. 5 日价格动量（越高越好）
    4. 20 日 Beta 值（越高越好）
    5. 10 日价格动量（用于最终排序，越低越好）
    """
    
    def __init__(self, price_data: pd.DataFrame, benchmark_data: pd.DataFrame):
        """初始化因子计算器
        
        Args:
            price_data: 个股价格数据
                columns: ts_code, trade_date, open, high, low, close, vol
            benchmark_data: 基准指数数据（中证 1000）
                columns: ts_code, trade_date, close, open, high, low, vol
        """
        self.price_data = price_data.copy()
        self.benchmark_data = benchmark_data.copy()
        
        # 预处理：转换日期格式为 datetime
        if self.price_data['trade_date'].dtype == 'object':
            self.price_data['trade_date'] = pd.to_datetime(
                self.price_data['trade_date'], format='%Y%m%d', errors='coerce'
            )
        
        if self.benchmark_data['trade_date'].dtype == 'object':
            self.benchmark_data['trade_date'] = pd.to_datetime(
                self.benchmark_data['trade_date'], format='%Y%m%d', errors='coerce'
            )
        
        # 排序
        self.price_data = self.price_data.sort_values(['ts_code', 'trade_date'])
        self.benchmark_data = self.benchmark_data.sort_values('trade_date')
    
    def calculate_residual_volatility(self, stock_code: str, window: int = 252) -> float:
        """计算 252 日残差收益波动率
        
        使用 CAPM 模型计算个股收益率相对于市场收益率的残差波动率
        
        Args:
            stock_code: 股票代码（带后缀，如 '600519.SH'）
            window: 计算窗口（交易日数，默认 252 约 1 年）
            
        Returns:
            残差收益波动率（年化），计算失败返回 np.nan
        """
        try:
            # 获取个股数据
            stock_df = self.price_data[self.price_data['ts_code'] == stock_code].copy()
            if len(stock_df) < window:
                return np.nan
            
            # 计算日收益率
            stock_df = stock_df.sort_values('trade_date')
            stock_df['return'] = stock_df['close'].pct_change()
            
            # 获取指数数据
            bench_df = self.benchmark_data.copy()
            bench_df = bench_df.sort_values('trade_date')
            bench_df['return_bench'] = bench_df['close'].pct_change()
            
            # 合并数据
            merged = pd.merge(
                stock_df[['trade_date', 'return']],
                bench_df[['trade_date', 'return_bench']],
                on='trade_date',
                how='inner'
            )
            
            if len(merged) < window:
                return np.nan
            
            # 取最近 window 天
            recent = merged.tail(window).dropna()
            
            if len(recent) < window * 0.8:  # 至少 80% 数据有效
                return np.nan
            
            # 填充 NaN 值
            recent = recent.fillna(0)
            
            # CAPM 回归：r_stock = alpha + beta * r_bench + epsilon
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                recent['return_bench'].values,
                recent['return'].values
            )
            
            # 计算残差
            recent['predicted'] = slope * recent['return_bench'] + intercept
            recent['residual'] = recent['return'] - recent['predicted']
            
            # 残差波动率（年化）
            residual_vol = recent['residual'].std() * np.sqrt(252)
            
            return residual_vol
            
        except Exception as e:
            return np.nan
    
    def calculate_turnover_rate(self, stock_code: str, window: int = 5) -> float:
        """计算 5 日评价换手率
        
        简化计算：使用成交量的均值作为换手率的代理指标
        
        Args:
            stock_code: 股票代码
            window: 计算窗口（交易日数）
            
        Returns:
            平均换手率（成交量均值），计算失败返回 np.nan
        """
        try:
            stock_df = self.price_data[self.price_data['ts_code'] == stock_code].copy()
            if len(stock_df) < window:
                return np.nan
            
            stock_df = stock_df.sort_values('trade_date').tail(window)
            
            # 计算平均成交量（手）
            avg_turnover = stock_df['vol'].mean()
            
            return avg_turnover if pd.notna(avg_turnover) else np.nan
            
        except Exception as e:
            return np.nan
    
    def calculate_momentum(self, stock_code: str, window: int = 5) -> float:
        """计算 N 日价格动量
        
        动量 = (当前价格 - N 日前价格) / N 日前价格
        
        Args:
            stock_code: 股票代码
            window: 动量计算窗口（交易日数）
            
        Returns:
            价格动量（收益率），计算失败返回 np.nan
        """
        try:
            stock_df = self.price_data[self.price_data['ts_code'] == stock_code].copy()
            if len(stock_df) < window + 1:
                return np.nan
            
            stock_df = stock_df.sort_values('trade_date').tail(window + 1)
            
            start_price = stock_df['close'].iloc[0]
            end_price = stock_df['close'].iloc[-1]
            
            if start_price == 0 or pd.isna(start_price) or pd.isna(end_price):
                return np.nan
            
            momentum = (end_price - start_price) / start_price
            return momentum
            
        except Exception as e:
            return np.nan
    
    def calculate_beta(self, stock_code: str, window: int = 20) -> float:
        """计算 20 日 Beta 值
        
        Beta = Cov(r_stock, r_bench) / Var(r_bench)
        
        Args:
            stock_code: 股票代码
            window: 计算窗口（交易日数）
            
        Returns:
            Beta 值，计算失败返回 np.nan
        """
        try:
            # 获取个股数据
            stock_df = self.price_data[self.price_data['ts_code'] == stock_code].copy()
            if len(stock_df) < window:
                return np.nan
            
            stock_df = stock_df.sort_values('trade_date')
            stock_df['return'] = stock_df['close'].pct_change()
            
            # 获取指数数据
            bench_df = self.benchmark_data.copy()
            bench_df = bench_df.sort_values('trade_date')
            bench_df['return_bench'] = bench_df['close'].pct_change()
            
            # 合并数据
            merged = pd.merge(
                stock_df[['trade_date', 'return']],
                bench_df[['trade_date', 'return_bench']],
                on='trade_date',
                how='inner'
            )
            
            if len(merged) < window:
                return np.nan
            
            # 取最近 window 天
            recent = merged.tail(window).dropna()
            
            if len(recent) < window * 0.8:
                return np.nan
            
            # 计算 Beta
            covariance = recent['return'].cov(recent['return_bench'])
            variance = recent['return_bench'].var()
            
            if variance == 0 or pd.isna(variance) or pd.isna(covariance):
                return np.nan
            
            beta = covariance / variance
            return beta
            
        except Exception as e:
            return np.nan
    
    def calculate_all_factors(self, stock_codes: list, verbose: bool = True) -> pd.DataFrame:
        """批量计算所有股票的所有因子
        
        Args:
            stock_codes: 股票代码列表
            verbose: 是否打印进度
            
        Returns:
            DataFrame with columns:
            - ts_code: 股票代码
            - residual_vol_252d: 252 日残差收益波动率
            - turnover_5d: 5 日评价换手率
            - momentum_5d: 5 日价格动量
            - beta_20d: 20 日 Beta 值
            - momentum_10d: 10 日价格动量（用于排序）
        """
        print(f"🔢 开始计算 {len(stock_codes)} 只股票的因子...")
        
        factor_data = []
        
        for i, stock_code in enumerate(stock_codes):
            if verbose and (i + 1) % 100 == 0:
                print(f"  进度：{i + 1}/{len(stock_codes)} ({(i + 1) / len(stock_codes) * 100:.1f}%)")
            
            factors = {
                'ts_code': stock_code,
                'residual_vol_252d': self.calculate_residual_volatility(
                    stock_code, window=252  # 使用 252 日窗口（约 1 年）
                ),
                'turnover_5d': self.calculate_turnover_rate(
                    stock_code, window=5
                ),
                'momentum_5d': self.calculate_momentum(
                    stock_code, window=5
                ),
                'beta_20d': self.calculate_beta(
                    stock_code, window=20
                ),
                'momentum_10d': self.calculate_momentum(
                    stock_code, window=10
                )
            }
            
            factor_data.append(factors)
        
        df = pd.DataFrame(factor_data)
        
        if verbose:
            print(f"✅ 因子计算完成")
            print(f"   有效数据：{df.notna().sum().to_dict()}")
        
        return df
