> 分片自 01_workflows.md 2026-08-20 拆分，原章节：二、流程说明 / 流程B：Bug 修复（原 L425-501）

## 流程B：Bug 修复

**步骤1** 项目经理记录Bug，指派测试工程师分析归属。

**步骤1.5（硬证据步骤，PM 必执行）** 本环境无 UserPromptSubmit 钩子，`retro-match.sh` 不会自动触发——Bug 诊断派发前 PM 必须执行 `bash ~/.agents/retro-registry/scripts/retro-match.sh "<用户原始输入>"`，并在回复中引用其输出结论行（MATCH FOUND 技能名/分数 或 NO MATCH/近似候选）；跳过必须显式写明理由留痕（匹配入口已扩展为四类全场景，不限于 Bug）： 【铁律】
- **触发范围覆盖四类场景：**
  - ① 故障/Bug修复（bug/报错/崩溃/白屏/404等30+关键词）
  - ② 流程规范/复盘固化（复盘/门禁/规范/审计/标准化/流程约束等）
  - ③ 研发效率/自动化校验（构建校验/打包验证/CI优化/自动化检查等）
  - ④ 技能缺失/能力补齐（缺少方案/能力缺口/流程缺失/空白流程等）
  - ⑤ 通用流程触发（流程A/B/C/D/E 原触发表全部保留）
- 钩子命中任意一类关键词 → 自动提取特征（tokens/role/bug_type/severity/场景分类）
- 自动比对 registry 中全部 retro 技能（短语50%+关键词40%+角色5%+类型5%，阈值0.50）
- registry 中各技能自带 `trigger_phrases`/`bug_type` 标签，算法自动区分故障/流程/效率/能力类技能，高相关优先展示
- 匹配结果写入 `~/.agents/retro-registry/runtime/_active_match.md`（含场景分类标注、角色分派指令、调用时机说明，会话中实时 echo；2026-08-22 修订：旧缓存路径已随迁移废止，唯一活路径以 retro-match.sh 实际写入为准）
- 钩子自动更新 registry-index.json 的 match_count/last_matched
- 钩子同步生成 `~/.agents/retro-registry/role-retro-links.json`（角色↔技能持久映射，含 trigger_scene / invoke_timing / match_count）
- 无 ≥0.50 命中时启用近似召回带：0.20 ≤ score < 0.50 的候选按分降序列出 ≤3 条（含 SKILL.md 路径），由 PM 语义判断适用后手动加载，不自动注入；全部 <0.20 → 不输出干扰信息，不阻断原有流程

**retro 匹配执行判定禁止手写（2026-08-16 裁定，gate-switch 机械门禁；注：retro_match_gate.json 依赖复盘注册表 retro-registry，未随本包发行，接入后自行恢复该 spec）：** 流程启动时先 `touch /tmp/retro_match_marker_<流程标识>` 标记起点；「已执行 retro 匹配」禁止口头声称，Bug 诊断派发前必须扳动 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/retro_match_gate.json --set work_start=/tmp/retro_match_marker_<流程标识>` 照抄结论——判 A（`~/.agents/retro-registry/runtime/_active_match.md` 新于起点 = 本次真实执行留痕）才允许派发诊断；判 B = 未执行/旧产物冒充本次执行，须先执行 retro-match.sh 再重新扳动。回复中是否引用结论行属语义核对，仍留软层。 【铁律】

**角色指派联动（匹配 → 角色绑定 → 自动预置）：**
- `_active_match.md` 包含 `## 角色调用绑定说明` 区块，标注绑定角色、触发场景、调用时机、执行要求
- `role-retro-links.json` 维护全局角色↔技能映射索引，PM 指派角色前可一键读取该角色所有关联技能
- **指派角色时：** 读取 `role-retro-links.json` 过滤对应角色的全部关联 retro 技能，按匹配度降序排列
- **自动预置：** 高匹配技能 Resolution Steps 自动注入开发/流程指令，PM 仅确认是否保留，无需手动查找

**PM此时只需：**
- 读取对话中 echo 的匹配结果（含分派角色），或查看 `_active_match.md` 完整绑定说明
- 匹配成功 → **按角色调用绑定说明分派**，技能 Resolution Steps 已在分派阶段预置
- 匹配失败或 registry 为空 → 正常推进，不附加 retro 技能
- 详见 retro-skill-dispatcher/SKILL.md（`~/.agents/skills/retro-skill-dispatcher`）

**步骤2** test-lead 调用技能10「调试排错」5步法，判断归属（前端/后端/产品设计）→ 汇报项目经理。
- **→ 项目输入 + 代码检索：** 读取 `.prd.md` / `.ui-proto.json` 并使用语义检索搜索相关代码，快速定位 Bug 所在模块和文件

**步骤3** 项目经理确认归属（链式引擎自动确认），正式指派对应开发工程师修复。
对应开发工程师调用技能10「调试排错」+ 技能4「切片实现」修复 → 汇报项目经理。
- **→ 项目输入 + 源码精准读取：** 读取 `.prd.md` / `.ui-proto.json` 与 Bug 文件源码理解上下文

**步骤3.5** 修复完成后，自动触发回归链（无需手动调度）：

首先执行**变更范围分析**（精准回归）：
- test-lead 分析修复涉及的模块/文件/接口范围
- test-case-designer 根据分析结果，只设计受影响的回归用例，而非全量回归
- 精准回归规则：
  - 前端修复 → 只回归该页面的 UI 用例 + 相邻页面交互
  - 后端修复 → 只回归该接口的用例 + 依赖该接口的前端场景
  - 配置变更 → 只回归受影响的功能模块
  - 全量回归标记：修复涉及公共基础设施（中间件/路由/状态管理）时强制全量

**Bug修复阶段强制自检（2026-07-11 新增）：**
修复提交前，对应开发工程师必须执行以下自检（任意一项未通过 → 修复不能提交）： 【规范】
  1. **导入验证**：涉及新文件 → `python3 -c "from <模块> import <函数>"` 验证
  2. **跨文件审计**：涉及函数重命名 → grep 全项目确认旧名称无遗留引用
  3. **依赖同步**：引入新库 → `requirements.txt` 已更新
  4. **配置文档同步**：涉及配置变更 → 相关文档已同步更新

  **自检通过判定禁止手写（2026-08-16 裁定，gate-switch 机械门禁；注：dev_selfcheck.json 包装的 dev_fix_selfcheck.py 属 pm 技能，未随本包发行，可自行按同模式写薄壳 spec）：** 「自检已过」禁止口头声称，必须按本次修复涉及项组合参数扳动 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/dev_selfcheck.json --set "args=--old-name <旧名> --paths <扫描范围> --import-mod <模块> --requirements <requirements.txt路径> --require-lib <新库名> --doc <文档路径> --doc-keyword <关键词>"`（按涉及项裁剪参数，至少一项；dev_fix_selfcheck.py 机械执行旧名零残留+导入冒烟+依赖同步+文档同步）照抄结论——判 A 才允许提交修复；判 B 则 violations 原文即未过项清单，修复后重新扳动。 【铁律】

回归链执行：
test-case-designer 补充/筛选用例 → test-lead 语义审核Q1-Q3 + backend/engine 机械格式校验Q4（`POST /api/test-gates/case-format`） → test-executor 执行回归 → test-lead Q5语义抽审 + backend/engine 机械证据链Q5-Q6（`POST /api/test-gates/evidence-chain`）

**步骤4** test-lead 验收审计结果：
- 通过 → 汇报项目经理，Bug关闭
- 不通过 → 汇报项目经理，重新指派 → 回步骤3循环

超过2轮未关闭 → 项目经理要求提供根因分析报告。

---

