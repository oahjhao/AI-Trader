"""Core trading package for AI-Trader.

This package centralizes shared utilities such as configuration loading
and agent class registry, so that live trading和回测可以复用同一套
入口逻辑，后续也便于容器化和多进程/多容器拆分。
"""

from .config import load_config  # re-export for convenience
from .agents import get_agent_class, AGENT_REGISTRY  # re-export
