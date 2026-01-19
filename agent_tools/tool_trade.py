import os
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from fastmcp import FastMCP

from typing import Dict, List, Optional, Any
import fcntl
from pathlib import Path
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import json

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import (get_latest_position, get_open_prices,
                               get_yesterday_date,get_yesterday_diff,
                               get_yesterday_open_and_close_price,
                               get_yesterday_profit)

# 导入推送功能
try:
    import sys
    sys.path.append(os.path.join(project_root, "webhook"))
    from dingtalk_webhook import DingTalkWebhook, PositionReporter
    PUSH_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    PUSH_NOTIFICATIONS_AVAILABLE = False
    print("⚠️ 推送通知模块不可用，将跳过交易推送功能")

mcp = FastMCP("TradeTools")

def _position_lock(signature: str):
    """Context manager for file-based lock to serialize position updates per signature."""
    class _Lock:
        def __init__(self, name: str):
            base_dir = Path(project_root) / "data" / "agent_data" / name
            base_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = base_dir / ".position.lock"
            # Ensure lock file exists
            self._fh = open(self.lock_path, "a+")
        def __enter__(self):
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            return self
        def __exit__(self, exc_type, exc, tb):
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
    return _Lock(signature)



@mcp.tool()
def buy(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Buy stock function

    This function simulates stock buying operations, including the following steps:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate buy conditions (sufficient cash, lot size for CN market)
    4. Update position (increase stock quantity, decrease cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Buy quantity, must be a positive integer, indicating how many shares to buy
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing stock quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = buy("AAPL", 10)
        >>> print(result)  # {"AAPL": 110, "MSFT": 5, "CASH": 5000.0, ...}
        >>> result = buy("600519.SH", 100)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"600519.SH": 100, "CASH": 85000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    print(datetime.now())
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Auto-detect market type based on symbol format
    if symbol.endswith((".SH", ".SZ")):
        market = "cn"
    else:
        market = "us"

    # Amount validation for stocks
    try:
        amount = int(amount)  # Convert to int for stocks
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be an integer for stock trading. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    # Acquire lock for atomic read-modify-write on positions
    with _position_lock(signature):
        try:
            current_position, current_action_id = get_latest_position(today_date, signature)
        except Exception as e:
            print(e)
            print(today_date, signature)
            return {"error": f"Failed to load latest position: {e}", "symbol": symbol, "date": today_date}
    # Step 3: Get stock opening price for the day
    # Use get_open_prices function to get the opening price of specified stock for the day
    # If stock symbol does not exist or price data is missing, KeyError exception will be raised
    try:
        this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
    except KeyError:
        # Stock symbol does not exist or price data is missing, return error message
        return {
            "error": f"Symbol {symbol} not found! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date,
        }
    
    this_symbol_diff = get_yesterday_diff(today_date, [symbol], market=market)
    if market == 'cn' and this_symbol_diff[f"{symbol}_p"]: 
        if (symbol.startswith("688") or symbol.startswith("300")) and (this_symbol_diff[f"{symbol}_p"] >= 20 or this_symbol_diff[f"{symbol}_p"] <= -20):
            return {
                "error": f"Symbol {symbol} yesterday diff > 20%. This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
                "diff": this_symbol_diff[f"{symbol}_p"],
            }
        elif (this_symbol_diff[f"{symbol}_p"] >= 10 or this_symbol_diff[f"{symbol}_p"] <= -10):
            return {
                "error": f"Symbol {symbol} yesterday diff > 10%. This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
                "diff": this_symbol_diff[f"{symbol}_p"],
            }

    # Step 4: Validate buy conditions
    # Calculate cash required for purchase: stock price × buy quantity
    try:
        cash_left = current_position["CASH"] - this_symbol_price * amount
    except Exception as e:
        print(current_position, "CASH", this_symbol_price, amount)

    # Check if cash balance is sufficient for purchase
    if cash_left < 0:
        # Insufficient cash, return error message
        return {
            "error": "Insufficient cash! This action will not be allowed.",
            "required_cash": this_symbol_price * amount,
            "cash_available": current_position.get("CASH", 0),
            "symbol": symbol,
            "date": today_date,
        }
    else:
        # Step 5: Execute buy operation, update position
        # Create a copy of current position to avoid directly modifying original data
        new_position = current_position.copy()

        # Decrease cash balance
        new_position["CASH"] = cash_left

        # Increase stock position quantity
        new_position[symbol] += amount

        # Step 6: Record transaction to position.jsonl file
        # Build file path: {project_root}/data/{log_path}/{signature}/position/position.jsonl
        # Use append mode ("a") to write new transaction record
        # Each operation ID increments by 1, ensuring uniqueness of operation sequence
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
        with open(position_file_path, "a") as f:
            # Write JSON format transaction record, containing date, operation ID, transaction details and updated position
            print(
                f"Writing to position.jsonl: {json.dumps({'date': today_date, 'id': current_action_id + 1, 'this_action':{'action':'buy','symbol':symbol,'amount':amount},'positions': new_position})}"
            )
            f.write(
                json.dumps(
                    {
                        "date": today_date,
                        "id": current_action_id + 1,
                        "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
                        "positions": new_position,
                    }
                )
                + "\n"
            )
        # Step 7: 发送交易推送通知
        position_record = {
            "date": today_date,
            "id": current_action_id + 1,
            "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
            "positions": new_position,
        }
        _send_trade_notification(signature, "buy", symbol, amount, position_record)
        
        # Step 8: Return updated position
        write_config_value("IF_TRADE", True)
        print("IF_TRADE", get_config_value("IF_TRADE"))
        return new_position


def _send_trade_notification(signature: str, action: str, symbol: str, amount: int, position_data: Dict[str, Any]):
    """
    发送交易操作推送通知
    
    Args:
        signature: 模型签名
        action: 操作类型 ("buy" 或 "sell")
        symbol: 股票代码
        amount: 数量
        position_data: 仓位数据
    """
    if not PUSH_NOTIFICATIONS_AVAILABLE:
        return
    
    try:
        # 从环境变量获取推送配置
        webhook_url = os.getenv("DINGTALK_WEBHOOK_URL") or os.getenv("WEBHOOK_URL")
        secret = os.getenv("DINGTALK_SECRET")
        
        if not webhook_url:
            print("⚠️ 未配置 Webhook URL，跳过推送")
            return
        
        # 创建推送器
        dingtalk = DingTalkWebhook(webhook_url, secret)
        reporter = PositionReporter()
        
        # 格式化交易操作消息
        action_text = "买入" if action == "buy" else "卖出" if action == "sell" else action
        display_name = reporter._get_stock_display_name(symbol)
        
        # 提取交易信息
        trade_id = position_data.get("id", "未知")
        trade_date = position_data.get("date", "未知时间")
        positions = position_data.get("positions", {})
        cash_balance = positions.get("CASH", 0)
        
        # 构建消息
        message_lines = [
            f"📈 **{signature} position 交易通知**  \n\n",
            f"📅 时间: {trade_date}  \n\n",
            f"🆔 交易ID: {trade_id}  \n\n",
            "  \n\n",
            f"📝 交易操作:  \n\n",
            f"  • {action_text} {display_name} {amount:,} 股  \n\n",
            "  \n\n",
            f"💰 剩余现金: ¥{cash_balance:,.2f}  \n\n"
        ]
        
        message_content = "".join(message_lines)
        
        # 发送推送
        success = dingtalk.send_message(message_content, msg_type="markdown")
        if success:
            print(f"✅ 交易推送成功: {action_text} {display_name} {amount}股")
        else:
            print(f"❌ 交易推送失败: {action_text} {display_name} {amount}股")
            
    except Exception as e:
        print(f"❌ 发送交易推送时出错: {e}")


def _get_today_buy_amount(symbol: str, today_date: str, signature: str) -> int:
    """
    Helper function to get the total amount bought today for T+1 restriction check

    Args:
        symbol: Stock symbol
        today_date: Trading date
        signature: Model signature

    Returns:
        Total shares bought today
    """
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix
    position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")

    if not os.path.exists(position_file_path):
        return 0

    total_bought_today = 0
    with open(position_file_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("date").split(' ')[0] == today_date.split(' ')[0]:
                    this_action = record.get("this_action", {})
                    if this_action.get("action") == "buy" and this_action.get("symbol") == symbol:
                        total_bought_today += this_action.get("amount", 0)
            except Exception:
                continue

    return total_bought_today


@mcp.tool()
def sell(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Sell stock function

    This function simulates stock selling operations, including the following steps:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate sell conditions (position exists, sufficient quantity, lot size, T+1 for CN market)
    4. Update position (decrease stock quantity, increase cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Sell quantity, must be a positive integer, indicating how many shares to sell
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100
                and cannot sell shares bought on the same day (T+1 rule)

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing stock quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = sell("AAPL", 10)
        >>> print(result)  # {"AAPL": 90, "MSFT": 5, "CASH": 15000.0, ...}
        >>> result = sell("600519.SH", 100)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"600519.SH": 0, "CASH": 115000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    print(datetime.now())
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    # Auto-detect market type based on symbol format
    if symbol.endswith((".SH", ".SZ")):
        market = "cn"
    else:
        market = "us"

    # Amount validation for stocks
    try:
        amount = int(amount)  # Convert to int for stocks
    except ValueError:
        return {
            "error": f"Invalid amount format. Amount must be an integer for stock trading. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    current_position, current_action_id = get_latest_position(today_date, signature)

    # Step 3: Get stock opening price for the day
    # Use get_open_prices function to get the opening price of specified stock for the day
    # If stock symbol does not exist or price data is missing, KeyError exception will be raised
    try:
        this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
    except KeyError:
        # Stock symbol does not exist or price data is missing, return error message
        return {
            "error": f"Symbol {symbol} not found! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date,
        }

    # Step 4: Validate sell conditions
    # Check if holding this stock
    if symbol not in current_position:
        return {
            "error": f"No position for {symbol}! This action will not be allowed.",
            "symbol": symbol,
            "date": today_date,
        }

    # Check if position quantity is sufficient for selling
    if current_position[symbol] < amount:
        return {
            "error": "Insufficient shares! This action will not be allowed.",
            "have": current_position.get(symbol, 0),
            "want_to_sell": amount,
            "symbol": symbol,
            "date": today_date,
        }

    # 🇨🇳 Chinese A-shares T+1 trading rule: Cannot sell shares bought on the same day
    if market == "cn":
        bought_today = _get_today_buy_amount(symbol, today_date, signature)
        if bought_today > 0:
            # Calculate sellable quantity (total position - bought today)
            sellable_amount = current_position[symbol] - bought_today
            if amount > sellable_amount:
                return {
                    "error": f"T+1 restriction violated! You bought {bought_today} shares of {symbol} today and cannot sell them until tomorrow.",
                    "symbol": symbol,
                    "total_position": current_position[symbol],
                    "bought_today": bought_today,
                    "sellable_today": max(0, sellable_amount),
                    "want_to_sell": amount,
                    "date": today_date,
                }

    # Step 5: Execute sell operation, update position
    # Create a copy of current position to avoid directly modifying original data
    new_position = current_position.copy()

    # Decrease stock position quantity
    new_position[symbol] -= amount

    # Increase cash balance: sell price × sell quantity
    # Use get method to ensure CASH field exists, default to 0 if not present
    new_position["CASH"] = new_position.get("CASH", 0) + this_symbol_price * amount

    # Step 6: Record transaction to position.jsonl file
    # Build file path: {project_root}/data/{log_path}/{signature}/position/position.jsonl
    # Use append mode ("a") to write new transaction record
    # Each operation ID increments by 1, ensuring uniqueness of operation sequence
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix
    position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
    with open(position_file_path, "a") as f:
        # Write JSON format transaction record, containing date, operation ID and updated position
        print(
            f"Writing to position.jsonl: {json.dumps({'date': today_date, 'id': current_action_id + 1, 'this_action':{'action':'sell','symbol':symbol,'amount':amount},'positions': new_position})}"
        )
        f.write(
            json.dumps(
                {
                    "date": today_date,
                    "id": current_action_id + 1,
                    "this_action": {"action": "sell", "symbol": symbol, "amount": amount},
                    "positions": new_position,
                }
            )
            + "\n"
        )

    # Step 7: 发送交易推送通知
    position_record = {
        "date": today_date,
        "id": current_action_id + 1,
        "this_action": {"action": "sell", "symbol": symbol, "amount": amount},
        "positions": new_position,
    }
    _send_trade_notification(signature, "sell", symbol, amount, position_record)
    
    # Step 8: Return updated position
    write_config_value("IF_TRADE", True)
    return new_position


if __name__ == "__main__":
    # new_result = buy("AAPL", 1)
    # print(new_result)
    # new_result = sell("AAPL", 1)
    # print(new_result)
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
