# ETLEngine 契约文档（存档重建版）

> ⚠️ 重建说明（2026-08-17 T2 单元）：本文件原是指向 `~/Desktop/ETLEngine契约文档.md` 的
> 符号链接，桌面原件已被移走（与 docs/改造清单v2.md 同源事件），链接断裂、原文不可恢复。
> 现按「落地实现 + docs/改造清单v2.md + docs/规则迁移台账.md」重建为实体文件存档。
> 第一节为既有契约要点重建（非原文逐字），第二、三节为 T2 新增内容。
> 规则唯一真源仍是 engine/contract_rules/*.yaml（逐条带台账编号溯源注释），本文件为叙述性契约。

## 一、既有契约要点（重建）

- **内核统一入口**：一切平台数据写入走 `engine.kernel.etl_engine(payload)`；
  固定时序 contract_validate → resource_control(LanceDB 探活) → 步骤链执行 → outbox 记账 → delivery；
  出参 code 四态：success / reject / block / error。
- **op 七枚举**：write / delete / reconcile / batch（历史族）
  + general_ingest / general_delete / general_reconcile（general 族）。
- **options 白名单**：仅 `list_overridable()` 键可覆盖
  （size_tiers / md5_dedup.enabled / retry_policy.* / chunking.max_token / tmp_retention /
  rebuild_bm25 / legacy_sql）。
- **steps 声明链**：write/delete 可携带 steps，内核按 stages.STAGE_REGISTRY 查表顺序执行；
  缺省走固定链 WRITE_CHAIN=(write_lance, bm25) / DELETE_CHAIN=(delete_lance, legacy_sql, bm25)。
- **幂等**：chunk_id 为稳定内容哈希（`etl-engine|{skill_id}|{seq}|{text}` MD5 前 8 字节），
  LanceDB merge_insert 同 ID 覆写，重试不膨胀；write 后置校验 chunk 存在。
- **outbox 状态机**：pending → ready / failed / deleted；reconcile 三方对账
  （registry 活跃集 ↔ LanceDB ↔ outbox），差集三键：
  missing_in_lance / orphan_lance_docs / outbox_not_ready。
- **规则抽离铁律**：规则唯一真源 engine/contract_rules/（8 表）；
  执行器代码禁写默认值与字面量，缺键即 RuleMissingError；
  契约-代码一致性由 test_rules_consistency.py 强制。
- **历史族既有资产**：旧向量库 / 旧 outbox / 旧 BM25 索引。

## 一·A、内核依赖注入契约（2026 新增）

内核不负责“如何构造 db / store”，只负责“使用满足契约的实例”。

```python
from engine.deps import Deps
from engine.kernel import etl_engine

# 传入现成实例
etl_engine(payload, deps=Deps(db=my_db, store=my_store))

# 传入工厂
etl_engine(payload, deps=Deps(db_factory=my_db_factory, store_factory=my_store_factory))
```

- `Deps.db` / `Deps.store`：优先使用已构造实例；
- `Deps.db_factory` / `Deps.store_factory`：无参工厂，由内核按需调用；
- `Deps.stages`：自定义 stage 注册表 `{step_name: Stage}`，Stage 协议见 `engine/contract.py`；
- `Deps.doc_id_factory`：自定义文档 ID 生成函数；
- `Deps.exception_classifier`：自定义异常分类函数；
- 不传 `deps`：回退 `general_stages` 默认实现，保持默认行为。
- DB / Store / Stage 只需满足 `engine/deps.py` / `engine/contract.py` 中的协议，不需要继承默认类。

## 二、导入恢复（2026-08-17 T2 新增）

### 2.1 原则：源文件=真源，平台=派生态

- 技能源文件（`skills/<skill_id>/SKILL.md` + `provenance.json`）是**真源，只管追加**；
  禁止手工编辑/删除源文件来"修"平台状态。
- 平台数据（LanceDB 向量、outbox 账、BM25 索引）是**派生态**，丢失/损坏后
  可从源文件完整重建，不构成数据事故。
- 派生态的一切写入统一走 `engine.kernel.etl_engine` 契约入口，
  **禁止手工改索引/向量库/outbox**。

### 2.2 标准工具：scripts/import_from_source.py

```bash
cd <repo-root>
PYTHONPATH=. python3 scripts/import_from_source.py [--all | --skill-id <id>] [--dry-run]
```

- 扫 `skills/` 全部源文件（或 `--skill-id` 指定单个）→ 读 provenance.json
  （role/keywords/project）与 SKILL.md → 调 `etl_engine` write 重建向量
  （幂等覆写，`options.rebuild_bm25=False`，批量收尾统一重建一次）
  → outbox 补账（已有 ready 账跳过）→ 末尾 reconcile 校验。
- 默认**增量**：已在向量库且账目齐备的技能跳过；`--all` 强制全量覆写重建。
- `--dry-run` 只打印导入计划与当前对账差集，不做任何写入。
- 分工：历史脚本 `scripts/repair_legacy_state.py` 保留不动（一次性修复原型），
  日常恢复/重建一律用 import_from_source.py。

### 2.3 恢复验收标准

导入完成后 reconcile 三类差集必须清零，工具末尾自动打印并作为退出判据：

- `missing_in_lance` = 0（活跃技能全部有向量）
- `orphan_lance_docs` = 0（无非活跃残留向量）
- `outbox_not_ready` = 0（无 pending/failed 挂账）

任一非零 → 退出码 1 并打印差集明细，修复后重跑（幂等可重入）。

## 三、晋升流程入口（2026-08-17 T2 新增）

### 3.1 领域→专项晋升的标准路径（唯一合法通道）

技能合并/删除（含领域技能吸收专项技能、经验晋升改写）**只走此流程**：

1. **dispatcher_generate 双轨定级**（scripts/dispatcher_generate.py L405-428）：
   `_detect_generality(content)` 机械判定 targeted/general →
   `skill_level` 双轨定级 domain/specialty（命中针对性标记强制 specialty，
   经验条目可显式 `triggers.level` 覆盖）。
2. **supersedes 归档链**：经验条目声明 `supersedes: [old_skill_id]`，
   新技能替换/吸收旧技能；registry 侧 `archive_skill()` 置 archived +
   `superseded_by` 指向新技能，形成可追溯归档链。
3. **引擎 batch op 晋升合并事务**：`etl_engine({"op": "batch", ...})`
   在**同一事务边界内删旧增新**（artifact.writes + artifact.deletes），
   逐项幂等记账，失败项落 outbox=failed 可重试自愈。
4. **BM25 单次重建**：batch 收尾统一重建一次，禁止逐条触发。
5. **熔断先行**：inject_fuse.py 判 A 后才执行引擎事务；判 B 回滚 registry
   并隔离本次生成的源文件，防止"有源文件无索引无向量"孤儿。

### 3.2 禁令

- **禁止手工改索引**（索引注册文件/角色关联文件的增删改
  只由 dispatcher_generate 流程产出）；
- **禁止手工删文件**（skills/ 源文件、向量行、outbox 账）；
- 违反上述禁令造成的派生态不一致，统一用 `import_from_source.py`
  从真源重建恢复，不得在派生态上打补丁。
