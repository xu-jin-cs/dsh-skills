"""observe 模块（P1）：声明加载，不依赖引擎内核。"""
from .contract_loader import scan, validate_observe, ContractError  # noqa: F401
