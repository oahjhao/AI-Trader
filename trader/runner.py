import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from trader.agents import get_agent_class
from trader.config import load_config
from trader.engine import run_single_model


async def _run(
    config_path: Optional[str],
    only_signature: Optional[str] = None,
) -> None:
    """通用 Runner：面向容器/云任务的统一入口.

    - 支持通过 config JSON 决定 agent_type / models 等；
    - 可选 --signature 只跑单个模型，方便一个容器对应一个 signature；
    - 内部复用 run_single_model，保证与 main.py 行为一致。
    """
    config = load_config(config_path)

    # Agent 类型与市场类型
    agent_type = config.get("agent_type", "BaseAgent")
    AgentClass = get_agent_class(agent_type)

    market = config.get("market", "us")
    if agent_type == "BaseAgentAStock":
        market = "cn"
    elif agent_type == "BaseAgentCrypto":
        market = "crypto"

    # 日期区间 + 环境变量覆盖
    init_date = config["date_range"]["init_date"]
    end_date = config["date_range"]["end_date"]

    if os.getenv("INIT_DATE"):
        init_date = os.getenv("INIT_DATE")  # type: ignore[assignment]
        print(f"⚠️  Using environment variable to override INIT_DATE: {init_date}")
    if os.getenv("END_DATE"):
        end_date = os.getenv("END_DATE")  # type: ignore[assignment]
        print(f"⚠️  Using environment variable to override END_DATE: {end_date}")

    # 校验日期区间
    if " " in init_date:
        init_dt = datetime.strptime(init_date, "%Y-%m-%d %H:%M:%S")
    else:
        init_dt = datetime.strptime(init_date, "%Y-%m-%d")

    if " " in end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    if init_dt > end_dt:
        print("❌ INIT_DATE is greater than END_DATE")
        raise SystemExit(1)

    # 过滤启用的模型
    enabled_models = [m for m in config["models"] if m.get("enabled", True)]
    if only_signature:
        enabled_models = [m for m in enabled_models if m.get("signature") == only_signature]
        if not enabled_models:
            print(f"⚠️ No enabled model found for signature: {only_signature}")
            return

    model_list_str = [m.get("name", m.get("signature")) for m in enabled_models]
    print("🚀 Starting trader runner (container/cloud mode)")
    print(f"🤖 Agent type: {agent_type}")
    print(f"🌍 Market: {market}")
    print(f"📅 Date range: {init_date} to {end_date}")
    print(f"🤖 Model list: {model_list_str}")
    if only_signature:
        print(f"🎯 Filtered signature: {only_signature}")

    for model_config in enabled_models:
        await run_single_model(
            AgentClass=AgentClass,
            agent_type=agent_type,
            market=market,
            config=config,
            model_config=model_config,
            init_date=init_date,
            end_date=end_date,
        )

    print("🎉 Runner completed all models")

    # 交易完成，容器退出前推送最终持仓信息
    try:
        print("\n📤 推送最终持仓信息...")
        project_root = Path(__file__).parent.parent
        push_script = project_root / "scripts" / "immediate_push.py"
        if push_script.exists():
            cmd = [sys.executable, str(push_script)]
            if config_path:
                cmd.extend(["--config", config_path])
            
            # 如果指定了 signature 或只有一个模型，则增加 --signature 限制
            if only_signature:
                cmd.extend(["--signature", only_signature])
            elif len(enabled_models) == 1:
                signature = enabled_models[0].get("signature")
                if signature:
                    cmd.extend(["--signature", signature])
            
            import subprocess
            subprocess.run(cmd, check=False)
        else:
            print(f"⚠️ 找不到推送脚本: {push_script}")
    except Exception as e:
        print(f"❌ 推送最终持仓信息失败: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Trader unified runner for containers/cloud")
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Path to config JSON (same as main.py). If omitted, use default_config.json",
    )
    parser.add_argument(
        "--signature",
        dest="signature",
        default=None,
        help="Run only this model signature (one container per signature is recommended)",
    )
    args = parser.parse_args()

    if args.config:
        print(f"📄 Using specified configuration file: {args.config}")
    else:
        print("📄 Using default configuration file: configs/default_config.json")

    asyncio.run(_run(args.config, args.signature))


if __name__ == "__main__":
    main()
