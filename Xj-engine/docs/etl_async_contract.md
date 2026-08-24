# 契约冻结 — ETL 异步化三路并行基线（2026-08-17，冻结后三路并行，禁止漂移）

## 1. RabbitMQ 拓扑（参数全量采纳用户细则）
- 连接：host=127.0.0.1 port=5672 vhost=/etl（账号/密码通过环境变量注入，不写入文档）
- 交换机：`etl_exchange`（direct，durable）
- 主队列：`etl_vector_index_task`（durable，消息 DeliveryMode=2 持久，x-message-ttl=90000，死信绑定 DLX）
- 死信：`etl_dlx`（direct，durable）→ `etl_vector_index_dlq`（durable，无 TTL，卡死样本永久保留）
- routing_key：`vector.index.task`
- 消费侧：prefetch_count=4（Qos），consumer 并发 6 起步（进程内线程池）
- 水位限流：主队列消息数 ≥ 20 → complete 接口返回 503 "排队任务过多，请稍后"

## 2. MQ 消息体（文档级，JSON）
```json
{
  "task_id": "upload_tasks 主键",
  "channel": "kb | general | pdf",
  "file_path": "组装后落盘绝对路径",
  "file_name": "原始文件名",
  "tenant_id": "default",
  "enqueued_ts": 175548xxxx
}
```

## 3. 发布端 API（middleware/etl_mq.py，新增）
- `publish_index_task(task_id: str, channel: str, file_path: str, file_name: str, tenant_id: str) -> None`（异常抛出让调用方置 failed）
- `queue_depth() -> int`（主队列消息数，查不到返回 -1）
- `WATERMARK = 20`
- 模块内惰性连接 + 线程锁，声明幂等（每次连接 declare 一遍拓扑）

## 4. Consumer（参考实现，已从 standalone 包移除，需按业务后端重新实现）
- 消费主队列 → Redis 幂等判断 `etl:index:done:{task_id}`（SET NX EX 7天）→ 已存在直接 ACK
- 执行：从你的后端数据库会话按 task_id 取任务记录，置 etl_running，调用
  你的后端分发逻辑处理 file_path（三通道），成功置 completed + 写 Redis done + ACK
- 失败：置 failed + error，`basic_nack(requeue=False)` → 进 DLQ；卡死超 90s TTL 自动进 DLQ
- 启动：参考实现原为 `scripts/etl_index_consumer.py`；standalone 包已移除该文件，接入时按你的后端项目路径设置 PYTHONPATH

## 5. upload_dispatch.py 改造点（线3）
- complete_upload：组装+校验（PDF页数）后 → 查 queue_depth()≥WATERMARK 则 503 →
  task.status="queued" + commit → publish_index_task(...) → 立即返回 _task_to_status(task)
- 投递失败：status=failed + error，抛 500
- _dispatch_kb/_dispatch_general/_dispatch_pdf 保持原签名不动（consumer 复用）

## 6. 引擎侧改造点（线1，engine/general_stages.py）
- general_write：埋点计时 embed 耗时 / lance 写耗时 / 总耗时，logger.info 输出（格式 `[ETL-PROF] doc=<id> embed=<ms> lance=<ms> chunks=<n>`）
- general_post：BM25 重建节流——模块级 threading.Lock 串行化 + 节流（距上次重建 <60s 且期间新增文档 <10 篇 → 跳过，记 logger），埋点 bm25 耗时
- general_write 内 LanceDB store.write_overwrite + db.write_chunks + outbox_record 段加模块级写锁串行化
- 禁止改动：kernel.py 契约、stages.py、outbox.py、三段对账/reconcile、embed.py 模型契约

## 7. 前端（线3附带，UploadDocumentDrawer.tsx）
- pollTask 状态映射补 "queued" → 显示"排队中"（视同 processing，progress 90）

## 8. 部署（收口，主会话做）
- start.sh 拉 consumer（nohup + 日志 /tmp/etl-index-consumer.log），stop.sh 停
- CLAUDE.md 更新引擎边界记录（解禁留痕：2026-08-17 用户裁决）

---

# 第二轮修订（2026-08-17，REFORM-GATE 判 A：~/.agents/logs/reform_gate_block_minio_mq_bound_20260817.md）

## R1. 主队列有界化（etl_mq.py 改）
- 删除并重建主队列（当前为空，安全；DLQ 27 条样本保留不动）：`etl_vector_index_task` 增加 arguments `x-max-length=20`、`x-overflow=reject-publish`，TTL 由 90000 改为 **1800000**（文档级任务实测 embed 90s，90s TTL 会静默丢任务）
- publish 开 publisher confirms（`channel.confirm_delivery()`），队列满被拒 → publish_index_task 抛异常 → upload 返回 503（与应用层 WATERMARK=20 双保险）
- 拓扑声明逻辑兼容已存在队列：启动时尝试 passive declare，参数不一致则 delete 后重建（仅主队列；DLQ 永不重建）

## R2. MinIO 前置落盘（upload_dispatch.py 改 + consumer 改）
- 复用 `etl/common/minio_ops.py`（upload_bytes/download_bytes 现成，自动建桶）
- complete_upload：组装校验后 → `upload_bytes("etl-raw", f"{task.id}/{task.file_name}", assembled_path.read_bytes())` → 成功才算用户提交完成 → 投递 MQ（消息体加 `minio_key` 字段）→ 返回 queued
- MinIO 写失败 → task failed + 500（不落盘不投递，宁可明确失败）
- consumer：file_path 本地存在则直接用；不存在 → `download_bytes("etl-raw", minio_key)` 落到 upload_tmp 再处理；处理完清理临时副本（原始对象保留在 MinIO 作对账基准源，禁删）
- 消息体 v2：§2 六字段 + `minio_key`（第七字段，可缺省兼容旧消息）

## R3. 引擎侧（general_stages.py 改，解禁范围内）
- embed 串行化：模块级 `_EMBED_LOCK`，`embed.compute_embeddings(...)` 调用整段包裹（消灭 6 线程 GPU 争抢 90s 长尾）
- ETL-PROF 埋点加 `lock_wait` 字段：`_WRITE_LOCK` 获取等待时长（`t0=time.monotonic(); with _WRITE_LOCK:` 前后差值）

## R4. consumer 加固（etl_index_consumer.py 改）
- watchdog：处理中的任务每 30s 打一条 `WATCHDOG task=<id> elapsed=<s>s` 日志（卡死可观测）
- DLQ 监听：启动时打印 DLQ 当前深度，每 60s 复查，>0 打 WARN

---

# 第三轮修订（2026-08-17，REFORM-GATE 判 A：~/.agents/logs/reform_gate_block_minio_first_no_reject_20260817.md）
# 用户裁决：先改造机制——MinIO 全量兜底、入口零拒载、MQ 无界持久缓冲、告警代替报错、巡检兜底代替补偿表

## R5. 入口零拒载 + MQ 无界化（etl_mq.py + upload_dispatch.py）
- etl_mq.py：主队列重建移除 `x-max-length`/`x-overflow`（当前队列空，安全；DLQ 永不动）；TTL **维持 1800000**（90s 为 chunk 级假设，本地文档级实测否决）；confirms 保留（防 Unroutable）
- etl_mq.py：publish 成功后写 Redis 标记 `SET etl:mq:sent:{task_id} 1 EX 86400`（巡检对账用）
- upload_dispatch.py complete_upload：**删除** WATERMARK 预检 503 块与"队列已满→503"分支；publish 失败 → 仅 logger.warning，task 维持 queued，正常返回成功（巡检补发兜底）；MinIO 落盘失败仍是唯一 500 拦截点

## R6. 巡检兜底（参考实现，standalone 包已移除 scripts/etl_minio_reconciler.py）
- 逻辑：list MinIO `etl-raw` 全部对象 → 解析 key 中 task_id → 跳过 Redis 有 `etl:mq:sent:{task_id}` 的 → 查你的任务模型：status 为 canceled/completed/failed(非投递失败) 跳过；其余（queued 但无 sent 标记 = 发布失败漏发）→ 补发 publish_index_task（file_path 可为空串，consumer 走 minio_key 回读）
- 运行形态：单次执行+循环（`RECONCILE_INTERVAL=300s`），由 start.sh 守护拉起，日志 /tmp/etl-minio-reconciler.log
- 幂等安全：重复补发由 consumer 侧 `etl:index:done` 幂等键兜住

## R7. 告警规则（新增 middleware/prometheus_rules/etl_engine.yaml）
- 三件套照搬用户细则：积压>20 持续 30s warning / 5m 新增积压>10 持续 60s critical / DLQ 1m 新增>0 critical
- 只落配置文件 + README 注明挂载方式，不动 Prometheus 运行配置

