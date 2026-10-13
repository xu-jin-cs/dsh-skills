"""节点执行器协议基类（框架无关）。

新建工作流/agent 获得子图编排能力的方式：
  1. flow.yml 节点声明 `executor: <module>:<Class>`（可选字段，未声明维持 LLM 自编排）；
  2. 节点 Agent 进节点后用 Bash 调起执行器（或宿主代码按字段反射加载）；
  3. 执行器跑内部编排（可用 LangGraph/纯 Python/任意框架实现 run()），
     产物按 flow.yml deliverables Schema 落盘；
  4. 照常走 flow_kernel advance + ET 裁决——执行器产物无任何绿色通道。

LangGraph 适配：继承本基类，run() 内惰性 `import langgraph` 并 invoke 子图即可；
基类不依赖 langgraph 包，不装也能导入本模块。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutorContext:
    """节点执行上下文：执行器的全部输入，禁止从隐式环境取数。"""

    node_name: str                      # flow.yml 中的节点名（如 test_lead_full）
    workdir: str                        # 产物落盘目录（通常为 output_delivery/<节点>/）
    inputs: dict[str, str] = field(default_factory=dict)   # 上游交付物路径表 {名称: 路径}
    params: dict[str, Any] = field(default_factory=dict)   # 节点身份契约传入的额外参数
    trace_id: str = ""                  # 引擎 trace_id，用于审计对齐


@dataclass
class ExecutorResult:
    """执行器出参。ok=False 时 error 必填；deliverables 为本次落盘的交付物路径列表。"""

    ok: bool
    deliverables: list[str] = field(default_factory=list)
    error: str = ""
    trace_path: str = ""                # 子图执行轨迹落盘路径（证据链核验数据源）


class NodeExecutor(ABC):
    """节点执行器协议基类。子类只需实现 run()。"""

    @abstractmethod
    def run(self, ctx: ExecutorContext) -> ExecutorResult:
        """执行节点内部编排，产出交付物并返回结果。"""

    def validate_result(self, ctx: ExecutorContext, result: ExecutorResult) -> ExecutorResult:
        """前置自检：交付物文件真实存在且非空。

        注意：这只是执行器层的存在性自检；Schema 合规与流转合法性由
        flow_kernel advance + ET 裁决负责，本方法通过不代表可流转。
        """
        if not result.ok:
            return result
        missing = [
            p for p in result.deliverables
            if not Path(p).is_file() or Path(p).stat().st_size == 0
        ]
        if missing:
            return ExecutorResult(
                ok=False,
                deliverables=result.deliverables,
                error=f"deliverables 缺失或为空: {missing}",
                trace_path=result.trace_path,
            )
        return result
