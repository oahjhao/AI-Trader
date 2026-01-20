import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from pathlib import Path as _Path
from dotenv import load_dotenv

load_dotenv()

from prompts.agent_prompt import all_nasdaq_100_symbols
# from prompts.agent_prompt import all_sse_50_symbols
# Import tools and prompts
from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import load_stock_list

# Agent class mapping and config loader are centralized in trader package
from trader.agents import AGENT_REGISTRY, get_agent_class
from trader.config import load_config
async def main(config_path=None):
    """Run trading experiment using BaseAgent class

    Args:
        config_path: Configuration file path, if None use default config
    """
    # Load configuration file
    config = load_config(config_path)

    # Get Agent type
    agent_type = config.get("agent_type", "BaseAgent")
    try:
        AgentClass = get_agent_class(agent_type)
    except (ValueError, ImportError, AttributeError) as e:
        print(str(e))
        exit(1)

    # Get market type from configuration
    market = config.get("market", "us")
    # Auto-detect market from agent_type (BaseAgentAStock always uses CN market)
    if agent_type == "BaseAgentAStock":
        market = "cn"
    elif agent_type == "BaseAgentCrypto":
        market = "crypto"

    if market == "crypto":
        print(f"🌍 Market type: Cryptocurrency (24/7 trading)")
    elif market == "cn":
        print(f"🌍 Market type: A-shares (China)")
    else:
        print(f"🌍 Market type: US stocks")

    # Get date range from configuration file
    INIT_DATE = config["date_range"]["init_date"]
    END_DATE = config["date_range"]["end_date"]

    # Environment variables can override dates in configuration file
    if os.getenv("INIT_DATE"):
        INIT_DATE = os.getenv("INIT_DATE")
        print(f"⚠️  Using environment variable to override INIT_DATE: {INIT_DATE}")
    if os.getenv("END_DATE"):
        END_DATE = os.getenv("END_DATE")
        print(f"⚠️  Using environment variable to override END_DATE: {END_DATE}")

    # Validate date range
    # Support both YYYY-MM-DD and YYYY-MM-DD HH:MM:SS formats
    if ' ' in INIT_DATE:
        INIT_DATE_obj = datetime.strptime(INIT_DATE, "%Y-%m-%d %H:%M:%S")
    else:
        INIT_DATE_obj = datetime.strptime(INIT_DATE, "%Y-%m-%d")
    
    if ' ' in END_DATE:
        END_DATE_obj = datetime.strptime(END_DATE, "%Y-%m-%d %H:%M:%S")
    else:
        END_DATE_obj = datetime.strptime(END_DATE, "%Y-%m-%d")
    
    if INIT_DATE_obj > END_DATE_obj:
        print("❌ INIT_DATE is greater than END_DATE")
        exit(1)

    # Get model list from configuration file (only select enabled models)
    enabled_models = [model for model in config["models"] if model.get("enabled", True)]

    from trader.engine import run_single_model

    print("🚀 Starting trading experiment")
    print(f"🤖 Agent type: {agent_type}")
    print(f"📅 Date range: {INIT_DATE} to {END_DATE}")
    print(f"🤖 Model list: {[m.get('name', m.get('signature')) for m in enabled_models]}")

    for model_config in enabled_models:
        await run_single_model(
            AgentClass=AgentClass,
            agent_type=agent_type,
            market=market,
            config=config,
            model_config=model_config,
            init_date=INIT_DATE,
            end_date=END_DATE,
        )

    print("🎉 All models processing completed!")

    # 交易完成，容器退出前推送最终持仓信息
    try:
        print("\n📤 推送最终持仓信息...")
        push_script = Path(__file__).parent / "scripts" / "immediate_push.py"
        if push_script.exists():
            cmd = [sys.executable, str(push_script)]
            if config_path:
                cmd.extend(["--config", config_path])
            
            # 如果只有一个模型，也可以指定 signature
            if len(enabled_models) == 1:
                signature = enabled_models[0].get("signature")
                if signature:
                    cmd.extend(["--signature", signature])
            
            import subprocess
            subprocess.run(cmd, check=False)
        else:
            print(f"⚠️ 找不到推送脚本: {push_script}")
    except Exception as e:
        print(f"❌ 推送最终持仓信息失败: {e}")


if __name__ == "__main__":
    import sys

    # Support specifying configuration file through command line arguments
    # Usage: python livebaseagent_config.py [config_path]
    # Example: python livebaseagent_config.py configs/my_config.json
    config_path = sys.argv[1] if len(sys.argv) > 1 else None

    if config_path:
        print(f"📄 Using specified configuration file: {config_path}")
    else:
        print(f"📄 Using default configuration file: configs/default_config.json")

    asyncio.run(main(config_path))
