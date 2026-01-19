from importlib import import_module
from typing import Dict, Type

# Agent class mapping table - for dynamic import and instantiation
# 统一维护，供 main.py / main_parrallel.py 以及后续的统一 Runner 使用。
AGENT_REGISTRY: Dict[str, Dict[str, str]] = {
    "BaseAgent": {
        "module": "agent.base_agent.base_agent",
        "class": "BaseAgent",
    },
    "BaseAgent_Hour": {
        "module": "agent.base_agent.base_agent_hour",
        "class": "BaseAgent_Hour",
    },
    "BaseAgentAStock": {
        "module": "agent.base_agent_astock.base_agent_astock",
        "class": "BaseAgentAStock",
    },
    "BaseAgentAStockHourly": {
        "module": "agent.base_agent_astock.base_agent_astock_hourly",
        "class": "BaseAgentAStockHourly",
    },
    "BaseAgentCrypto": {
        "module": "agent.base_agent_crypto.base_agent_crypto",
        "class": "BaseAgentCrypto",
    },
}


def get_agent_class(agent_type: str) -> Type:
    """Dynamically import and return the corresponding class based on agent type.

    This is moved out of main.py / trader.runner so that:
    - 所有入口统一从这里拿 Agent 实现，方便后续扩展美股/港股等新 Agent。
    - 也便于在不同进程/容器中保持一致的映射。
    """
    if agent_type not in AGENT_REGISTRY:
        supported_types = ", ".join(AGENT_REGISTRY.keys())
        raise ValueError(
            f"❌ Unsupported agent type: {agent_type}\n"
            f"   Supported types: {supported_types}"
        )

    agent_info = AGENT_REGISTRY[agent_type]
    module_path = agent_info["module"]
    class_name = agent_info["class"]

    try:
        module = import_module(module_path)
        agent_class = getattr(module, class_name)
        print(f"✅ Successfully loaded Agent class: {agent_type} (from {module_path})")
        return agent_class
    except ImportError as e:
        raise ImportError(f"❌ Unable to import agent module {module_path}: {e}")
    except AttributeError as e:
        raise AttributeError(f"❌ Class {class_name} not found in module {module_path}: {e}")
