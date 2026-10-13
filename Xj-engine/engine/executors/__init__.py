# engine.executors — 节点执行器协议（2026-10-13 REFORM-GATE 判A · node_executor_protocol_20261013.md）
#
# 定位：flow.yml 节点 `executor` 声明的可插拔内部执行器。执行器只负责"节点内部怎么干活"
# （多步骤编排/并行扇出/条件回流），节点的"能不能流转"仍由 flow_kernel + ET 裁决。
# 红线（详见 docs/node_executor_contract.md）：
#   1. 执行器产物无绿色通道，必须照常过 flow_kernel advance + ET 门禁；
#   2. 执行器内部控制流（如 LangGraph 条件边）禁止替代引擎状态机跃迁；
#   3. 执行轨迹必须落盘，供证据链门禁核验。
from .node_executor import ExecutorContext, ExecutorResult, NodeExecutor

__all__ = ["ExecutorContext", "ExecutorResult", "NodeExecutor"]
