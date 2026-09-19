---
name: agent-eval
description: "Agent/Skills 专项能力评估与可视化报告技能（2026-09-18 用户裁定定稿）。执行 scripts/eval_agents.py，只读采集 ~/.agents/skills/ 全部技能 → 体系级 9 维评分（冻结基线+信号确定性加减）→ 逐技能 ability 维机械评分 → 强弱识别（阻断/高风险/一般优化三级+行动指引）→ 综合排名 → 产出两张深色科技风报告图（agent_radar.png 多维能力雷达 / agent_rank.png 综合能力排名榜）+ agent_rank.md + report.html + shards JSON。范围仅 Agent/Skills，不含 RAG/引擎/规则闸/设计者反推。触发：/agenteval、agent能力评估、技能评估、agent排名、能力可视化报告、评估报告出图。"
metadata:
  version: "1.0.0"
  author: agent-eval
---

# agent-eval — Agent/Skills 专项能力评估·可视化报告

核心目标：**一条命令执行脚本，生成 Agent 能力可视化报告**（雷达图 + 排名榜 + 文字报告）。

## 执行步骤（照抄执行，禁止手写判定）

1. **执行评估**（默认内部自研 9 维模式）：
   ```bash
   python3 ~/.agents/skills/agent-eval/scripts/eval_agents.py
   ```
   缺 matplotlib 时脚本自动改用 `~/.browser-use-env/bin/python3` 重启自身，无需人工处理。
2. **核对控制台三行回执**：`[采集]`（有效技能数/脚本数/关键技能缺失/retro 水位/路径漂移数）、`saved`（两张图路径+体系综合分与评级）、`[排名]`（Top3 + 阻断计数）。exit≠0 或缺回执即失败，禁止未验证报完成。
3. **交付**：向用户报告本轮 round 目录路径、体系综合分/评级、Top3、阻断/高风险短板条数，并附两张图与 report.html 的链接。

## 可选模式

| 命令 | 用途 |
|---|---|
| `--mode generic` | 通用 7 基础维（机制创新性/自动化闭环降为附加标签）；`--with-optional` 按 7:1.5 降权并入 |
| `--compare <上轮 shards/skills_system.json>` | 雷达图叠加上轮灰色虚线，两轮对比涨跌 |
| `--config cfg.json` | 覆盖 skills_dir/key_skills/阈值/开关，用于评估其他本地文件式 Agent |
| `--out <目录>` | 自定义产出目录（默认 `~/Desktop/agent-skills-eval-<YYYYMMDD>/`） |

## 评分口径（与脚本 docstring 一致，改动须先改脚本）

- 体系级 9 维冻结基线（2026-09-09）：9/9/8/8.5/8/8/7/9/9；调整版信号加减（2026-09-18 裁定）：关键技能缺失阶梯扣分 -0.3/个上限 -1.0、全齐 +0.5、全库零漂移可维护 +0.5、retro<200 扣 -1.0 绑定 `enable_agent_self_evolution` 开关；clamp [0,10] 步进 0.5；overall=均值；评级 A-≥85/B+≥80/B≥75/B-≥70/C+≥65/C≥55/D。
- 逐技能 9 维机械评分（RUBRIC 规则表：frontmatter/行数/脚本数/漂移引用/六组关键词，无裁量）。
- 短板三级：【阻断】frontmatter 契约缺失＞【高风险】失效路径引用＞【一般优化】文档/执行面完善类；每条带行动指引。
- 排名：overall 降序 → 阻断数升序 → 核心四维（功能覆盖/工程实现/可靠可验证/安全治理）均值降序 → 完全同分并列。

## 出图契约（深色科技风，2026-09-18 用户三次裁定定稿）

- **图1 `images/agent_radar.png`**：体系多维雷达，青 #2DD4BF，标杆线 85=A-；底部强弱清单区从底边锚定紧凑排列、标题居中、明细左对齐，每条独立成行不截断，亮点/短板各最多 10 行并在图上标注该规则与总条数（超出指向 agent_rank.md），短板按等级配色。
- **图2 `images/agent_rank.png`**：综合能力排名榜（卡片式无条形），全部技能 3 栏上榜；每卡三行——`#排名 技能名`+`综合分 评级`（17pt 加粗、评级配色）／绿字 ◆优势整行／短板整行（红阻断/黄高风险/灰一般）；全文不截断自动换行，短板的"（例：路径）"图上省略、完整见 agent_rank.md。
- 样式常量：背景 #0B1120 / 面板 #111A2E / 网格 #334155 / 文字 #E5E7EB·#94A3B8；字体回退链 PingFang SC → Heiti SC → Arial Unicode MS。

## 规则

1. **全程只读**：采集只 glob/读文件/HTTP GET/pgrep，禁止改动任何被评估技能文件。
2. **证据锚点制**：一切分数来自机械信号与冻结基线加减，禁止凭印象改分；调整口径必须落在脚本代码里。
3. **范围纪律**：本技能只评 Agent/Skills；RAG/引擎/规则闸/平台评估走 auto_eval.py（msh-eval 体系），不在此挂载。
4. 产出全部原子写（tmp+os.replace）；round 目录按日期落 ~/Desktop/。

## 产出清单（round 目录）

```
images/agent_radar.png   图1 多维能力雷达（含强弱清单区）
images/agent_rank.png    图2 综合能力排名榜（45 技能全上榜）
agent_rank.md            排名总表+迭代调整方向+各技能详情+筛选指引
baseline.md              体系评分+加减分 notes+Top10
report.html              深色一页报告（两图+评分表+排名总表）
shards/skills_system.json / shards/skills_rank.json
```

## 开发稿与文档

- 设计/口径文档：`~/Desktop/agent-skills-eval/评估方案.md`（最终方案）、`评估逻辑全解.md`（逻辑溯源）
- `~/Desktop/agent-skills-eval/eval_agents.py` 为开发稿副本，**正式调用入口以本技能 scripts/ 为准**；改脚本先改本副本再同步。
