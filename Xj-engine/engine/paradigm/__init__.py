"""范式选型机制（引擎侧唯一实现）：打分 / 置信三档 / 三门校验 / 样本回流 / 逃逸检测。"""
from .matcher import confidence_of, decide, input_hash, score_all  # noqa: F401
from .gates import run as validate_template  # noqa: F401
from .escape import detect as detect_escape  # noqa: F401
from .spec import load, paradigm_version, thresholds  # noqa: F401

__all__ = ["decide", "confidence_of", "score_all", "input_hash",
           "validate_template", "detect_escape", "load", "paradigm_version", "thresholds"]
