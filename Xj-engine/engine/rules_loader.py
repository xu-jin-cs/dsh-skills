"""rules_loader.py — contract_rules/ 规则表唯一读取入口（改造清单 v2 §一）。

铁律（契约 §一-2/§九-2）：
  - 规则唯一真源是 engine/contract_rules/*.yaml，执行器代码禁写默认值与字面量；
  - get() 缺键即抛 RuleMissingError，禁止返回默认值兜底；
  - options 白名单：只有规则表中显式标记 overridable: true 的键可被 payload.options 覆盖。

overridable 标注两种形态（loader 解包/剥离后按原值返回，消费方无感）：
  1. 映射节点内 `overridable: true`        → 整棵子树可覆盖（如 validation.size_tiers）
  2. 标量叶子 `{value: X, overridable: true}` → 该叶子可覆盖（如 chunking.max_token）

进程内缓存：load_rules() 首次加载后驻留；测试用 reload() 强制重载。
"""
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # 不自写 YAML 解析器（任务规约），直接报告依赖缺失
    raise ImportError("rules_loader 依赖 PyYAML：请 pip install pyyaml") from exc

RULES_DIR = Path(__file__).resolve().parent / "contract_rules"

# 8 张规则表（文件名去后缀即表名；点号路径第一段）
TABLES = (
    "validation",
    "parsing",
    "cleaning",
    "chunking",
    "retry_exception",
    "pipeline",
    "storage",
    "isolation",
)


class RuleMissingError(KeyError):
    """规则表缺键：执行器禁止默认值兜底，缺键即报错。"""


_rules: dict | None = None
_overridable: frozenset | None = None


def _unwrap(node, path: str, overridable: set):
    """剥离 overridable 标记并登记路径，返回消费方可见的干净树。"""
    if isinstance(node, dict):
        # 形态 2：标量叶子包装 {value, overridable}
        if set(node.keys()) == {"value", "overridable"}:
            if node["overridable"] is True:
                overridable.add(path)
            return node["value"]
        out = {}
        if node.get("overridable") is True:  # 形态 1：整棵子树可覆盖
            overridable.add(path)
        for k, v in node.items():
            if k == "overridable":
                continue  # 标记是元数据，不进规则树
            out[k] = _unwrap(v, f"{path}.{k}" if path else str(k), overridable)
        return out
    if isinstance(node, list):
        return [_unwrap(v, path, overridable) for v in node]
    return node


def load_rules() -> dict:
    """加载 8 张规则表（进程内缓存）。缺表/解析失败即抛错，不兜底。"""
    global _rules, _overridable
    if _rules is not None:
        return _rules
    rules: dict = {}
    overridable: set = set()
    for table in TABLES:
        path = RULES_DIR / f"{table}.yaml"
        if not path.is_file():
            raise RuleMissingError(f"规则表缺失: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise RuleMissingError(f"规则表 {table} 顶层必须是映射: {path}")
        rules[table] = _unwrap(data, table, overridable)
    _rules = rules
    _overridable = frozenset(overridable)
    return _rules


def get(dot_path: str):
    """点号路径取值，如 get("validation.whitelist")。缺键抛 RuleMissingError。"""
    rules = load_rules()
    node = rules
    walked = []
    for seg in str(dot_path).split("."):
        walked.append(seg)
        if isinstance(node, dict) and seg in node:
            node = node[seg]
        else:
            raise RuleMissingError(
                f"规则缺键: {dot_path!r}（已走到 {'.'.join(walked[:-1]) or '<root>'}，"
                f"可用键: {sorted(node) if isinstance(node, dict) else '非映射节点'}）")
    return node


def list_overridable() -> frozenset:
    """全部 overridable 键的完整点号路径集合（如 'validation.size_tiers'）。

    contract.py options 白名单校验以此为准：options 键按完整路径或叶子后缀匹配。
    """
    load_rules()
    return _overridable


def reload() -> dict:
    """清缓存强制重载（测试专用）。"""
    global _rules, _overridable
    _rules = None
    _overridable = None
    return load_rules()
