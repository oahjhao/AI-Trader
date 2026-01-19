from pathlib import Path
from typing import Tuple

# NOTE:
# 统一的数据落盘路径规划：所有与日志、持仓、run_id 相关的路径都通过
# 这一层来计算，避免在各个入口里手写路径字符串，方便未来调整目录
# 结构（比如挂载到不同的数据盘或对象存储同步目录）。

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _normalize_log_path(log_path_cfg: str) -> Path:
    """Resolve log_path from config to an absolute directory under project root.

    约定：
    - log_path_cfg 一般形如 "./data/agent_data_astock" 或 "data/agent_data"；
    - 统一去掉前导的 "./"，然后拼到 PROJECT_ROOT 下面。
    """
    # 去掉前导的 "./"，保持与旧代码 PROJECT_ROOT / log_path 的效果一致
    if log_path_cfg.startswith("./"):
        log_path_cfg = log_path_cfg[2:]
    return PROJECT_ROOT / log_path_cfg


def get_signature_root(log_path_cfg: str, signature: str) -> Path:
    """根目录: <PROJECT_ROOT>/<log_path>/<signature>"""
    return _normalize_log_path(log_path_cfg) / signature


def get_position_file(log_path_cfg: str, signature: str) -> Path:
    """持仓文件路径: <root>/position/position.jsonl"""
    return get_signature_root(log_path_cfg, signature) / "position" / "position.jsonl"


def get_lock_file(log_path_cfg: str, signature: str) -> Path:
    """锁文件路径: <root>/.lock，用于单 signature 并发保护"""
    return get_signature_root(log_path_cfg, signature) / ".lock"


def get_run_base_dir(log_path_cfg: str, signature: str, run_id: str) -> Path:
    """本次运行的基础目录: <root>/runs/<run_id>

    当前阶段仅负责创建目录，具体要落哪些结果文件由上层逐步接入。
    """
    return get_signature_root(log_path_cfg, signature) / "runs" / run_id
