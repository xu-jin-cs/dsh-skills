# 文档重组契约（Document Reassembly Contract）v1.0 — 2026-08-24

> 地位：**可选消费契约（opt-in）**。不属于引擎默认写入链（pipeline.yaml default_chain 不含本逻辑），
> 谁需要"按句找文、拼回整文件"的能力，谁按本契约实现/接入，即获得跨消费方互操作性。
> 纯只读契约：禁止任何写库/改索引动作；零物化存储（on-the-fly 计算，无双份数据、无写放大）。

## 0. 前置不变量（引擎写路径保证，非本契约职责）

由 chunking.yaml `meta_assembly_anchor` 节 + general_stages.py 落锚，CI 机械断言三条：
1. 单文件入库的所有 chunk，`meta.parent_chunk_id` 存在（int64）；
2. 同文件所有 chunk 的 parent_chunk_id 同值；
3. parent_chunk_id == chunk_seq=1 的 chunk 的 chunk_id（首 chunk 锚）。

## 1. 输入

`anchor`：以下任一 —
- 一个命中 chunk 行（从中提取 `meta.parent_chunk_id`）；
- 直接的 parent_chunk_id（int64）。

## 2. 处理流程（R1~R5，顺序固定）

| 步 | 名称 | 规则 |
|---|---|---|
| R1 | 取锚 | 提取 parent_chunk_id；缺失 → 返回 error=NO_ANCHOR，不猜测不兜底 |
| R2 | 捞取 | 两段式：先按锚取首 chunk 行得 `doc_unique_id` → 按 doc_unique_id 捞全量 chunk → 逐行校验 meta.parent_chunk_id==anchor，异值行剔除并记 `orphan_seqs` |
| R3 | 连续性校验 | chunk_seq 必须构成 1..N 连续序列；缺号记入 `gaps`（缺号清单），**禁止静默跳号拼接** |
| R4 | 排序 | **严格升序排列（strictly ascending order）**：以 chunk_seq 为排序键，从小到大 1→N 严格升序；禁止降序/乱序/按字符串序。chunk_id 递增序仅作兜底校验（与 chunk_seq 升序不一致记 warning 不阻断） |
| R5 | 拼接 | 相邻 chunk 按 chunking.yaml `overlap_token`（默认 200）去除重叠段后按 R4 升序结果依次拼接；overlap 去重失败（找不到重叠边界）降级为直接拼接并记 `overlap_fallback: true` |

## 3. 输出结构（消费方统一契约）

```json
{
  "parent_chunk_id": 8101234567,
  "doc_unique_id": "GD000123",
  "chunk_count": 12,
  "full_text": "<拼接后全文>",
  "complete": true,
  "gaps": [],
  "orphan_seqs": [],
  "overlap_fallback": false
}
```

- `complete=false` 当且仅当 gaps 非空；此时 full_text 仍返回已拼部分，消费方自行裁定可用性。

## 4. 接入方式（两档，消费方自选）

- **方式 A｜外部逻辑**：检索服务/应用层按 §2 自行实现，遵守 §3 输出结构；
- **方式 B｜引擎侧可插拔模块**：独立模块（建议位 `retrieval/reassembly.py` 或等价位置），
  显式调用触发，**不挂入 general 族 default_chain**、不改 kernel.py 契约、不新增写路径。

## 5. 接入方验收测试（机械可判，实现后自测）

1. 单文件 3 chunk 入库 → 以第 2 chunk 为 anchor → 返回 chunk_count=3、complete=true、full_text 与原文一致；
2. 人为删除中间 chunk → gaps=[2]、complete=false、full_text 为两段拼接；
3. 无锚 chunk（meta 缺 parent_chunk_id）→ error=NO_ANCHOR；
4. 篡改某 chunk 的 parent_chunk_id → 该行入 orphan_seqs 且不参与拼接。
