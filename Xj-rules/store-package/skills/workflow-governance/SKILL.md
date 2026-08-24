---
name: workflow-governance
description: "多智能体工作流治理规则包：目录安全铁律、流程A/B/C 全流程、任务路由。"
---

# workflow-governance — 工作流治理规则包

纯规则文档包（无脚本）。内容为本体系沉淀的Markdown规则原文，供挂载到项目的规则加载入口使用。

## 内容清单

- `references/00_root_safety.md`
- `references/01_workflows.md`
- `references/01a_flow_a_new_feature.md`
- `references/01b_flow_b_bugfix.md`
- `references/01c_flow_c_wrapup.md`
- `references/01d_flow_de_aux.md`
- `references/01e_retro_system.md`
- `references/01f_appendix.md`
- `references/13_workflow_router.md`

## 使用方式

1. 直接把 `references/` 下的规则文件拷入项目的 `rules/` 目录（或 `~/.agents/rules/`）；
2. 在项目根 `AGENTS.md` 加入口声明，示例：

```markdown
# AGENTS.md — 全局顶层入口

本项目采用路径匹配按需加载规则，不会一次性载入全部约束文本，规避上下文超限。
全局强制底线：所有文件操作必须严格遵循 .agents/rules/00_root_safety.md 目录安全铁律。

细分业务规则存放目录：.agents/rules/
```

规则正文中引用的 `gate-switch` 闸 spec 路径，对应本商店中同名独立闸技能（如 `zero_residual/`）；未随包发行的闸在正文中均有注记说明。
