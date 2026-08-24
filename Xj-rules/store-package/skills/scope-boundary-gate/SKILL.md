---
name: scope-boundary-gate
description: 范围边界门禁。编码阶段执行，拦截超范围开发，保障需求聚焦。
---

# 范围边界门禁（Scope Boundary Gate）

## 触发条件
- 编码阶段启动前
- 开发过程中发现"可顺便加上的功能"

## 核心规则
**超范围功能不交付，禁止自主拓展需求。**

发现当前PRD/P0-P2清单之外的功能点时：
1. **立即暂停**当前开发工作
2. 记录该功能点的价值与成本
3. 汇报PM确认是否纳入本轮
4. PM确认通过才能做，否则即使代码已写也要删掉

## 自检清单（编码阶段每轮执行）

> **越界判定禁止手写（2026-08-15 裁定，gate-switch 机械门禁 · SV-GATE-001 重生版）：每轮自检前必须扳动
> `python3 ~/.agents/skills/scope_boundary/scripts/gate_switch.py --spec ~/.agents/skills/scope_boundary/scripts/specs/scope_boundary.json --set repo=<仓库> --set allow=<范围清单文件> [--set base=<git基线>]`
> 照抄输出——判 A（变更全在范围内）才允许提交；判 B 则越界清单原文上报 PM，确认纳入或删除（即使代码已写也要删掉）。前置：task-breakdown 输出须含范围文件清单。**

- [ ] 当前实现的功能是否都在PRD功能清单内？
- [ ] 如果有不在清单内的功能，是否已经PM确认？
- [ ] 是否有"反正顺手就做了"的逻辑？
- [ ] 修改涉及的文件是否都在原始需求范围内？

## 例外情况
仅以下情况可不经PM确认：
- 修复Bug时的必要连带修改
- 重构不改变外部行为的内部优化
- IDE自动生成的配置/类型声明
