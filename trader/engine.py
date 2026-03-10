import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from prompts.agent_prompt import all_nasdaq_100_symbols
from tools.general_tools import write_config_value
from tools.price_tools import load_stock_list
from trader.storage import (
    get_lock_file,
    get_position_file,
    get_run_base_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SignatureLock:
    """File-based lock to avoid concurrent writes for the same signature/log_path."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.acquired = False

    def acquire(self) -> None:
        """Acquire the lock file (atomic file creation).
        If the lock already exists, check if it's stale (older than 2 hours).
        If stale, force remove it and try again.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        info = {
            "pid": os.getpid(),
            "created_at": datetime.utcnow().isoformat(),
        }
        data = json.dumps(info).encode("utf-8")
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        except FileExistsError:
            # Lock file exists, check if it's stale
            try:
                import time
                lock_age_seconds = time.time() - self.lock_path.stat().st_mtime
                lock_age_hours = lock_age_seconds / 3600
                
                if lock_age_hours > 2:  # Stale lock older than 2 hours
                    print(f"⚠️  Found stale lock file (age: {lock_age_hours:.1f} hours), removing...")
                    self.lock_path.unlink()
                    print("✅ Stale lock removed, retrying...")
                    # Retry acquiring the lock
                    fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    try:
                        os.write(fd, data)
                    finally:
                        os.close(fd)
                else:
                    print(
                        f"❌ Another run is already in progress for {self.lock_path.parent.name}. "
                        f"Lock age: {lock_age_hours:.1f} hours. "
                        "Refusing to start to avoid concurrent position writes."
                    )
                    # 使用RuntimeError而不是SystemExit，让调用者能够在finally中清理
                    raise RuntimeError(
                        f"Lock file already exists for {self.lock_path.parent.name}"
                    )
            except FileNotFoundError:
                # Lock was removed between check and stat, retry
                print("♻️  Lock file disappeared, retrying...")
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
        self.acquired = True

    def release(self) -> None:
        if self.acquired and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            finally:
                self.acquired = False


async def run_single_model(
    AgentClass: type,
    agent_type: str,
    market: str,
    config: Dict[str, Any],
    model_config: Dict[str, Any],
    init_date: str,
    end_date: str,
) -> None:
    """Run one model (signature) over a date range.

    这是对 main.py 中单个 model 处理逻辑的抽象封装，后续无论是实盘
    还是回测，只要给定同样的配置和时间区间，都可以通过这个函数来
    统一执行。并发执行时，只要不同进程/容器使用不同 signature，
    各自的数据落盘仍然互不影响。
    """
    agent_config = config.get("agent_config", {})
    log_config = config.get("log_config", {})

    max_steps = agent_config.get("max_steps", 10)
    max_retries = agent_config.get("max_retries", 3)
    base_delay = agent_config.get("base_delay", 0.5)
    initial_cash = agent_config.get("initial_cash", 10000.0)

    model_name = model_config.get("name", "unknown")
    basemodel = model_config.get("basemodel")
    signature = model_config.get("signature")
    openai_base_url = model_config.get("openai_base_url", None)
    openai_api_key = model_config.get("openai_api_key", None)

    # Validate required fields
    if not basemodel:
        print(f"❌ Model {model_name} missing basemodel field")
        return
    if not signature:
        print(f"❌ Model {model_name} missing signature field")
        return

    print("=" * 60)
    print(datetime.now())
    print(f"🤖 Processing model: {model_name}")
    print(f"📝 Signature: {signature}")
    print(f"🔧 BaseModel: {basemodel}")

    # Resolve log path, position file and lock file
    log_path = log_config.get("log_path", "./data/agent_data")
    position_file = get_position_file(log_path, signature)
    lock_path = get_lock_file(log_path, signature)

    # Prepare run_id and run directory (for future multi-run storage)
    run_id = (
        model_config.get("run_id")
        or os.getenv("RUN_ID")
        or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    )
    run_base_dir = get_run_base_dir(log_path, signature, run_id)
    run_base_dir.mkdir(parents=True, exist_ok=True)
    write_config_value("RUN_ID", run_id)
    print(f"🧾 Run ID: {run_id}, run directory: {run_base_dir}")

    lock = SignatureLock(lock_path)
    lock.acquire()
    try:
        # 如果 position 文件不存在，清理共享 runtime_env 配置，确保从 init_date 重新开始
        if not position_file.exists():
            from tools.general_tools import _resolve_runtime_env_path

            runtime_env_path = Path(_resolve_runtime_env_path())
            print(f"✅ Runtime env path : {runtime_env_path}")
            if runtime_env_path.exists():
                runtime_env_path.unlink()
                print(
                    f"🔄 Position file not found, cleared config for fresh start from {init_date}"
                )

        # 初始化共享运行时配置（目前仍沿用原有 IF_TRADE / MARKET / LOG_PATH 机制）
        write_config_value("SIGNATURE", signature)
        write_config_value("IF_TRADE", False)
        write_config_value("MARKET", market)
        write_config_value("LOG_PATH", log_path)

        print(f"✅ Runtime config initialized: SIGNATURE={signature}, MARKET={market}")

        # 选股逻辑：保持与原来 main.py 一致
        if agent_type == "BaseAgentCrypto":
            stock_symbols = None
        elif market == "cn":
            stock_symbols = load_stock_list(init_date=init_date)
        else:
            stock_symbols = all_nasdaq_100_symbols

        backtest_mode = config.get("backtest_mode", False)

        try:
            if agent_type == "BaseAgentCrypto":
                agent = AgentClass(
                    signature=signature,
                    basemodel=basemodel,
                    log_path=log_path,
                    max_steps=max_steps,
                    max_retries=max_retries,
                    base_delay=base_delay,
                    initial_cash=initial_cash,
                    init_date=init_date,
                    openai_base_url=openai_base_url,
                    openai_api_key=openai_api_key,
                )
            else:
                agent_params: Dict[str, Any] = {
                    "signature": signature,
                    "basemodel": basemodel,
                    "stock_symbols": stock_symbols,
                    "log_path": log_path,
                    "max_steps": max_steps,
                    "max_retries": max_retries,
                    "base_delay": base_delay,
                    "initial_cash": initial_cash,
                    "init_date": init_date,
                    "openai_base_url": openai_base_url,
                    "openai_api_key": openai_api_key,
                }
                if agent_type == "BaseAgentAStock" and backtest_mode:
                    agent_params["backtest_mode"] = True
                    print("ℹ️  Running in backtest mode (search disabled)")

                agent = AgentClass(**agent_params)

            print(f"✅ {agent_type} instance created successfully: {agent}")
            
            # 发送 Agent 启动通知
            try:
                from webhook.notify_client import send_agent_start_notification
                stock_count = len(stock_symbols) if stock_symbols is not None else 0
                send_agent_start_notification(
                    signature=signature,
                    market=market,
                    init_date=init_date,
                    end_date=end_date,
                    stock_count=stock_count,
                    basemodel=basemodel
                )
            except Exception as e:
                print(f"⚠️ 发送启动通知失败: {e}")

            await agent.initialize()
            print("✅ Initialization successful")

            await agent.run_date_range(init_date, end_date)

            summary = agent.get_position_summary()
            if agent.market == "crypto":
                currency_symbol = "USDT"
            elif agent.market == "cn":
                currency_symbol = "¥"
            else:
                currency_symbol = "${}"[0]
            print("📊 Final position summary:")
            print(f"   - Latest date: {summary.get('latest_date')}")
            print(f"   - Total records: {summary.get('total_records')}")
            print(
                f"   - Cash balance: {currency_symbol}{summary.get('positions', {}).get('CASH', 0):,.2f}"
            )

            if agent.market == "crypto" and hasattr(agent, "crypto_symbols"):
                crypto_positions = {
                    k: v
                    for k, v in summary.get("positions", {}).items()
                    if k.endswith("-USDT") and v > 0
                }
                if crypto_positions:
                    print("   - Crypto positions:")
                    for symbol, amount in crypto_positions.items():
                        print(f"     • {symbol}: {amount}")
        except Exception as e:
            print(f"❌ Error processing model {model_name} ({signature}): {str(e)}")
            print(f"📋 Error details: {e}")
            raise
    finally:
        lock.release()

    print("=" * 60)
    print(f"✅ Model {model_name} ({signature}) processing completed")
    print("=" * 60)
