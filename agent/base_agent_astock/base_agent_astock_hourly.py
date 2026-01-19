"""
BaseAgentAStockHourly class - A股专用交易Agent基类
Chinese A-shares specific trading agent base class
Encapsulates core functionality for A-shares trading including MCP tool management, AI agent creation, and trading execution
"""

import asyncio
import json
import os
# Import project tools
import sys
import pandas as pd
import tiktoken
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


class DeepSeekChatOpenAI(ChatOpenAI):
    """
    Custom ChatOpenAI wrapper for DeepSeek API compatibility.
    Handles the case where DeepSeek returns tool_calls.args as JSON strings instead of dicts,
    and ensures message content is always a string.
    """

    def _convert_list_content_to_string(self, content: list) -> str:
        text_content = ""
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_content += part.get("text", "")
            elif isinstance(part, str):
                text_content += part
        return text_content

    def _generate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override generation to sanitize messages and fix tool_calls format in responses"""
        # Sanitize messages content
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, list):
                msg.content = self._convert_list_content_to_string(msg.content)
            elif hasattr(msg, "content") and msg.content is None:
                msg.content = ""

        # Call parent's generate method
        result = super()._generate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        self._fix_tool_calls(result)
        return result

    async def _agenerate(self, messages: list, stop: Optional[list] = None, **kwargs):
        """Override async generation to sanitize messages and fix tool_calls format in responses"""
        # Sanitize messages content
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, list):
                msg.content = self._convert_list_content_to_string(msg.content)
            elif hasattr(msg, "content") and msg.content is None:
                msg.content = ""

        # Call parent's async generate method
        result = await super()._agenerate(messages, stop, **kwargs)

        # Fix tool_calls format in the generated messages
        self._fix_tool_calls(result)
        return result

    def _fix_tool_calls(self, result):
        """Fix tool_calls format in the generated messages"""
        for generation in result.generations:
            for gen in generation:
                if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                    tool_calls = gen.message.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        for tool_call in tool_calls:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                args = tool_call["function"]["arguments"]
                                # If arguments is a string, parse it
                                if isinstance(args, str):
                                    try:
                                        tool_call["function"]["arguments"] = json.loads(args)
                                    except json.JSONDecodeError:
                                        pass  # Keep as string if parsing fails
        return result


from prompts.agent_prompt_astock import (STOP_SIGNAL,get_agent_system_prompt_astock)
from tools.general_tools import (extract_conversation, extract_tool_messages,get_config_value, write_config_value)
from tools.price_tools import (add_no_trade_record,load_stock_list)

# Load environment variables
load_dotenv()


class BaseAgentAStockHourly:
    """
    A股专用交易Agent基类
    Chinese A-shares specific trading agent base class

    Main functionalities:
    1. MCP tool management and connection
    2. AI agent creation and configuration
    3. Trading execution and decision loops (with A-shares specific rules)
    4. Logging and management
    5. Position and configuration management
    """

    # Default SSE 50 stock symbols (A-shares only)
    DEFAULT_SSE50_SYMBOLS = [
        '000686.SZ',
        '002139.SZ',
        '002151.SZ',
        '002171.SZ',
        '002332.SZ',
        '002643.SZ',
        '300236.SZ',
        '600641.SH',
        '600850.SH',
        '600877.SH',
    ]

    def __init__(
        self,
        signature: str,
        basemodel: str,
        stock_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 10,
        max_retries: int = 3,
        base_delay: float = 0.5,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 100000.0,  # 默认10万人民币
        init_date: str = "2025-10-09 10:30:00",  # Hourly timestamp format 
        market: str = "cn",  # 接受但忽略此参数，始终使用"cn"
    ):
        """
        Initialize BaseAgentAStock

        Args:
            signature: Agent signature/name
            basemodel: Base model name
            stock_symbols: List of stock symbols, defaults to SSE 50
            mcp_config: MCP tool configuration, including port and URL information
            log_path: Log path, defaults to ./data/agent_data_astock
            max_steps: Maximum reasoning steps
            max_retries: Maximum retry attempts
            base_delay: Base delay time for retries
            openai_base_url: OpenAI API base URL
            openai_api_key: OpenAI API key
            initial_cash: Initial cash amount (default: 100000.0 RMB)
            init_date: Initialization date
            market: Market type (accepted for compatibility, but always uses "cn")
        """
        self.signature = signature
        self.basemodel = basemodel
        self.market = "cn"  # 硬编码为A股市场
        self.encoding = None

        # 默认使用上证50成分股
        if stock_symbols is None:
            self.stock_symbols = load_stock_list()
        else:
            self.stock_symbols = stock_symbols

        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

        # Set MCP configuration
        self.mcp_config = mcp_config or self._get_default_mcp_config()

        # Set log path - A股专用路径
        self.base_log_path = log_path or "./data/agent_data_astock"

        # Set OpenAI configuration
        if openai_base_url == None:
            self.openai_base_url = os.getenv("OPENAI_API_BASE")
        else:
            self.openai_base_url = openai_base_url
        if openai_api_key == None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        else:
            self.openai_api_key = openai_api_key

        # Initialize components
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: Optional[List] = None
        self.model: Optional[ChatOpenAI] = None
        self.agent: Optional[Any] = None

        # Data paths
        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")
    


    def _get_default_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        """Get default MCP configuration"""
        return {
            "math": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', '8000')}/mcp",
            },
            "stock_local": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('GETPRICE_HTTP_PORT', '8003')}/mcp",
            },
            "search": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', '8001')}/mcp",
            },
            "trade": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('TRADE_HTTP_PORT', '8002')}/mcp",
            },
        }

    async def initialize(self) -> None:
        """Initialize MCP client and AI model"""
        print(f"🚀 Initializing A-shares agent: {self.signature}")

        # Validate OpenAI configuration
        if not self.openai_api_key:
            raise ValueError(
                "❌ OpenAI API key not set. Please configure OPENAI_API_KEY in environment or config file."
            )
        if not self.openai_base_url:
            print("⚠️  OpenAI base URL not set, using default")

        try:
            # Create MCP client
            self.client = MultiServerMCPClient(self.mcp_config)

            # Get tools
            self.tools = await self.client.get_tools()
            if not self.tools:
                print("⚠️  Warning: No MCP tools loaded. MCP services may not be running.")
                print(f"   MCP configuration: {self.mcp_config}")
            else:
                print(f"✅ Loaded {len(self.tools)} MCP tools")
        except Exception as e:
            raise RuntimeError(
                f"❌ Failed to initialize MCP client: {e}\n"
                f"   Please ensure MCP services are running at the configured ports.\n"
                f"   Run: python agent_tools/start_mcp_services.py"
            )

        try:
            # Create AI model - use custom DeepSeekChatOpenAI for DeepSeek models
            # to handle tool_calls.args format differences (JSON string vs dict)
            if "deepseek" in self.basemodel.lower():
                self.model = DeepSeekChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
            else:
                self.model = ChatOpenAI(
                    model=self.basemodel,
                    base_url=self.openai_base_url,
                    api_key=self.openai_api_key,
                    max_retries=3,
                    timeout=30,
                )
        except Exception as e:
            raise RuntimeError(f"❌ Failed to initialize AI model: {e}")

        # Note: agent will be created in run_trading_session() based on specific date
        # because system_prompt needs the current date and price information

        print(f"✅ A-shares agent {self.signature} initialization completed")

    def _setup_logging(self, today_date: str) -> str:
        """Set up log file path"""
        log_path = os.path.join(self.base_log_path, self.signature, "log", today_date)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, new_messages: List[Dict[str, str]]) -> None:
        """Log messages to log file"""
        log_entry = {"timestamp": datetime.now().isoformat(), "signature": self.signature, "new_messages": new_messages}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    def count_tokens(self):
        """计算消息的token数量"""
        self.encoding = tiktoken.get_encoding("cl100k_base")  # DeepSeek使用的编码

    async def _ainvoke_with_retry(self, message: List[Dict[str, str]]) -> Any:
        """Agent invocation with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.agent.ainvoke({"messages": message}, {"recursion_limit": 100})
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                print(f"⚠️ Attempt {attempt} ainvoke failed, retrying after {self.base_delay * attempt} seconds...")
                print(f"Error details: {e}")
                await asyncio.sleep(self.base_delay * attempt)

    async def run_trading_session(self, today_date: str) -> None:
        """
        Run single day trading session (A-shares specific)

        Args:
            today_date: Trading date
        """
        print(f"📈 Starting A-shares hourly trading session: {today_date}")

        log_date = ''
        # Set up logging
        if ' ' in today_date or 'T' in today_date:
            log_date = datetime.strptime(today_date, "%Y-%m-%d %H:%M:%S")
            log_date = log_date.strftime("%Y-%m-%d")

        log_file = self._setup_logging(log_date)
        prompt=get_agent_system_prompt_astock(today_date, self.signature, self.stock_symbols)

        # Update system prompt - 使用A股专用提示词
        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=prompt,
        )

        # Initial user query
        init_prompt = [{"role": "assistant", "content": f"[AI: deepseek-chat]\n初始提示词:{prompt}"}]
        user_query = [{"role": "user", "content": f"请分析并更新今日（{today_date}）的持仓。"}]
        message = user_query.copy()
        self.count_tokens()

        # Log initial message
        self._log_message(log_file, init_prompt)
        self._log_message(log_file, user_query)

        # Trading loop
        current_step = 0
        total_tokens = 0
        trading_done = False
        while current_step < self.max_steps:
            current_step += 1
            print(f"🔄 Step {current_step}/{self.max_steps}")
            total_tokens = sum(len(self.encoding.encode(msg["content"])) for msg in message)
            # print(f"total tokens is {total_tokens}")

            if total_tokens > 131072:
                message = message[-5:]  # 保留最后5条消息

            try:
                # Call agent
                response = await self._ainvoke_with_retry(message)

                # Extract agent response
                agent_response = extract_conversation(response, "all")
                for resp in agent_response:
                    self._log_message(log_file, [{"role": "assistant", "content": resp}])
                    message.extend([{"role": "assistant", "content": resp}])
                    # Check stop signal
                    if STOP_SIGNAL in resp:
                        print("✅ Received stop signal, trading session ended")
                        trading_done = True        

                if trading_done:
                    break

                # # Extract tool messages
                # tool_msgs = extract_tool_messages(response)
                # tool_response = "\n".join([msg.content for msg in tool_msgs])

                # # Prepare new messages
                # new_messages = [
                #     {"role": "assistant", "content": agent_response},
                #     {"role": "user", "content": f"Tool results: {tool_response}"},
                # ]

                # # Add new messages
                # message.extend(agent_response)

                # # Log messages
                # self._log_message(log_file, new_messages[0])
                # self._log_message(log_file, new_messages[1])

            except Exception as e:
                print(f"❌ Trading session error: {datetime.now().isoformat()} {str(e)}")
                print(f"Error details: {e}")
                raise

        # Handle trading results
        await self._handle_trading_result(today_date)

    async def _handle_trading_result(self, today_date: str) -> None:
        """Handle trading results"""
        if_trade = get_config_value("IF_TRADE")
        if if_trade:
            write_config_value("IF_TRADE", False)
            print("✅ Trading completed")
        else:
            print("📊 No trading, maintaining positions")
            try:
                add_no_trade_record(today_date, self.signature)
            except NameError as e:
                print(f"❌ NameError: {e}")
                raise
            write_config_value("IF_TRADE", False)

    def register_agent(self) -> None:
        """Register new agent, create initial positions"""
        # Check if position.jsonl file already exists
        if os.path.exists(self.position_file):
            print(f"⚠️ Position file {self.position_file} already exists, skipping registration")
            return

        # Ensure directory structure exists
        position_dir = os.path.join(self.data_path, "position")
        if not os.path.exists(position_dir):
            os.makedirs(position_dir)
            print(f"📁 Created position directory: {position_dir}")

        # Create initial positions
        init_position = {symbol: 0 for symbol in self.stock_symbols}
        init_position["CASH"] = self.initial_cash

        with open(self.position_file, "w") as f:  # Use "w" mode to ensure creating new file
            f.write(json.dumps({"date": self.init_date, "id": 0, "positions": init_position}) + "\n")

        print(f"✅ A-shares agent {self.signature} registration completed")
        print(f"📁 Position file: {self.position_file}")
        print(f"💰 Initial cash: ¥{self.initial_cash:,.2f}")
        print(f"📊 Number of stocks: {len(self.stock_symbols)}")


    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        """
        Get trading date list from merged_hourly.jsonl for hourly data

        Args:
            init_date: Start date (YYYY-MM-DD HH:MM:SS)
            end_date: End date (YYYY-MM-DD HH:MM:SS)

        Returns:
            List of trading dates/times within the range
        """
        print()
        # Determine output format based on input format
        has_time1 = ' ' in init_date
        has_time2 = ' ' in end_date
        assert has_time1 == has_time2, "init_date and end_date must have the same time format"
        has_time = has_time1
        if has_time:
            init_dt = datetime.strptime(init_date, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        else:
            raise ValueError("Only support hour-level trading. Please use YYYY-MM-DD HH:MM:SS format.")

        # Get merged_hourly.jsonl path (A-shares specific)
        base_dir = Path(__file__).resolve().parents[2]
        merged_file = base_dir / "data" / "A_stock" / "merged_hourly.jsonl"

        if not merged_file.exists():
            return []

        # Collect all timestamps from merged_hourly.jsonl
        all_timestamps = set()

        with merged_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    # Find all keys starting with "Time Series"
                    for key, value in doc.items():
                        if key.startswith("Time Series"):
                            if isinstance(value, dict):
                                all_timestamps.update(value.keys())
                            break
                except Exception:
                    continue

        if not all_timestamps:
            return []
        # Determine min_datetime based on init_date and last processed date in position file
        min_datetime = init_dt

        last_processed_dt = None
        if os.path.exists(self.position_file):
            max_date = None
            with open(self.position_file, "r") as f:
                for line in f:
                    doc = json.loads(line)
                    current_date = doc['date']
                    if max_date is None:
                        max_date = current_date
                    else:
                        if ' ' in current_date:
                            current_date_obj = datetime.strptime(current_date, "%Y-%m-%d %H:%M:%S")
                        else:
                            current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")

                        if ' ' in max_date:
                            max_date_obj = datetime.strptime(max_date, "%Y-%m-%d %H:%M:%S")
                        else:
                            max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")

                        if current_date_obj > max_date_obj:
                            max_date = current_date

            if max_date:
                if has_time:
                    last_processed_dt = datetime.strptime(max_date, "%Y-%m-%d %H:%M:%S")
                else:
                    last_processed_dt = datetime.strptime(max_date, "%Y-%m-%d")
            REGISTER = False
        else:
            # ensure agent registration if no position file yet
            self.register_agent()
            REGISTER = True
        # Take the larger lower bound between init_dt and last_processed_dt
        if last_processed_dt is not None:
            # If last processed has time, we will filter strictly greater than it;
            min_datetime = max(init_dt, last_processed_dt)
            if not has_time:
                last_processed_dt = last_processed_dt.date()

        # Filter timestamps within the range
        trading_times = []
        if not has_time:
            min_datetime = min_datetime.date()
            end_dt = end_dt.date()

        for ts_str in all_timestamps:
            try:
                if has_time:
                    ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                else:
                    ts_dt = datetime.strptime(ts_str, "%Y-%m-%d").date()
                # Check if timestamp is in range with boundary rules
                in_lower = False
                if last_processed_dt is None:
                    in_lower = ts_dt >= min_datetime
                else:
                    in_lower = ts_dt > min_datetime
                if in_lower and ts_dt <= end_dt:
                    trading_times.append(ts_str)

            except Exception as e:
                print(f"❌ Error processing timestamp: {ts_str}")
                print(e)
                continue

        # Sort and remove duplicates
        trading_times = sorted(list(set(trading_times)))
        if REGISTER:
            # Only skip the very first timestamp if it exactly equals init_date to avoid double-processing
            if trading_times and trading_times[0] == init_date:
                print("REGISTER: init_date equals first timestamp; skipping first to avoid duplication")
                trading_times = trading_times[1:]
        return trading_times

    async def run_with_retry(self, today_date: str) -> None:
        """Run method with retry"""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"🔄 Attempting to run {self.signature} - {today_date} (Attempt {attempt})")
                await self.run_trading_session(today_date)
                print(f"✅ {self.signature} - {today_date} run successful")
                return
            except Exception as e:
                print(f"❌ Attempt {attempt} failed: {datetime.now().isoformat()}{str(e)}")
                if attempt == self.max_retries:
                    print(f"💥 {self.signature} - {today_date} all retries failed")
                    raise
                else:
                    wait_time = self.base_delay * attempt
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        """
        Run all trading days in date range

        Args:
            init_date: Start date
            end_date: End date
        """
        print(f"📅 Running A-shares date range: {init_date} to {end_date}")

        # Get trading date list
        trading_dates = self.get_trading_dates(init_date, end_date)

        if not trading_dates:
            print(f"ℹ️ No trading days to process")
            return

        print(f"📊 Trading days to process: {trading_dates}")

        # Process each trading day
        for date in trading_dates:
            print(f"🔄 Processing {self.signature} - Date: {date}")

            # Set configuration
            write_config_value("TODAY_DATE", date)
            write_config_value("SIGNATURE", self.signature)

            try:
                await self.run_with_retry(date)
            except Exception as e:
                print(f"❌ Error processing {self.signature} - Date: {date}")
                print(e)
                raise

        print(f"✅ {self.signature} processing completed")

    def get_position_summary(self) -> Dict[str, Any]:
        """Get position summary"""
        if not os.path.exists(self.position_file):
            return {"error": "Position file does not exist"}

        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                positions.append(json.loads(line))

        if not positions:
            return {"error": "No position records"}

        latest_position = positions[-1]
        return {
            "signature": self.signature,
            "latest_date": latest_position.get("date"),
            "positions": latest_position.get("positions", {}),
            "total_records": len(positions),
        }

    def _is_valid_astock_trading_time(self, timestamp: str) -> bool:
        """
        Validate if timestamp is a valid A-shares trading time

        A-shares market trading hours (Beijing time):
        - Morning session: 09:30 - 11:30 (data points at 10:30, 11:30)
        - Afternoon session: 13:00 - 15:00 (data points at 14:00, 15:00)

        Args:
            timestamp: Timestamp string in format "YYYY-MM-DD HH:MM:SS"

        Returns:
            True if timestamp is within valid A-shares trading hours, False otherwise

        Example:
            >>> agent._is_valid_astock_trading_time("2025-10-09 10:30:00")
            True
            >>> agent._is_valid_astock_trading_time("2025-10-09 16:00:00")
            False
        """
        try:
            # Extract time component
            if " " not in timestamp:
                return False

            time_str = timestamp.split()[1]  # Get "HH:MM:SS"

            # Check if time is in the expected trading hour list
            if time_str in self.ASTOCK_TRADING_HOURS:
                return True

            # Alternative: Check time range (more flexible)
            hour, minute, second = map(int, time_str.split(":"))
            time_in_minutes = hour * 60 + minute

            # Morning session: 09:30 - 11:30 (570 - 690 minutes)
            morning_start = 9 * 60 + 30  # 570
            morning_end = 11 * 60 + 30  # 690

            # Afternoon session: 13:00 - 15:00 (780 - 900 minutes)
            afternoon_start = 13 * 60  # 780
            afternoon_end = 15 * 60  # 900

            return (morning_start <= time_in_minutes <= morning_end) or \
                   (afternoon_start <= time_in_minutes <= afternoon_end)

        except Exception as e:
            print(f"⚠️  Error validating trading time '{timestamp}': {e}")
            return False

    def _check_daily_completeness(self, trading_times: List[str], date: str) -> Dict[str, Any]:
        """
        Check if a trading day has all 4 expected time points

        A-shares hourly data should have exactly 4 time points per day:
        - 10:30:00 (morning mid-point)
        - 11:30:00 (morning close)
        - 14:00:00 (afternoon mid-point)
        - 15:00:00 (afternoon close)

        Args:
            trading_times: List of all trading timestamps
            date: Date to check (YYYY-MM-DD)

        Returns:
            Dictionary with completeness information:
            {
                "date": "2025-10-09",
                "expected": 4,
                "found": 3,
                "missing": ["14:00:00"],
                "is_complete": False
            }

        Example:
            >>> times = ["2025-10-09 10:30:00", "2025-10-09 11:30:00", "2025-10-09 15:00:00"]
            >>> agent._check_daily_completeness(times, "2025-10-09")
            {"date": "2025-10-09", "expected": 4, "found": 3, "missing": ["14:00:00"], "is_complete": False}
        """
        # Filter times for this specific date
        date_times = [t for t in trading_times if t.startswith(date)]

        # Extract hour:minute:second from timestamps
        found_times = set()
        for ts in date_times:
            if " " in ts:
                time_part = ts.split()[1]
                found_times.add(time_part)

        # Check against expected times
        expected_times = set(self.ASTOCK_TRADING_HOURS)
        missing_times = expected_times - found_times

        result = {
            "date": date,
            "expected": len(expected_times),
            "found": len(found_times),
            "found_times": sorted(list(found_times)),
            "missing": sorted(list(missing_times)),
            "is_complete": len(missing_times) == 0
        }

        # Print warning if incomplete
        if not result["is_complete"]:
            print(f"⚠️  警告: {date} 数据不完整")
            print(f"   预期时间点: {len(expected_times)} 个 {sorted(expected_times)}")
            print(f"   实际时间点: {len(found_times)} 个 {sorted(found_times)}")
            print(f"   缺失时间点: {sorted(missing_times)}")

        return result

    def validate_trading_times(self, trading_times: List[str], verbose: bool = True) -> Dict[str, Any]:
        """
        Validate and analyze a list of trading times

        This method performs comprehensive validation including:
        1. Checking if all timestamps are in valid A-shares trading hours
        2. Checking daily completeness (4 time points per day)
        3. Detecting duplicates
        4. Verifying timestamp format

        Args:
            trading_times: List of trading timestamps
            verbose: If True, print detailed validation results

        Returns:
            Dictionary with validation results:
            {
                "total_times": 8,
                "valid_times": 7,
                "invalid_times": 1,
                "invalid_list": ["2025-10-09 16:00:00"],
                "unique_dates": ["2025-10-09", "2025-10-10"],
                "daily_completeness": {...},
                "has_duplicates": False,
                "is_valid": True
            }

        Example:
            >>> times = ["2025-10-09 10:30:00", "2025-10-09 11:30:00", ...]
            >>> result = agent.validate_trading_times(times)
            >>> print(f"Valid: {result['is_valid']}")
        """
        # Count valid/invalid times
        valid_times = []
        invalid_times = []

        for ts in trading_times:
            if self._is_valid_astock_trading_time(ts):
                valid_times.append(ts)
            else:
                invalid_times.append(ts)

        # Extract unique dates
        unique_dates = set()
        for ts in valid_times:
            if " " in ts:
                date = ts.split()[0]
                unique_dates.add(date)

        # Check daily completeness for each date
        daily_checks = {}
        for date in sorted(unique_dates):
            daily_checks[date] = self._check_daily_completeness(trading_times, date)

        # Check for duplicates
        has_duplicates = len(trading_times) != len(set(trading_times))

        # Compile results
        result = {
            "total_times": len(trading_times),
            "valid_times": len(valid_times),
            "invalid_times": len(invalid_times),
            "invalid_list": invalid_times,
            "unique_dates": sorted(list(unique_dates)),
            "num_trading_days": len(unique_dates),
            "daily_completeness": daily_checks,
            "has_duplicates": has_duplicates,
            "is_valid": len(invalid_times) == 0 and not has_duplicates
        }

        # Print summary if verbose
        if verbose:
            print("=" * 60)
            print("交易时间验证结果")
            print("=" * 60)
            print(f"总时间点数: {result['total_times']}")
            print(f"有效时间点: {result['valid_times']}")
            print(f"无效时间点: {result['invalid_times']}")

            if result['invalid_times'] > 0:
                print(f"\n⚠️  无效时间点列表:")
                for ts in result['invalid_list']:
                    print(f"   - {ts}")

            print(f"\n交易日数: {result['num_trading_days']}")
            print(f"日期范围: {result['unique_dates'][0] if result['unique_dates'] else 'N/A'} 至 "
                  f"{result['unique_dates'][-1] if result['unique_dates'] else 'N/A'}")

            # Summary of daily completeness
            complete_days = sum(1 for check in daily_checks.values() if check['is_complete'])
            incomplete_days = len(daily_checks) - complete_days

            print(f"\n完整交易日: {complete_days}/{len(daily_checks)}")
            if incomplete_days > 0:
                print(f"不完整交易日: {incomplete_days}")

            if has_duplicates:
                print("\n⚠️  检测到重复时间点")

            print(f"\n总体验证: {'✅ 通过' if result['is_valid'] else '❌ 失败'}")
            print("=" * 60)

        return result

    def __str__(self) -> str:
        return (
            f"BaseAgentAStockHourly(signature='{self.signature}', basemodel='{self.basemodel}', "
            f"market='cn', stocks={len(self.stock_symbols)})"
        )

    def __repr__(self) -> str:
        return self.__str__()
