"""
选股策略配置
Stock Selection Configuration
"""
from pathlib import Path
from typing import Optional


# 容器内数据目录（通过 volume mount 挂载持久化数据）
# 宿主机持久化目录会被挂载到此路径
DATA_DIR = Path("/home/ec2-user/AI-Trader/data/A_stock")


class SelectionConfig:
    """选股策略配置参数"""
    
    def __init__(self):
        # 中证 1000 指数代码
        self.INDEX_CODE = "000852.SH"
        
        # 因子计算参数
        self.RESIDUAL_VOL_WINDOW = 252      # 残差收益波动率窗口（交易日，约 1 年）
        self.TURNOVER_WINDOW = 5            # 评价换手率窗口（交易日）
        self.MOMENTUM_SHORT_WINDOW = 5      # 短期动量窗口（交易日）
        self.BETA_WINDOW = 20               # Beta 值计算窗口（交易日）
        self.MOMENTUM_RANK_WINDOW = 10      # 排序动量窗口（交易日）
        
        # 筛选比例（百分位）
        self.RESIDUAL_VOL_PERCENTILE = 0.5    # 残差波动率：前 50%（越低越好）
        self.TURNOVER_PERCENTILE = 0.5        # 换手率：前 50%（越高越好）
        self.MOMENTUM_PERCENTILE = 0.7        # 5 日动量：前 30%（越高越好）
        self.BETA_PERCENTILE = 0.7            # 20 日 Beta：前 30%（越高越好）
        
        # 最终选取数量
        self.FINAL_TOP_N = 10               # 按 10 日动量排序选取 Top N（可以少于 10 或没有）
        
        # 输出配置 - 容器内数据目录
        self.OUTPUT_DIR = DATA_DIR
        self.OUTPUT_FILENAME_PREFIX = "sse_pick_"   # 输出文件名前缀
        self.OUTPUT_FILENAME_SUFFIX = ".csv"        # 输出文件后缀
        
        # 数据路径 - 容器内目录
        self.PRICE_DATA_PATH = DATA_DIR / "zz1000_merged.jsonl"
        self.BENCHMARK_DATA_PATH = None  # 基准指数数据路径（可选，默认从 Tushare 获取）
        
        # 日志配置
        self.VERBOSE = True                # 是否打印详细信息
        
        # API 配置
        self.API_RETRY_TIMES = 3           # API 重试次数
        self.API_RETRY_DELAY = 2           # API 重试延迟（秒）
        
        # 确保输出目录存在
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    def get_output_filename(self, date):
        """生成输出文件名"""
        if '-' in str(date):
            date = str(date).replace('-', '')
        return "{}{}{}".format(
            self.OUTPUT_FILENAME_PREFIX,
            date,
            self.OUTPUT_FILENAME_SUFFIX
        )
    
    def get_output_path(self, date):
        """生成输出文件完整路径"""
        return self.OUTPUT_DIR / self.get_output_filename(date)


# 默认配置实例
DEFAULT_CONFIG = SelectionConfig()
