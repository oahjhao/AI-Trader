import json
from pathlib import Path
from typing import Optional

# NOTE:
# This module centralizes configuration loading so that both main.py
# and trader.runner share the same logic. It also makes it easier
# to introduce更严格的配置结构（dataclass / pydantic）而不影响外部调用。

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_config_path(config_path: Optional[str]) -> Path:
    """Resolve config path to an absolute Path.

    - If config_path is None, use PROJECT_ROOT/configs/default_config.json
    - If config_path is relative, treat it as relative to PROJECT_ROOT
    """
    if config_path is None:
        return PROJECT_ROOT / "configs" / "default_config.json"

    p = Path(config_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration JSON used by trading agents.

    This function is intentionally兼容当前 main.py 和 trader.runner
    的行为：
    - 默认读取 configs/default_config.json
    - 保持和原来一样的错误信息与退出方式
    """
    path = _resolve_config_path(config_path)

    if not path.exists():
        print(f"❌ Configuration file does not exist: {path}")
        raise SystemExit(1)

    try:
        with path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"✅ Successfully loaded configuration file: {path}")
        return config
    except json.JSONDecodeError as e:
        print(f"❌ Configuration file JSON format error: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"❌ Failed to load configuration file: {e}")
        raise SystemExit(1)
