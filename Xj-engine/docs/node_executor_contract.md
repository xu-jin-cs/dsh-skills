# 节点执行器契约（node_executor_contract）

> 落地依据：2026-10-13 REFORM-GATE 判A（块文件 `~/.agents/logs/reform_blocks/node_executor_protocol_20261013.md`）。
> 定位：**框架无关的节点内部编排协议**。协议不绑定任何子图框架（2026-11-04 起：langgraph 已移出引擎依赖清单，框架由执行器作者自备）。
> 形态：A 方案（节点内执行器）——引擎内核零改动，执行器只替换"节点内部怎么干活"。

## 1. 解决什么问题

复杂节点内部的多步编排（并行扇出/条件回流/循环回归）靠 LLM 自编排有跳步风险；
把节点内部控制流固化为子图代码后：**步骤不可跳过、并行是真实并行、断点恢复到步骤级、
确定性步骤零 token**。从引擎视角节点仍是原子节点，上下游契约零变化。

## 2. flow.yml 接入方式（新建工作流/agent 默认获得）

节点声明可选字段 `executor`：

```yaml
- name: test_lead_full
  executor: my_flow.executors:TestFullExecutor   # <module>:<Class>，可选
  deliverables: [...]                             # 不变
  branch_conditions: {...}                        # 不变
```

- **声明了 executor**：节点 Agent 进节点后反射加载该类，构造 `ExecutorContext` 调 `run()`，
  产物落盘 → 照常 `flow_kernel.py advance` → ET 裁决。
- **未声明**：维持现状（LLM 按 SKILL.md 自编排）。老 flow.yml 无需任何改动，向后兼容。

## 3. 协议三件套（engine/executors/node_executor.py）

| 件 | 职责 |
|---|---|
| `ExecutorContext` | 全部输入显式化：node_name / workdir / inputs（上游交付物路径表）/ params / trace_id；禁止从隐式环境取数 |
| `ExecutorResult` | ok / deliverables（落盘路径列表）/ error / trace_path（执行轨迹，证据链数据源） |
| `NodeExecutor` | 抽象基类，子类只实现 `run(ctx)`；`validate_result()` 自带产物存在性前置自检 |

## 4. 三条红线（叠加不破坏体系的前提）

1. **引擎裁决不可绕过**：执行器产物必须满足 flow.yml deliverables Schema 并照常过
   flow_kernel + ET 门禁——执行器没有绿色通道，`validate_result` 通过 ≠ 可流转。
2. **两层状态机不混**：执行器内部控制流（如子图条件边）是"干活流程"；
   引擎状态机 allowed_pairs（FlowStatus 枚举实测 17 值，engine/flow/state.py）是"合法流转"——禁止在执行器内触发状态机跃迁
   （例如子图里直接推进"部署"即越权）。
3. **执行轨迹必须落盘**：trace_path 指向子图运行轨迹（所选框架 checkpoint/trace 或自实现日志），
   写入 output_delivery/<节点>/，供证据链门禁（md5 防复用/audit）核验；无轨迹 = 证据链断。

## 5. 子图编排适配指引（框架无关）

**状态（2026-10-13 合并完成；2026-11-04 依赖清退）**：引擎**不捆绑**任何子图框架——
requirements-optional.txt 已移除 langgraph（全仓零 import 实证），执行器作者若选用
需自行声明并安装。下方 langgraph 示例仅为历史验证过的范例（当年最小三路并行子图
冒烟通过：START 扇出 → aggregate 聚合 → END）。

```python
from engine.executors import ExecutorContext, ExecutorResult, NodeExecutor

class TestFullExecutor(NodeExecutor):
    def run(self, ctx: ExecutorContext) -> ExecutorResult:
        from langgraph.graph import StateGraph          # 惰性导入，框架依赖由执行器作者自备
        graph = build_test_full_graph()                  # 三路扇出/回流/聚合子图
        final = graph.invoke({"inputs": ctx.inputs, "workdir": ctx.workdir})
        return self.validate_result(ctx, ExecutorResult(
            ok=True,
            deliverables=[f"{ctx.workdir}/test-master-report.json",
                          f"{ctx.workdir}/defect-auto-grade.json"],
            trace_path=f"{ctx.workdir}/subgraph_trace.jsonl",
        ))
```

**并行写入坑（2026-10-13 实测，langgraph 使用者注意）**：并行分支写同一 state key 必须用 reducer 声明，
否则 `InvalidUpdateError: Can receive only one value per step`——
`class S(TypedDict): results: Annotated[list, operator.add]`。首个子图作者务必注意。

子图框架均为执行器作者自备依赖（引擎零捆绑，2026-11-04 用户裁定）；
未安装时仅 executor 声明节点不可用，引擎与其余节点不受影响。

## 6. 验收口径

新建工作流声称"已接入节点执行器"的完成判据：
① flow.yml 节点含 executor 声明；② 执行器类继承 NodeExecutor 且过 `validate_result`；
③ 一次真实运行的 ExecutorResult + trace 文件落盘；④ flow_kernel advance 返回 success。
四条缺一即未接入，禁止口头声称。
