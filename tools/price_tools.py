import os

from dotenv import load_dotenv

load_dotenv()
import json
import sys
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 将项目根目录加入 Python 路径，便于从子目录直接运行本文件
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from tools.general_tools import get_config_value


def get_market_type() -> str:
    """
    智能获取市场类型，支持多种检测方式：
    1. 优先从配置中读取 MARKET
    2. 如果未设置，则根据 LOG_PATH 推断（agent_data_astock -> cn, agent_data_crypto -> crypto, agent_data -> us）
    3. 最后默认为 us

    Returns:
        "cn" for A-shares market, "us" for US market, "crypto" for cryptocurrency market
    """
    # 方式1: 从配置读取
    market = get_config_value("MARKET", None)
    if market in ["cn", "us", "crypto"]:
        return market

    # 方式2: 根据 LOG_PATH 推断
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if "astock" in log_path.lower() or "a_stock" in log_path.lower():
        return "cn"
    elif "crypto" in log_path.lower():
        return "crypto"

    # 方式3: 默认为美股
    return "us"


all_nasdaq_100_symbols = [
    "NVDA",
    "MSFT",
    "AAPL",
    "GOOG",
    "GOOGL",
    "AMZN",
    "META",
    "AVGO",
    "TSLA",
    "NFLX",
    "PLTR",
    "COST",
    "ASML",
    "AMD",
    "CSCO",
    "AZN",
    "TMUS",
    "MU",
    "LIN",
    "PEP",
    "SHOP",
    "APP",
    "INTU",
    "AMAT",
    "LRCX",
    "PDD",
    "QCOM",
    "ARM",
    "INTC",
    "BKNG",
    "AMGN",
    "TXN",
    "ISRG",
    "GILD",
    "KLAC",
    "PANW",
    "ADBE",
    "HON",
    "CRWD",
    "CEG",
    "ADI",
    "ADP",
    "DASH",
    "CMCSA",
    "VRTX",
    "MELI",
    "SBUX",
    "CDNS",
    "ORLY",
    "SNPS",
    "MSTR",
    "MDLZ",
    "ABNB",
    "MRVL",
    "CTAS",
    "TRI",
    "MAR",
    "MNST",
    "CSX",
    "ADSK",
    "PYPL",
    "FTNT",
    "AEP",
    "WDAY",
    "REGN",
    "ROP",
    "NXPI",
    "DDOG",
    "AXON",
    "ROST",
    "IDXX",
    "EA",
    "PCAR",
    "FAST",
    "EXC",
    "TTWO",
    "XEL",
    "ZS",
    "PAYX",
    "WBD",
    "BKR",
    "CPRT",
    "CCEP",
    "FANG",
    "TEAM",
    "CHTR",
    "KDP",
    "MCHP",
    "GEHC",
    "VRSK",
    "CTSH",
    "CSGP",
    "KHC",
    "ODFL",
    "DXCM",
    "TTD",
    "ON",
    "BIIB",
    "LULU",
    "CDW",
    "GFS",
]

all_sse_50_symbols = [
    "600519.SH",
    "601318.SH",
    "600036.SH",
    "601899.SH",
    "600900.SH",
    "601166.SH",
    "600276.SH",
    "600030.SH",
    "603259.SH",
    "688981.SH",
    "688256.SH",
    "601398.SH",
    "688041.SH",
    "601211.SH",
    "601288.SH",
    "601328.SH",
    "688008.SH",
    "600887.SH",
    "600150.SH",
    "601816.SH",
    "601127.SH",
    "600031.SH",
    "688012.SH",
    "603501.SH",
    "601088.SH",
    "600309.SH",
    "601601.SH",
    "601668.SH",
    "603993.SH",
    "601012.SH",
    "601728.SH",
    "600690.SH",
    "600809.SH",
    "600941.SH",
    "600406.SH",
    "601857.SH",
    "601766.SH",
    "601919.SH",
    "600050.SH",
    "600760.SH",
    "601225.SH",
    "600028.SH",
    "601988.SH",
    "688111.SH",
    "601985.SH",
    "601888.SH",
    "601628.SH",
    "601600.SH",
    "601658.SH",
    "600048.SH",
]

all_spif_symbols = [
    # "510050.SH",
    # "512100.SH",
    # "588000.SH",
    # "688256.SH",
    # "600519.SH",
    # "601288.SH",
    # "300059.SZ",
    "300274.SZ",
]

def load_stock_list(init_date: Optional[str] = None, base_dir: Optional[str] = None) -> List[str]:
    """加载股票列表
    
    根据 init_date 自动选择带日期后缀的股票列表文件。
    优先级：sse_pick_YYYYMMDD.csv > sse_pick.csv
    
    Args:
        init_date: 初始日期（格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS），
                   用于生成日期后缀 YYYYMMDD
        base_dir: 基础目录，默认自动检测 EFS 或本地路径
    
    Returns:
        List[str]: 股票代码列表
    """
    import os
    
    # 路径自适配：检测 EFS 挂载或使用本地路径
    if base_dir is None:
        if Path("/mnt/efs/ai-trader/data/A_stock").exists():
            base_dir = "/mnt/efs/ai-trader/data/A_stock"
        else:
            base_dir = "/home/ec2-user/AI-Trader/data/A_stock"
    
    base_path = Path(base_dir)
    
    # 构建文件路径
    date_suffix = None
    
    # 优先从环境变量读取 DATE_SUFFIX
    if os.getenv("DATE_SUFFIX"):
        date_suffix = os.getenv("DATE_SUFFIX")
        print(f"📅 从环境变量读取 DATE_SUFFIX: {date_suffix}")
    elif init_date:
        # 提取日期部分并转换为 YYYYMMDD 格式
        date_only = init_date.split()[0] if ' ' in init_date else init_date
        date_suffix = date_only.replace('-', '').replace(':', '')[:8]
        print(f"📅 从 init_date 提取 DATE_SUFFIX: {date_suffix}")
    
    if date_suffix:
        stock_list_path = base_path / f"sse_pick_{date_suffix}.csv"
        
        # 严格使用 date_suffix，不回退
        if not stock_list_path.exists():
            raise FileNotFoundError(
                f"带日期后缀的股票列表文件不存在: {stock_list_path}\n"
                f"请确保已生成对应日期的配置文件。"
            )
    else:
        stock_list_path = base_path / "sse_pick.csv"
    
    if not stock_list_path.exists():
        raise FileNotFoundError(f"股票列表文件不存在: {stock_list_path}")
    
    print(f"从 {stock_list_path} 加载股票列表")
    df = pd.read_csv(stock_list_path)
    
    # 从 con_code 列提取唯一的股票代码
    if "con_code" not in df.columns:
        raise ValueError(f"文件 {stock_list_path} 中缺少 'con_code' 列")
    
    stock_list = df["con_code"].unique()
    
    # 去除 .SH 或 .SZ 后缀
    # stock_list = [code.replace(".SH", "").replace(".SZ", "") for code in stock_list]
    
    print(f"成功加载 {len(stock_list)} 只股票")
    print(f"股票列表: {stock_list[:5]}..." if len(stock_list) > 5 else f"股票列表: {stock_list}")
    
    return stock_list

def _to_hourly_merged_path(merged_file: Path) -> Path:
    """Convert daily merged file path to hourly merged file path.
    
    merged_20260202.jsonl -> merged_hourly_20260202.jsonl
    merged.jsonl -> merged_hourly.jsonl
    crypto_merged_20260202.jsonl -> crypto_merged_hourly_20260202.jsonl
    """
    hourly_name = merged_file.name.replace('merged', 'merged_hourly', 1)
    return merged_file.with_name(hourly_name)


def get_merged_file_path(market: str = "us", date_suffix: Optional[str] = None) -> Path:
    """Get merged.jsonl path based on market type.

    Args:
        market: Market type, "us" for US stocks, "cn" for A-shares, "crypto" for cryptocurrencies
        date_suffix: Optional date suffix (YYYYMMDD format) for data isolation.
                     If not provided, will try to read from DATE_SUFFIX environment variable.

    Returns:
        Path object pointing to the merged.jsonl file (with date suffix if applicable)
    """
    import os
    
    # Try to get date suffix from environment if not provided
    if date_suffix is None:
        date_suffix = os.getenv("DATE_SUFFIX")
    
    base_dir = Path(__file__).resolve().parents[1]
    
    if market == "cn":
        base_path = base_dir / "data" / "A_stock"
        # Check for EFS mount
        efs_path = Path("/mnt/efs/ai-trader/data/A_stock")
        if efs_path.exists():
            base_path = efs_path
        
        if date_suffix:
            filename = f"merged_{date_suffix}.jsonl"
        else:
            filename = "merged.jsonl"
        return base_path / filename
    elif market == "crypto":
        base_path = base_dir / "data" / "crypto"
        efs_path = Path("/mnt/efs/ai-trader/data/crypto")
        if efs_path.exists():
            base_path = efs_path
        
        if date_suffix:
            filename = f"crypto_merged_{date_suffix}.jsonl"
        else:
            filename = "crypto_merged.jsonl"
        return base_path / filename
    else:
        base_path = base_dir / "data"
        efs_path = Path("/mnt/efs/ai-trader/data")
        if efs_path.exists():
            base_path = efs_path
        
        if date_suffix:
            filename = f"merged_{date_suffix}.jsonl"
        else:
            filename = "merged.jsonl"
        return base_path / filename


def is_trading_day(date: str, market: str = "us") -> bool:
    """Check if a given date is a trading day by looking up merged.jsonl.

    Args:
        date: Date string in "YYYY-MM-DD" format
        market: Market type ("us", "cn", or "crypto")

    Returns:
        True if the date exists in merged.jsonl (is a trading day), False otherwise
    """
    # MVP assumption: crypto trades every day
    if market == "crypto":
        return True

    merged_file_path = get_merged_file_path(market)

    if not merged_file_path.exists():
        print(f"⚠️  Warning: {merged_file_path} not found, cannot validate trading day")
        return False

    try:
        with open(merged_file_path, "r", encoding="utf-8") as f:
            # Read first line to check if date exists
            for line in f:
                try:
                    data = json.loads(line.strip())
                    # Check for daily time series first
                    time_series = data.get("Time Series (Daily)", {})
                    if date in time_series:
                        return True

                    # If no daily data, check for hourly data (e.g., "Time Series (60min)")
                    for key, value in data.items():
                        if key.startswith("Time Series") and isinstance(value, dict):
                            # Check if any hourly timestamp starts with the date
                            for timestamp in value.keys():
                                if timestamp.startswith(date):
                                    return True
                except json.JSONDecodeError:
                    continue
            # If we get here, checked all stocks and date was not found in any
            return False
    except Exception as e:
        print(f"⚠️  Error checking trading day: {e}")
        return False


def get_all_trading_days(market: str = "us") -> List[str]:
    """Get all available trading days from merged.jsonl.

    Args:
        market: Market type ("us" or "cn")

    Returns:
        Sorted list of trading dates in "YYYY-MM-DD" format
    """
    merged_file_path = get_merged_file_path(market)

    if not merged_file_path.exists():
        print(f"⚠️  Warning: {merged_file_path} not found")
        return []

    trading_days = set()
    try:
        with open(merged_file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    time_series = data.get("Time Series (Daily)", {})
                    # Add all dates from this stock's time series
                    trading_days.update(time_series.keys())
                except json.JSONDecodeError:
                    continue
        return sorted(list(trading_days))
    except Exception as e:
        print(f"⚠️  Error reading trading days: {e}")
        return []


def get_stock_name_mapping(market: str = "us") -> Dict[str, str]:
    """Get mapping from stock symbols to names.

    Args:
        market: Market type ("us" or "cn")

    Returns:
        Dictionary mapping symbols to names, e.g. {"600519.SH": "贵州茅台"}
    """
    merged_file_path = get_merged_file_path(market)

    if not merged_file_path.exists():
        return {}

    name_map = {}
    try:
        with open(merged_file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    meta = data.get("Meta Data", {})
                    symbol = meta.get("2. Symbol")
                    name = meta.get("2.1. Name", "")
                    if symbol and name:
                        name_map[symbol] = name
                except json.JSONDecodeError:
                    continue
        return name_map
    except Exception as e:
        print(f"⚠️  Error reading stock names: {e}")
        return {}


def format_price_dict_with_names(
    price_dict: Dict[str, Optional[float]], market: str = "us"
) -> Dict[str, Optional[float]]:
    """Format price dictionary to include stock names for display.

    Args:
        price_dict: Original price dictionary with keys like "600519.SH_price"
        market: Market type ("us" or "cn")

    Returns:
        New dictionary with keys like "600519.SH (贵州茅台)_price" for CN market,
        unchanged for US market
    """
    if market != "cn":
        return price_dict

    name_map = get_stock_name_mapping(market)
    if not name_map:
        return price_dict

    formatted_dict = {}
    for key, value in price_dict.items():
        if key.endswith("_price"):
            symbol = key[:-6]  # Remove "_price" suffix
            stock_name = name_map.get(symbol, "")
            if stock_name:
                new_key = f"{symbol} ({stock_name})_price"
            else:
                new_key = key
            formatted_dict[new_key] = value
        else:
            formatted_dict[key] = value

    return formatted_dict


def get_yesterday_date(today_date: str, merged_path: Optional[str] = None, market: str = "us") -> str:
    """
    获取输入日期的上一个交易日或时间点。
    从 merged.jsonl 读取所有可用的交易时间，然后找到 today_date 的上一个时间。
    
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS。
        merged_path: 可选，自定义 merged.jsonl 路径；默认根据 market 参数读取对应市场的 merged.jsonl。
        market: 市场类型，"us" 为美股，"cn" 为A股

    Returns:
        yesterday_date: 上一个交易日或时间点的字符串，格式与输入一致。
    """
    
    # 获取 merged.jsonl 文件路径
    if merged_path is None:
        merged_file = get_merged_file_path(market)
    else:
        merged_file = Path(merged_path)

    # 解析输入日期/时间
    if ' ' in today_date:
        input_dt = datetime.strptime(today_date, "%Y-%m-%d %H:%M:%S")
        date_only = False
        merged_file = _to_hourly_merged_path(merged_file)
    else:
        input_dt = datetime.strptime(today_date, "%Y-%m-%d")
        date_only = True
    
    if not merged_file.exists():
        # 如果文件不存在，根据输入类型回退
        print(f"merged.jsonl file does not exist at {merged_file}")
        if date_only:
            yesterday_dt = input_dt - timedelta(days=1)
            while yesterday_dt.weekday() >= 5:
                yesterday_dt -= timedelta(days=1)
            return yesterday_dt.strftime("%Y-%m-%d")
        else:
            yesterday_dt = input_dt - timedelta(hours=1)
            return yesterday_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 从 merged.jsonl 读取所有可用的交易时间
    all_timestamps = set()
    
    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                # 查找所有以 "Time Series" 开头的键
                for key, value in doc.items():
                    if key.startswith("Time Series"):
                        if isinstance(value, dict):
                            all_timestamps.update(value.keys())
                        break
            except Exception:
                continue
    
    if not all_timestamps:
        # 如果没有找到任何时间戳，根据输入类型回退
        if date_only:
            yesterday_dt = input_dt - timedelta(days=1)
            while yesterday_dt.weekday() >= 5:
                yesterday_dt -= timedelta(days=1)
            return yesterday_dt.strftime("%Y-%m-%d")
        else:
            yesterday_dt = input_dt - timedelta(hours=1)
            return yesterday_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 将所有时间戳转换为 datetime 对象，并找到小于 today_date 的最大时间戳
    if date_only:
        all_timestamps = [datetime.strptime(ts, '%Y-%m-%d') for ts in all_timestamps]
        sorted_timestamps = sorted(all_timestamps, key=lambda x: x)
        previous_timestamp = None
        for ts_dt in sorted_timestamps:
            try:
                # print(f"get_yesterday_date:ts_dt vs input_dt:{ts_dt} {type(ts_dt)} {input_dt} {type(input_dt)} ")
                if ts_dt < input_dt:
                    if previous_timestamp is None or ts_dt > previous_timestamp:
                        previous_timestamp = ts_dt
            except Exception:
                continue
    else:
        all_timestamps = [datetime.strptime(ts, '%Y-%m-%d %H:%M:%S') for ts in all_timestamps]
        sorted_timestamps = sorted(all_timestamps, key=lambda x: x)
        previous_timestamp = None
        for ts_dt in sorted_timestamps:
            try:
                # print(f"get_yesterday_date:ts_dt vs input_dt:{ts_dt} {type(ts_dt)} {input_dt} {type(input_dt)} ")
                if ts_dt <= input_dt:
                    if previous_timestamp is None or ts_dt > previous_timestamp:
                        previous_timestamp = ts_dt
            except Exception:
                continue
    
    # print(f"get_yesterday_date:sorted_timestamps:{sorted_timestamps}")
    # print(f"get_yesterday_date:previous_timestamp:{previous_timestamp}")
    # 如果没有找到更早的时间戳，根据输入类型回退
    if previous_timestamp is None:
        if date_only:
            yesterday_dt = input_dt - timedelta(days=1)
            while yesterday_dt.weekday() >= 5:
                yesterday_dt -= timedelta(days=1)
            # print(f"get_yesterday_date:previous_timestamp:{yesterday_dt.strftime("%Y-%m-%d")}")
            return yesterday_dt.strftime("%Y-%m-%d")
        else:
            yesterday_dt = input_dt - timedelta(hours=1)
            # print(f"get_yesterday_date:previous_timestamp:{yesterday_dt.strftime("%Y-%m-%d %H:%M:%S")}")
            return yesterday_dt.strftime("%Y-%m-%d %H:%M:%S")

    # 返回结果
    if date_only:
        return previous_timestamp.strftime("%Y-%m-%d")
    else:
        return previous_timestamp.strftime("%Y-%m-%d %H:%M:%S")



def get_open_prices(
    today_date: str, symbols: List[str], merged_path: Optional[str] = None, market: str = "us"
) -> Dict[str, Optional[float]]:
    """从 data/merged.jsonl 中读取指定日期与标的的开盘价。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD或YYYY-MM-DD HH:MM:SS。
        symbols: 需要查询的股票代码列表。
        merged_path: 可选，自定义 merged.jsonl 路径；默认读取项目根目录下 data/merged.jsonl。
        market: 市场类型，"us" 为美股，"cn" 为A股

    Returns:
        {symbol_price: open_price 或 None} 的字典；若未找到对应日期或标的，则值为 None。
    """
    wanted = set(symbols)
    results: Dict[str, Optional[float]] = {}

    if merged_path is None:
        merged_file = get_merged_file_path(market)
    else:
        merged_file = Path(merged_path)

    if ' ' in today_date:
        merged_file = _to_hourly_merged_path(merged_file)

    if not merged_file.exists():
        return results

    # print(f"get_open_prices:merged_file:{merged_file}")
    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except Exception:
                continue
            meta = doc.get("Meta Data", {}) if isinstance(doc, dict) else {}
            sym = meta.get("2. Symbol")
            if sym not in wanted:
                continue
            # 查找所有以 "Time Series" 开头的键
            series = None
            for key, value in doc.items():
                if key.startswith("Time Series"):
                    series = value
                    break
            if not isinstance(series, dict):
                continue
            bar = series.get(today_date)
            if isinstance(bar, dict):
                open_val = bar.get("1. buy price")
                
                try:
                    results[f"{sym}_price"] = float(open_val) if open_val is not None else None
                except Exception:
                    results[f"{sym}_price"] = None

    return results


def get_yesterday_open_and_close_price(
    today_date: str, symbols: List[str], merged_path: Optional[str] = None, market: str = "us"
) -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """从 data/merged.jsonl 中读取指定日期与股票的昨日买入价和卖出价。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        symbols: 需要查询的股票代码列表。
        merged_path: 可选，自定义 merged.jsonl 路径；默认读取项目根目录下 data/merged.jsonl。
        market: 市场类型，"us" 为美股，"cn" 为A股

    Returns:
        (买入价字典, 卖出价字典) 的元组；若未找到对应日期或标的，则值为 None。
    """
    wanted = set(symbols)
    buy_results: Dict[str, Optional[float]] = {}
    sell_results: Dict[str, Optional[float]] = {}

    if merged_path is None:
        merged_file = get_merged_file_path(market)
    else:
        merged_file = Path(merged_path)
    
    if ' ' in today_date:
        merged_file = _to_hourly_merged_path(merged_file)

    if not merged_file.exists():
        return buy_results, sell_results

    yesterday_date = get_yesterday_date(today_date, market=market)
    # print(f"get_yesterday_open_and_close_price:yesterday_date:{yesterday_date}")

    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except Exception:
                continue
            meta = doc.get("Meta Data", {}) if isinstance(doc, dict) else {}
            sym = meta.get("2. Symbol")
            if sym not in wanted:
                continue
            # 查找所有以 "Time Series" 开头的键
            series = None
            for key, value in doc.items():
                if key.startswith("Time Series"):
                    series = value
                    break
            if not isinstance(series, dict):
                continue

            # 尝试获取昨日买入价和卖出价
            bar = series.get(yesterday_date)
            if isinstance(bar, dict):
                buy_val = bar.get("1. buy price")  # 买入价字段
                sell_val = bar.get("4. sell price")  # 卖出价字段

                try:
                    buy_price = float(buy_val) if buy_val is not None else None
                    sell_price = float(sell_val) if sell_val is not None else None
                    buy_results[f"{sym}_price"] = buy_price
                    sell_results[f"{sym}_price"] = sell_price
                except Exception:
                    buy_results[f"{sym}_price"] = None
                    sell_results[f"{sym}_price"] = None
            else:
                # 如果昨日没有数据，尝试向前查找最近的交易日
                # raise ValueError(f"No data found for {sym} on {yesterday_date}")
                # print(f"No data found for {sym} on {yesterday_date}")
                buy_results[f'{sym}_price'] = None
                sell_results[f'{sym}_price'] = None
                # today_dt = datetime.strptime(today_date, "%Y-%m-%d")
                # yesterday_dt = today_dt - timedelta(days=1)
                # current_date = yesterday_dt
                # found_data = False
                
                # # 最多向前查找5个交易日
                # for _ in range(5):
                #     current_date -= timedelta(days=1)
                #     # 跳过周末
                #     while current_date.weekday() >= 5:
                #         current_date -= timedelta(days=1)
                    
                #     check_date = current_date.strftime("%Y-%m-%d")
                #     bar = series.get(check_date)
                #     if isinstance(bar, dict):
                #         buy_val = bar.get("1. buy price")
                #         sell_val = bar.get("4. sell price")
                        
                #         try:
                #             buy_price = float(buy_val) if buy_val is not None else None
                #             sell_price = float(sell_val) if sell_val is not None else None
                #             buy_results[f'{sym}_price'] = buy_price
                #             sell_results[f'{sym}_price'] = sell_price
                #             found_data = True
                #             break
                #         except Exception:
                #             continue
                
                # if not found_data:
                #     buy_results[f'{sym}_price'] = None
                #     sell_results[f'{sym}_price'] = None

    return buy_results, sell_results

def get_yesterday_diff(
    today_date: str, symbols: List[str], merged_path: Optional[str] = None, market: str = "us"
) -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """从 data/merged.jsonl 中读取指定日期与股票的昨日买入价和卖出价。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        symbols: 需要查询的股票代码列表。
        merged_path: 可选，自定义 merged.jsonl 路径；默认读取项目根目录下 data/merged.jsonl。
        market: 市场类型，"us" 为美股，"cn" 为A股

    Returns:
        (买入价字典, 卖出价字典) 的元组；若未找到对应日期或标的，则值为 None。
    """
    wanted = set(symbols)
    diff_result: Dict[str, Optional[float]] = {}
    #diff_5d_result: Dict[str, Optional[float]] = {}
    #diff_20d_result: Dict[str, Optional[float]] = {}

    if merged_path is None:
        merged_file = get_merged_file_path(market)
    else:
        merged_file = Path(merged_path)
    
    if ' ' in today_date:
        merged_file = _to_hourly_merged_path(merged_file)

    input_dt = get_yesterday_date(today_date, merged_path=merged_path, market=market)
    #print(f"today:{today_date} yes:{yesterday_date}")

    # 解析输入日期/时间
    # if ' ' in yesterday_date:
    #     input_date_yes = datetime.strptime(yesterday_date, "%Y-%m-%d %H:%M:%S")
    #     input_date_to = datetime.strptime(today_date, "%Y-%m-%d %H:%M:%S")
    #     if input_date_yes.strftime("%Y-%m-%d") == input_date_to.strftime("%Y-%m-%d"): 
    #         input_dt = (input_date_yes - timedelta(days=1)).strftime("%Y-%m-%d") 
    # else:
    #     input_dt = yesterday_date

    # print(f"input_dt : {input_dt}")
    if not merged_file.exists():
        return diff_result 

    with merged_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
            except Exception:
                continue
            meta = doc.get("Meta Data", {}) if isinstance(doc, dict) else {}
            sym = meta.get("2. Symbol")
            if sym not in wanted:
                continue
            # 查找所有以 "Time Series" 开头的键
            series = None
            for key, value in doc.items():
                if key.startswith("Time Series"):
                    series = value
                    break
            if not isinstance(series, dict):
                continue

            # 尝试获取昨日买入价和卖出价
            bar = series.get(input_dt)
            if isinstance(bar, dict):
                diff_val = bar.get("6. pct_chg")
                #diff_5d_val = bar.get("10. diff_5d") 
                #diff_20d_val = bar.get("11. diff_20d") 

                try:
                    diff_p = float(diff_val) if diff_val is not None else None
                    #diff_5d_p = float(diff_5d_val) if diff_5d_val is not None else None
                    #diff_20d_p = float(diff_20d_val) if diff_20d_val is not None else None
                    diff_result[f"{sym}_p"] = diff_p
                    #diff_5d_result[f"{sym}_p"] = diff_5d_p
                    #diff_20d_result[f"{sym}_p"] = diff_20d_p
                except Exception:
                    diff_result[f"{sym}_p"] = None
                    #diff_5d_result[f"{sym}_p"] = None
                    #diff_20d_result[f"{sym}_p"] = None
            else:
                diff_result[f"{sym}_p"] = None
                #diff_5d_result[f"{sym}_p"] = None
                #diff_20d_result[f"{sym}_p"] = None

    return diff_result


def get_yesterday_profit(
    today_date: str,
    yesterday_buy_prices: Dict[str, Optional[float]],
    yesterday_sell_prices: Dict[str, Optional[float]],
    yesterday_init_position: Dict[str, float],
    stock_symbols: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    获取今日开盘时持仓的收益，收益计算方式为：(昨日收盘价格 - 昨日开盘价格)*当前持仓。
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        yesterday_buy_prices: 昨日开盘价格字典，格式为 {symbol_price: price}
        yesterday_sell_prices: 昨日收盘价格字典，格式为 {symbol_price: price}
        yesterday_init_position: 昨日初始持仓字典，格式为 {symbol: weight}
        stock_symbols: 股票代码列表，默认为 all_nasdaq_100_symbols

    Returns:
        {symbol: profit} 的字典；若未找到对应日期或标的，则值为 0.0。
    """
    profit_dict = {}

    # 使用传入的股票列表或默认的纳斯达克100列表
    if stock_symbols is None:
        stock_symbols = all_nasdaq_100_symbols

    # 遍历所有股票代码
    for symbol in stock_symbols:
        symbol_price_key = f"{symbol}_price"

        # 获取昨日开盘价和收盘价
        buy_price = yesterday_buy_prices.get(symbol_price_key)
        sell_price = yesterday_sell_prices.get(symbol_price_key)

        # 获取昨日持仓权重
        position_weight = yesterday_init_position.get(symbol, 0.0)

        # 计算收益：(收盘价 - 开盘价) * 持仓权重
        if buy_price is not None and sell_price is not None and position_weight > 0:
            profit = (sell_price - buy_price) * position_weight
            profit_dict[symbol] = round(profit, 4)  # 保留4位小数
        else:
            profit_dict[symbol] = 0.0

    return profit_dict

def get_today_init_position(today_date: str, signature: str) -> Dict[str, float]:
    """
    获取今日开盘时的初始持仓（即文件中上一个交易日代表的持仓）。从../data/agent_data/{signature}/position/position.jsonl中读取。
    如果同一日期有多条记录，选择id最大的记录作为初始持仓。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        signature: 模型名称，用于构建文件路径。

    Returns:
        {symbol: weight} 的字典；若未找到对应日期，则返回空字典。
    """
    from tools.general_tools import get_config_value
    import os

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, must be explicitly set
    log_path = get_config_value("LOG_PATH")
    if not log_path:
        # LOG_PATH未设置,无法确定position文件路径,返回空字典
        print(f"⚠️  LOG_PATH not set, cannot load initial position for {signature}")
        return {}

    # Handle different path formats:
    # - If it's an absolute path (like temp directory), use it directly
    # - If it's a relative path starting with "./data/", remove the prefix and prepend base_dir/data
    # - Otherwise, treat as relative to base_dir/data
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        position_file = Path(log_path) / signature / "position" / "position.jsonl"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"
#     position_file = base_dir / "data" / "agent_data" / signature / "position" / "position.jsonl"

    if not position_file.exists():
        print(f"Position file {position_file} does not exist")
        return {}
    
    # 获取市场类型，智能判断
    market = get_market_type()
    yesterday_date = get_yesterday_date(today_date, market=market)
    
    max_id = -1
    latest_positions = {}
    all_records = []
  
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                record_date = doc.get("date")
                if record_date and record_date < today_date:
                    all_records.append(doc)
            except Exception:
                continue

    if not all_records:
        return {}

    # Sort by date (descending) then by id (descending) to get the most recent record
    all_records.sort(key=lambda x: (x.get("date", ""), x.get("id", 0)), reverse=True)

    return all_records[0].get("positions", {})


def get_latest_position(today_date: str, signature: str) -> Tuple[Dict[str, float], int]:
    """
    获取最新持仓。从 ../data/agent_data/{signature}/position/position.jsonl 中读取。
    优先选择当天 (today_date) 中 id 最大的记录；
    若当天无记录，则回退到上一个交易日，选择该日中 id 最大的记录。

    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        signature: 模型名称，用于构建文件路径。

    Returns:
        (positions, max_id):
          - positions: {symbol: weight} 的字典；若未找到任何记录，则为空字典。
          - max_id: 选中记录的最大 id；若未找到任何记录，则为 -1.
    """
    from tools.general_tools import get_config_value
    import os

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, must be explicitly set
    log_path = get_config_value("LOG_PATH")
    if not log_path:
        # LOG_PATH未设置,无法确定position文件路径,返回空字典和-1
        print(f"⚠️  LOG_PATH not set, cannot load latest position for {signature}")
        return {}, -1

    # Handle different path formats:
    # - If it's an absolute path (like temp directory), use it directly
    # - If it's a relative path starting with "./data/", remove the prefix and prepend base_dir/data
    # - Otherwise, treat as relative to base_dir/data
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        position_file = Path(log_path) / signature / "position" / "position.jsonl"
    else:
        if log_path.startswith("./data/"):
            log_path = str(log_path)[7:]  # Remove "./data/" prefix
        position_file = base_dir / "data" / Path(log_path) / signature / "position" / "position.jsonl"
    print(f"position_file : {position_file}")
    if not position_file.exists():
        return {}, -1

    # 获取市场类型，智能判断
    market = get_market_type()
    
    # Step 1: 先查找当天的记录
    max_id_today = -1
    latest_positions_today: Dict[str, float] = {}
    
    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == today_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_today:
                        max_id_today = current_id
                        latest_positions_today = doc.get("positions", {})
            except Exception:
                continue
    
    # 如果当天有记录，直接返回
    if max_id_today >= 0 and latest_positions_today:
        return latest_positions_today, max_id_today
    
    # Step 2: 当天没有记录，则回退到上一个交易日
    prev_date = get_yesterday_date(today_date, market=market)
    
    max_id_prev = -1
    latest_positions_prev: Dict[str, float] = {}

    with position_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                doc = json.loads(line)
                if doc.get("date") == prev_date:
                    current_id = doc.get("id", -1)
                    if current_id > max_id_prev:
                        max_id_prev = current_id
                        latest_positions_prev = doc.get("positions", {})
            except Exception:
                continue
    
    # 如果前一天也没有记录，尝试找文件中最新的记录（按日期和id排序）
    if max_id_prev < 0 or not latest_positions_prev:
        all_records = []
        with position_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    if doc.get("date") and doc.get("date") < today_date:
                        all_records.append(doc)
                except Exception:
                    continue
        
        if all_records:
            # 按日期和id排序，取最新的一条
            all_records.sort(key=lambda x: (x.get("date", ""), x.get("id", 0)), reverse=True)
            latest_positions_prev = all_records[0].get("positions", {})
            max_id_prev = all_records[0].get("id", -1)
    
    return latest_positions_prev, max_id_prev

def add_no_trade_record(today_date: str, signature: str):
    """
    添加不交易记录。从 ../data/agent_data/{signature}/position/position.jsonl 中前一日最后一条持仓，并更新在今日的position.jsonl文件中。
    Args:
        today_date: 日期字符串，格式 YYYY-MM-DD，代表今天日期。
        signature: 模型名称，用于构建文件路径。

    Returns:
        None
    """
    save_item = {}
    current_position, current_action_id = get_latest_position(today_date, signature)
    
    save_item["date"] = today_date
    save_item["id"] = current_action_id + 1
    save_item["this_action"] = {"action": "no_trade", "symbol": "", "amount": 0}

    save_item["positions"] = current_position

    from tools.general_tools import get_config_value
    import os

    base_dir = Path(__file__).resolve().parents[1]

    # Get log_path from config, must be explicitly set
    log_path = get_config_value("LOG_PATH")
    if not log_path:
        raise ValueError(
            f"❌ LOG_PATH not set in runtime environment. "
            f"Cannot save no_trade record for signature={signature}"
        )

    # Handle different path formats:
    # - If it's an absolute path (like temp directory), use it directly
    # - If it's a relative path starting with "./data/", remove the prefix and prepend base_dir/data
    # - Otherwise, treat as relative to base_dir/data
    if os.path.isabs(log_path):
        # Absolute path (like temp directory) - use directly
        position_file = Path(log_path) / signature / "position" / "position.jsonl"
    else:
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file = base_dir / "data" / log_path / signature / "position" / "position.jsonl"

    with position_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(save_item) + "\n")
    
    # 发送无交易推送
    try:
        # 避免循环引用，在函数内部导入
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        webhook_path = os.path.join(project_root, "webhook")
        if webhook_path not in sys.path:
            sys.path.append(webhook_path)
            
        # from dingtalk_webhook import send_no_trade_notification  # 已禁用：降低钉钉推送打扰
        # send_no_trade_notification(signature, today_date, current_position)  # 已禁用：降低钉钉推送打扰
    except Exception as e:
        print(f"⚠️ 发送无交易自动推送失败: {e}")
        
    return


if __name__ == "__main__":
    # today_date = get_config_value("TODAY_DATE")
    # signature = get_config_value("SIGNATURE")
    # if signature is None:
    #     raise ValueError("SIGNATURE environment variable is not set")
    # print(today_date, signature)

    # yesterday_date = get_yesterday_date("2025-12-22 10:30:00", market="cn")
    # print(yesterday_date)
    # yesterday_date = get_yesterday_date("2025-12-22 10:31:00", market="cn")
    # print(yesterday_date)

    # yesterday_date = get_yesterday_date("2025-12-19", market="cn")
    # print(yesterday_date)
    # yesterday_date = get_yesterday_date("2025-12-22", market="cn")
    # print(yesterday_date)
    # yesterday_date = get_yesterday_date("2025-12-23", market="cn")
    # print(yesterday_date)

    buy_results, sell_results = get_yesterday_open_and_close_price("2025-12-22 10:31:00", ['601677.SH'], market="cn")
    print(buy_results, sell_results)

    buy_results, sell_results = get_yesterday_open_and_close_price("2025-12-22", ['601677.SH'], market="cn")
    print(buy_results, sell_results)
    # today_buy_price = get_open_prices(today_date, all_nasdaq_100_symbols)
    # print(today_buy_price)
    # yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(today_date, all_nasdaq_100_symbols)
    # print(yesterday_sell_prices)
    # today_init_position = get_today_init_position(today_date, signature='qwen3-max')
    # print(today_init_position)
    # latest_position, latest_action_id = get_latest_position('2025-10-24', 'qwen3-max')
    # print(latest_position, latest_action_id)
    # latest_position, latest_action_id = get_latest_position('2025-10-16 16:00:00', 'test')
    # print(latest_position, latest_action_id)
    
    # yesterday_profit = get_yesterday_profit(today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position)
    # # print(yesterday_profit)
    # add_no_trade_record(today_date, signature)
