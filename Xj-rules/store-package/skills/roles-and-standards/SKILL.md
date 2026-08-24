---
name: roles-and-standards
description: "角色职责与工程标准规则包：角色分工、工程技能、开发规范、性能优化。"
---

# roles-and-standards — 角色职责与工程标准规则包

纯规则文档包（无脚本）。内容为本体系沉淀的Markdown规则原文，供挂载到项目的规则加载入口使用。

## 内容清单

- `references/02_roles_responsibility.md`
- `references/03_engineering_skills.md`
- `references/04_dev_standard.md`
- `references/10_performance_optimization.md`

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
