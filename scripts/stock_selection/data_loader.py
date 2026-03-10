"""
数据加载器 (Tushare 优化版)
Data Loader for A-Share Stock Selection using Tushare

优化:
- 添加重试机制
- 批量获取数据
- 缩短数据窗口要求
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

# 添加当前目录到 Python 路径，支持直接运行和模块导入
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

try:
    from config import SelectionConfig
except ImportError:
    from .config import SelectionConfig

load_dotenv()


class DataLoader:
    """数据加载器 (Tushare 优化版)"""
    
    def __init__(self, config: Optional[SelectionConfig] = None):
        """初始化数据加载器"""
        self.config = config or SelectionConfig()
        self.token = os.getenv("TUSHARE_TOKEN")
        
        if not self.token:
            raise ValueError("TUSHARE_TOKEN 环境变量未设置")
        
        ts.set_token(self.token)
        self.pro = ts.pro_api()
        
        # 设置超时
        if hasattr(self.pro, 'api') and hasattr(self.pro.api, 'timeout'):
            self.pro.api.timeout = 120
    
    def _api_call_with_retry(self, api_func, max_retries=None, **kwargs):
        """API 调用带重试机制"""
        if max_retries is None:
            max_retries = self.config.API_RETRY_TIMES
        
        for attempt in range(1, max_retries + 1):
            try:
                result = api_func(**kwargs)
                return result
            except Exception as e:
                if attempt < max_retries:
                    wait_time = self.config.API_RETRY_DELAY * attempt
                    print(f"⚠️ API 调用失败 (尝试 {attempt}/{max_retries})，等待 {wait_time} 秒后重试...")
                    print(f"   错误：{str(e)[:100]}")
                    time.sleep(wait_time)
                else:
                    print(f"❌ API 调用失败，已达到最大重试次数")
                    raise
    
    def get_constituents(self, date: Optional[str] = None) -> List[str]:
        """获取中证 1000 成分股列表"""
        today = datetime.now()
        
        if date is None:
            # 使用最近 30 天的范围
            start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")
        else:
            if '-' in date:
                date = date.replace('-', '')
            dt = datetime.strptime(date, "%Y%m%d")
            # 使用选股日期往前推 30 天的范围
            start_date = (dt - timedelta(days=30)).strftime("%Y%m%d")
            end_date = dt.strftime("%Y%m%d")
        
        print(f"📊 获取中证 1000 成分股 ({start_date} - {end_date})...")
        
        try:
            df = self._api_call_with_retry(
                self.pro.index_weight,
                index_code=self.config.INDEX_CODE,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                print(f"⚠️ 未获取到成分股数据，尝试使用最近一个月")
                end_date = today.strftime("%Y%m%d")
                start_date = (today - timedelta(days=30)).strftime("%Y%m%d")
                df = self._api_call_with_retry(
                    self.pro.index_weight,
                    index_code=self.config.INDEX_CODE,
                    start_date=start_date,
                    end_date=end_date
                )
            
            if df.empty:
                raise ValueError("无法获取中证 1000 成分股数据")
            
            constituents = df['con_code'].unique().tolist()
            print(f"✅ 获取到 {len(constituents)} 只成分股")
            
            return constituents
            
        except Exception as e:
            print(f"❌ 获取成分股失败：{e}")
            raise
    
    def get_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """获取股票中文名称"""
        print(f"📝 获取 {len(stock_codes)} 只股票名称...")
        
        try:
            df = self._api_call_with_retry(
                self.pro.stock_basic,
                exchange='',
                list_status='L',
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            
            name_map = dict(zip(df['ts_code'], df['name']))
            result = {code: name_map.get(code, "Unknown") for code in stock_codes}
            
            print(f"✅ 获取到 {len(result)} 只股票名称")
            return result
            
        except Exception as e:
            print(f"⚠️ 获取股票名称失败：{e}，使用默认名称")
            return {code: f"股票{code[:6]}" for code in stock_codes}
    
    def load_price_data(self, stock_codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """从 Tushare API 加载个股日线价格数据
        
        注意：Tushare 批量查询会限制每只股票返回的记录数，因此采用单只股票获取策略
        """
        print(f"📈 从 Tushare API 获取 {len(stock_codes)} 只股票日线数据 ({start_date} - {end_date})...")
        print(f"⚠️  采用单只股票获取模式（确保每只股票数据完整）...")
        
        all_data = []
        
        for i, stock_code in enumerate(stock_codes):
            try:
                df = self._api_call_with_retry(
                    self.pro.daily,
                    ts_code=stock_code,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if not df.empty:
                    all_data.append(df)
                    
                    # 每 100 只股票显示进度
                    if (i + 1) % 100 == 0:
                        print(f"  进度：{i + 1}/{len(stock_codes)} ({(i + 1) / len(stock_codes) * 100:.1f}%)")
                
            except Exception as e:
                print(f"⚠️ 股票 {stock_code} 获取失败：{e}")
            
            # 避免 API 限流：每 10 只股票暂停 0.1 秒
            if (i + 1) % 10 == 0:
                time.sleep(0.1)
        
        if not all_data:
            raise ValueError("未能获取到任何价格数据")
        
        df_all = pd.concat(all_data, ignore_index=True)
        
        # 统计每只股票的数据条数
        stock_counts = df_all.groupby('ts_code').size()
        min_count = stock_counts.min()
        max_count = stock_counts.max()
        avg_count = stock_counts.mean()
        
        print(f"✅ 获取到 {len(df_all)} 条价格记录，{df_all['ts_code'].nunique()} 只股票")
        print(f"   每只股票数据条数：最小={min_count}, 最大={max_count}, 平均={avg_count:.0f}")
        
        return df_all
    
    def load_benchmark_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """加载基准指数（中证 1000）日线数据"""
        print(f"📊 获取中证 1000 指数数据 ({start_date} - {end_date})...")
        
        try:
            df = self._api_call_with_retry(
                self.pro.index_daily,
                ts_code=self.config.INDEX_CODE,
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                raise ValueError("未能获取到指数数据")
            
            print(f"✅ 获取到 {len(df)} 条指数记录")
            return df
            
        except Exception as e:
            print(f"❌ 获取指数数据失败：{e}")
            raise
    
    def load_price_data_from_jsonl(self, jsonl_path: Optional[Path] = None, 
                                   required_stocks: Optional[List[str]] = None) -> Tuple[pd.DataFrame, bool]:
        """从 JSONL 文件加载价格数据"""
        if jsonl_path is None:
            jsonl_path = self.config.PRICE_DATA_PATH
        
        if not jsonl_path.exists():
            print(f"⚠️ JSONL 文件不存在：{jsonl_path}")
            return pd.DataFrame(), False
        
        print(f"📂 从 JSONL 加载价格数据：{jsonl_path}...")
        
        records = []
        stock_count = 0
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line)
                    meta = data.get('Meta Data', {})
                    symbol = meta.get('2. Symbol', '')
                    time_series = data.get('Time Series (Daily)', {})
                    
                    for date_str, prices in time_series.items():
                        trade_date = date_str.replace('-', '')
                        
                        records.append({
                            'ts_code': symbol,
                            'trade_date': trade_date,
                            'open': float(prices.get('1. buy price', 0)),
                            'high': float(prices.get('2. high', 0)),
                            'low': float(prices.get('3. low', 0)),
                            'close': float(prices.get('4. sell price', 0)),
                            'vol': int(float(prices.get('5. volume', 0)))
                        })
                    
                    stock_count += 1
                    if stock_count % 100 == 0:
                        print(f"  已读取 {stock_count} 只股票...")
                        
                except Exception as e:
                    continue
        
        if not records:
            return pd.DataFrame(), False
        
        df = pd.DataFrame(records)
        unique_stocks = df['ts_code'].nunique()
        
        coverage_ok = True
        if required_stocks:
            coverage = unique_stocks / len(required_stocks)
            if coverage < 0.9:
                print(f"⚠️ JSONL 数据覆盖率不足：{unique_stocks}/{len(required_stocks)} ({coverage*100:.1f}%)")
                coverage_ok = False
            else:
                print(f"✅ JSONL 数据覆盖率：{unique_stocks}/{len(required_stocks)} ({coverage*100:.1f}%)")
        
        print(f"✅ 加载到 {len(df)} 条价格记录，{unique_stocks} 只股票")
        return df, coverage_ok
