"""ETL 异步化 RabbitMQ 发布端基建（契约冻结：docs/etl_async_contract_20260817.md）。

拓扑（§1 + R5 第三轮修订，声明幂等，每次连接 declare 一遍）：
- exchange `etl_exchange`（direct, durable），routing_key `vector.index.task`
- 主队列 `etl_vector_index_task`（durable，x-message-ttl=1800000，
  死信进 DLX）——R5：MQ 无界化，移除 x-max-length/x-overflow（R1 有界化废止）
- 死信 `etl_dlx`（direct, durable）→ `etl_vector_index_dlq`（durable），
  routing_key `vector.index.dlq`，卡死样本永久保留（DLQ 永不删除重建）

参数兼容逻辑（RabbitMQ 不允许改已存在队列的参数；实测 passive declare 不做
arguments 等价校验，故参数一致性用带目标参数的正式 declare 探测）：每次连接先
passive declare 探测主队列存在性——404 不存在 → 按新参数直接建；存在则再以
目标参数 declare 探测等价性——成功即参数一致；406 PRECONDITION_FAILED
（x-max-length / x-overflow 残留等不符）→ queue_delete 主队列后按新参数重建
（仅限主队列；DLQ 永不删除重建），随后重新 bind。R5 首轮连接即借该机制
自动完成无界化重建（当前主队列空，安全）。

发布端 API（§3 + R5）：
- publish_index_task(...)：模块级惰性连接 + threading.Lock，断线自动重连一次重试；
  publisher confirms（channel.confirm_delivery()）保留——R5 防 Unroutable；
  发布成功后写 Redis 标记 etl:mq:sent:{task_id}（EX 86400，巡检对账用，
  标记失败仅 warning 不阻断主流程）
- queue_depth()：passive declare 主队列取 method.message_count，查不到返回 -1
- WATERMARK = 20：已废止于 R5（入口零拒载，upload 侧不再使用），保留供监控参考
"""

import json
import logging
import os
import threading
import time

import pika

logger = logging.getLogger("etl_mq")

# ── 契约 §1 连接参数 ────────────────────────────────────────────────
# 2026-08-17 FIX-etl-mq-password：口令外置环境变量（security_baseline 闸实证拦截后修复），
# 与 start.sh/.env 同源；未设置时启动期告警，禁止明文回落（旧值见 .bak.20260817 备份考古）
MQ_HOST = os.environ.get("RABBITMQ_HOST", "127.0.0.1")
MQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
MQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/etl")
MQ_USER = os.environ.get("RABBITMQ_USER", "")
MQ_PASSWORD = os.environ.get("RABBITMQ_PASS", "")
if not MQ_USER or not MQ_PASSWORD:
    logging.getLogger(__name__).warning(
        "RABBITMQ_USER/RABBITMQ_PASS 未设置——ETL MQ 发布端将无法连接；请在 .env 或环境变量中配置")
HEARTBEAT = 60
BLOCKED_CONNECTION_TIMEOUT = 30

# ── 契约 §1 拓扑常量 ────────────────────────────────────────────────
EXCHANGE = "etl_exchange"
DLX = "etl_dlx"
MAIN_QUEUE = "etl_vector_index_task"
DLQ = "etl_vector_index_dlq"
ROUTING_KEY_TASK = "vector.index.task"
ROUTING_KEY_DLQ = "vector.index.dlq"
# R1：TTL 90000→1800000（30 分钟；90s 为 chunk 级假设，文档级实测否决）
MESSAGE_TTL_MS = 1800000
# R5：主队列无界化——R1 的 MAX_LENGTH/OVERFLOW（reject-publish）已废止移除

# ── 契约 §3 水位限流阈值 ────────────────────────────────────────────
# 已废止于 R5（入口零拒载，upload 侧不再使用），保留供监控参考
WATERMARK = 20

# ── R5 Redis 巡检对账标记（惰性单例）──────────────────────────────
REDIS_SENT_KEY_PREFIX = "etl:mq:sent:"
REDIS_SENT_TTL_S = 86400
_redis_client = None

# 模块级惰性连接（单连接多复用；pika 非线程安全，发布侧用锁串行化）
_conn_lock = threading.Lock()
_connection = None


def _conn_params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=MQ_HOST,
        port=MQ_PORT,
        virtual_host=MQ_VHOST,
        credentials=pika.PlainCredentials(MQ_USER, MQ_PASSWORD),
        heartbeat=HEARTBEAT,
        blocked_connection_timeout=BLOCKED_CONNECTION_TIMEOUT,
    )


def _main_queue_arguments() -> dict:
    """主队列目标参数（R5 冻结：TTL + DLX/DLQ-key，无 max-length/overflow）。"""
    return {
        "x-message-ttl": MESSAGE_TTL_MS,
        "x-dead-letter-exchange": DLX,
        "x-dead-letter-routing-key": ROUTING_KEY_DLQ,
    }


def _get_redis():
    """Redis 惰性单例（R5 巡检对账标记；不可用时返回 None，不阻断主流程）。"""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.Redis(host="127.0.0.1", port=6379, db=0)
        except Exception as exc:
            logger.warning("Redis 客户端初始化失败，跳过投递标记: %s", exc)
    return _redis_client


def _mark_sent(task_id: str) -> None:
    """publish 成功后写 Redis 标记 SET etl:mq:sent:{task_id} 1 EX 86400。

    R5 巡检（参考实现，standalone 包已移除 reconciler）对账依据；标记失败仅 warning。
    """
    try:
        client = _get_redis()
        if client is not None:
            client.set(f"{REDIS_SENT_KEY_PREFIX}{task_id}", 1, ex=REDIS_SENT_TTL_S)
    except Exception as exc:
        logger.warning("任务 %s Redis 投递标记写入失败（不阻断主流程）: %s", task_id, exc)


def _declare(conn: pika.BlockingConnection) -> None:
    """声明契约 §1+R5 全部拓扑（每次新建连接都跑一遍）。

    交换机 / DLQ 幂等 declare（DLQ 永不删除重建——卡死样本永久保留）。
    主队列：先 passive declare 探测存在性——
      - 404 NOT_FOUND：队列不存在，按新参数直接建；
      - 存在：再以 R5 目标参数正式 declare 探测等价性（passive declare 实测不做
        arguments 等价校验，必须用此路径）；406 PRECONDITION_FAILED 即参数不符
        （RabbitMQ 不允许原地改参数）→ queue_delete 后按新参数重建（仅限主队列）。
    最后统一重新 bind（幂等；删除重建后必须补绑）。
    """
    with conn.channel() as ch:
        ch.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
        ch.exchange_declare(exchange=DLX, exchange_type="direct", durable=True)

        ch.queue_declare(queue=DLQ, durable=True)
        ch.queue_bind(queue=DLQ, exchange=DLX, routing_key=ROUTING_KEY_DLQ)

    # ── 第一步：passive declare 探测主队列存在性（404 走新建）────────
    probe = conn.channel()
    try:
        probe.queue_declare(queue=MAIN_QUEUE, passive=True, durable=True)
        exists = True
    except pika.exceptions.ChannelClosedByBroker as exc:
        if exc.reply_code == 404:
            exists = False
        else:
            raise
    finally:
        if probe.is_open:
            probe.close()

    # ── 第二步：等价性探测——带 R5 目标参数 declare，406 即参数不符 ────
    need_create = not exists
    delete_first = False
    if exists:
        probe2 = conn.channel()
        try:
            probe2.queue_declare(
                queue=MAIN_QUEUE,
                durable=True,
                arguments=_main_queue_arguments(),
            )
            # 成功：参数一致，幂等通过
        except pika.exceptions.ChannelClosedByBroker as exc:
            if exc.reply_code == 406:
                need_create = True
                delete_first = True
                logger.warning(
                    "主队列已存在但参数不符（R5 目标参数 %s），"
                    "删除重建（DLQ 不动）: %s",
                    _main_queue_arguments(), exc.reply_text,
                )
            elif exc.reply_code == 404:
                need_create = True  # 并发窗口内被删，按新建处理
            else:
                raise
        finally:
            if probe2.is_open:
                probe2.close()

    if need_create:
        with conn.channel() as ch:
            if delete_first:
                ch.queue_delete(queue=MAIN_QUEUE)
            ch.queue_declare(
                queue=MAIN_QUEUE,
                durable=True,
                arguments=_main_queue_arguments(),
            )
        logger.warning("主队列已按 R5 参数（重）建 arguments=%s", _main_queue_arguments())

    # 重新 bind（幂等；删除重建后必须补绑）
    with conn.channel() as ch:
        ch.queue_bind(queue=MAIN_QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY_TASK)


def _get_connection() -> pika.BlockingConnection:
    """惰性连接：断线或不存在时重建（调用方须持 _conn_lock）。"""
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = pika.BlockingConnection(_conn_params())
        _declare(_connection)
        logger.info("etl_mq 连接已建立，拓扑声明完成 vhost=%s", MQ_VHOST)
    return _connection


def _reset_connection() -> None:
    global _connection
    try:
        if _connection is not None and _connection.is_open:
            _connection.close()
    except Exception:
        pass
    _connection = None


def publish_index_task(
    task_id: str,
    channel: str,
    file_path: str,
    file_name: str,
    tenant_id: str,
    minio_key: str = "",
) -> None:
    """发布向量索引任务（契约 §2 消息体，delivery_mode=2 持久）。

    R5：publisher confirms（confirm_delivery）保留，防 Unroutable（路由失败 →
    UnroutableError → 抛 RuntimeError）。pika 1.3.2 basic_publish 恒返回 None，
    确认语义全走异常。主队列已无界化（无 max-length/overflow），正常无 NACK。

    发布成功后写 Redis 标记 etl:mq:sent:{task_id}（EX 86400，巡检对账用；
    标记失败仅 warning，不阻断主流程）。

    断线自动重连一次并重试一次；仍失败则异常抛出，由调用方处理
    （R5：调用方仅 warning，task 维持 queued，巡检补发兜底）。
    """
    body = json.dumps(
        {
            "task_id": task_id,
            "channel": channel,
            "file_path": file_path,
            "file_name": file_name,
            "tenant_id": tenant_id,
            "minio_key": minio_key,
            "enqueued_ts": int(time.time()),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    props = pika.BasicProperties(
        delivery_mode=2,
        content_type="application/json",
    )

    last_exc = None
    with _conn_lock:
        for attempt in range(2):  # 首次 + 断线重连后重试一次
            try:
                conn = _get_connection()
                ch = conn.channel()
                try:
                    ch.confirm_delivery()
                    # confirm 模式下：ACK 正常返回（恒 None）；路由失败抛
                    # UnroutableError（R5 保留 confirms 的防 Unroutable 用途）
                    ch.basic_publish(
                        exchange=EXCHANGE,
                        routing_key=ROUTING_KEY_TASK,
                        body=body,
                        properties=props,
                    )
                finally:
                    if ch.is_open:
                        ch.close()
                _mark_sent(task_id)  # R5：巡检对账 Redis 标记（失败仅 warning）
                logger.info(
                    "已发布索引任务 task_id=%s channel=%s file=%s",
                    task_id, channel, file_name,
                )
                return
            except (pika.exceptions.NackError, pika.exceptions.UnroutableError) as exc:
                # broker 明确拒绝（路由失败等）：不重连重试，直接抛出由调用方处理
                raise RuntimeError(f"投递被拒/未确认 task_id={task_id}: {exc}")
            except (pika.exceptions.AMQPError, OSError) as exc:
                last_exc = exc
                logger.warning("发布失败(attempt=%d)，重建连接重试: %s", attempt, exc)
                _reset_connection()
    raise RuntimeError(f"publish_index_task 失败 task_id={task_id}: {last_exc}")


def queue_depth() -> int:
    """主队列当前消息数（passive declare 取 method.message_count）。

    DEPRECATED（ENG-038，2026-08-20 审计）：R5 废止水位限流后全库零调用方，
    保留仅供将来监控接入；接入前任何新代码禁止调用（死代码防误食）。
    任何异常（连接失败等）返回 -1，调用方按"查不到"语义处理。
    """
    try:
        with _conn_lock:
            conn = _get_connection()
            with conn.channel() as ch:
                method = ch.queue_declare(queue=MAIN_QUEUE, passive=True)
                return method.method.message_count
    except Exception as exc:
        logger.warning("queue_depth 查询失败，返回 -1: %s", exc)
        _reset_connection()
        return -1
