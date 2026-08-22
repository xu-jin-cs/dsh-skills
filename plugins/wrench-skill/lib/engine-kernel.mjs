/**
 * engine-kernel.mjs — agent 引擎机制内核（签发/状态同步）Node.js ESM 移植版
 *
 * 真源（Python，逐语义对齐）：
 *   agent-harness/backend/engine/kernel.py        et() 六段时序统一入口
 *   agent-harness/backend/engine/et_contract.py   payload/输出契约校验
 *   agent-harness/backend/engine/et_sign.py       canonical JSON + sha256/hmac-sha256 签发验签
 *   agent-harness/backend/engine/state_store.py   实例状态存取（移植版：本地 JSON 文件）
 *   agent-harness/backend/engine/state_wiring.py  状态收口双写
 *   agent-harness/backend/engine/audit.py         审计事件（移植版：本地 jsonl）
 *   agent-harness/scripts/harness-step-sync.sh    状态同步脚本（移植版：无 HTTP，直调内核）
 *
 * 定性：本模块是「签发内容、同步状态」的纯机制内核 et()，不写业务数据、
 * 不依赖 MySQL/Redis/FastAPI。所有业务规则（ACL/跃迁/配额/校验）全部由
 * 调用方以 JS 对象注入 payload，本模块不内置任何业务规则、不解析 yaml。
 *
 * 零第三方依赖，仅 node: 内置模块。
 *
 * 出参 code 五态（与 Python 版一致）：
 *   success / reject / block / timeout / error
 *
 * 状态持久化目录：~/.dsh/xujin-engine/state/（JSON 文件，可用 options.stateDir 覆盖）
 * 审计事件：      ~/.dsh/xujin-engine/audit.jsonl（options.auditFile 覆盖）
 * 步骤日志：      ~/.dsh/xujin-engine/steps.jsonl（options.stepsFile 覆盖）
 * 目录不存在时自动创建；审计/日志写失败只告警，不炸主流程。
 */

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// ═══════════════════════════════════════════════════════════════
// 默认落盘位置
// ═══════════════════════════════════════════════════════════════

export const ENGINE_HOME = path.join(os.homedir(), ".dsh", "xujin-engine");
export const DEFAULT_STATE_DIR = path.join(ENGINE_HOME, "state");
export const DEFAULT_AUDIT_FILE = path.join(ENGINE_HOME, "audit.jsonl");
export const DEFAULT_STEPS_FILE = path.join(ENGINE_HOME, "steps.jsonl");

function _ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function _warn(msg) {
  // 旁路（审计/日志/双写）失败只告警，绝不阻断裁决主流程
  try { process.stderr.write(`[engine-kernel] WARNING ${msg}\n`); } catch { /* ignore */ }
}

// ═══════════════════════════════════════════════════════════════
// et_sign.py 移植 — 签发验签
// ═══════════════════════════════════════════════════════════════

export const SECRET_ENV_KEY = "AGENT_ENGINE_SECRET";

export class SecretMissingError extends Error {
  constructor(message) {
    super(message);
    this.name = "SecretMissingError";
  }
}

/** 解析内核默认密钥：仅读 env AGENT_ENGINE_SECRET，缺省即抛 SecretMissingError。 */
export function defaultSecret() {
  const env = process.env[SECRET_ENV_KEY];
  if (!env) {
    throw new SecretMissingError(
      `缺少环境变量 ${SECRET_ENV_KEY}：hmac-sha256 签发必须显式注入密钥` +
      "（生产由 check_engine_secret.sh 预检强制；本地开发请自行 export）。"
    );
  }
  return Buffer.from(env, "utf-8");
}

/** Python 字符串排序按 Unicode 码点；JS 默认按 UTF-16 码元，此处对齐码点序。 */
function _codePointCompare(a, b) {
  const ca = Array.from(a);
  const cb = Array.from(b);
  const n = Math.min(ca.length, cb.length);
  for (let i = 0; i < n; i++) {
    const pa = ca[i].codePointAt(0);
    const pb = cb[i].codePointAt(0);
    if (pa !== pb) return pa - pb;
  }
  return ca.length - cb.length;
}

/**
 * canonical JSON：与 Python
 *   json.dumps(obj, separators=(",", ":"), sort_keys=True,
 *              ensure_ascii=False, default=str)
 * 逐字节对齐。键按码点排序、紧凑分隔符、非 ASCII 不转义（JS JSON.stringify 默认行为）。
 * 已知残余偏差（报告中有述）：JS 无法区分 int 1 与 float 1.0（Python 后者输出 "1.0"）；
 * 非有限浮点按 Python 风格输出 Infinity/-Infinity/NaN。
 */
export function canonicalStringify(value) {
  if (value === null || value === undefined) return "null";
  const t = typeof value;
  if (t === "boolean") return value ? "true" : "false";
  if (t === "number") {
    if (Number.isNaN(value)) return "NaN";
    if (!Number.isFinite(value)) return value > 0 ? "Infinity" : "-Infinity";
    return String(value);
  }
  if (t === "string") return JSON.stringify(value); // 不转义非 ASCII，与 ensure_ascii=False 一致
  if (t === "bigint") return String(value);
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalStringify).join(",") + "]";
  }
  if (t === "object") {
    const keys = Object.keys(value).sort(_codePointCompare);
    const parts = keys.map(
      (k) => JSON.stringify(k) + ":" + canonicalStringify(value[k])
    );
    return "{" + parts.join(",") + "}";
  }
  // default=str 语义：其余不可序列化类型转字符串后按字符串处理
  return canonicalStringify(String(value));
}

/** 签名原文：canonical({trace_id, artifact, state_meta})。 */
export function canonicalSignSource(traceId, artifact, stateMeta = null) {
  return canonicalStringify({
    trace_id: traceId,
    artifact,
    state_meta: stateMeta || {},
  });
}

/**
 * 按统一规则计算签名。algo ∈ "sha256" / "hmac-sha256"。
 * hmac-sha256 密钥：secret 缺省时走 defaultSecret()（仅读 env，未注入即抛
 * SecretMissingError，经内核异常通道返回 code=error）。
 */
export function computeSignature(
  artifact,
  traceId,
  stateMeta = null,
  algo = "sha256",
  secret = null
) {
  const canonical = canonicalSignSource(traceId, artifact, stateMeta);
  if (algo === "hmac-sha256") {
    let key;
    if (secret) {
      key = typeof secret === "string" ? Buffer.from(secret, "utf-8") : secret;
    } else {
      key = defaultSecret();
    }
    return crypto.createHmac("sha256", key).update(canonical, "utf-8").digest("hex");
  }
  if (algo === "sha256") {
    return crypto.createHash("sha256").update(canonical, "utf-8").digest("hex");
  }
  throw new Error(`不支持的签名算法: ${algo}`);
}

/**
 * 验签：按 content_issue 同一规则重算签名并与 issueMeta["signature"] 比对
 * （对齐 et_sign.verify_issue；恒定时间比对）。
 */
export function verifySignature(
  artifact,
  issueMeta,
  traceId,
  stateMeta = null,
  secret = null
) {
  if (issueMeta === null || typeof issueMeta !== "object" || Array.isArray(issueMeta)) {
    return false;
  }
  const algo = issueMeta.algo || "sha256";
  const signature = issueMeta.signature;
  if (!signature || (algo !== "sha256" && algo !== "hmac-sha256")) return false;
  let expected;
  try {
    expected = computeSignature(artifact, traceId, stateMeta, algo, secret);
  } catch {
    return false; // 含 SecretMissingError：未注入密钥时验签失败返回 false
  }
  const a = Buffer.from(expected, "utf-8");
  const b = Buffer.from(String(signature), "utf-8");
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

/** et_sign.verify_issue 原名别名（对齐 Python 命名）。 */
export const verifyIssue = verifySignature;

// ═══════════════════════════════════════════════════════════════
// et_contract.py 移植 — 契约校验（零依赖迷你 JSON-Schema 子集）
// ═══════════════════════════════════════════════════════════════

export class ContractViolationError extends Error {
  constructor(errors) {
    super("ET Payload 契约校验失败: " + errors.join("; "));
    this.name = "ContractViolationError";
    this.errors = errors;
  }
}

export class OutputContractError extends Error {
  constructor(errors) {
    super("内核出参契约校验失败: " + errors.join("; "));
    this.name = "OutputContractError";
    this.errors = errors;
  }
}

function _typeOf(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  return typeof value; // object/string/boolean/...
}

function _matchType(value, type) {
  const t = _typeOf(value);
  if (type === "number") return t === "number" || t === "integer";
  return t === type;
}

/**
 * 迷你 JSON-Schema 校验器：支持 type/required/properties/additionalProperties(false)/
 * enum/items/minLength/minimum/minItems，覆盖 et_contract 两个 Schema 用到的全部关键字。
 */
function _validateSchema(schema, value, pathSeg, errors) {
  const here = pathSeg || "<root>";
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!types.some((t) => _matchType(value, t))) {
      errors.push(`${here}: 类型不符，期望 ${types.join("|")}，实际 ${_typeOf(value)}`);
      return; // 类型不符不再深入，避免级联噪音
    }
  }
  if (schema.enum !== undefined && !schema.enum.some((e) => e === value)) {
    errors.push(`${here}: 取值 ${JSON.stringify(value)} 不在枚举 ${JSON.stringify(schema.enum)} 内`);
  }
  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${here}: 长度 ${value.length} 小于 minLength ${schema.minLength}`);
    }
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(`${here}: ${value} 小于 minimum ${schema.minimum}`);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(`${here}: ${value} 大于 maximum ${schema.maximum}`);
    }
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${here}: 数组长度 ${value.length} 小于 minItems ${schema.minItems}`);
    }
    if (schema.items) {
      value.forEach((item, i) => _validateSchema(schema.items, item, `${here}[${i}]`, errors));
    }
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const props = schema.properties || {};
    for (const req of schema.required || []) {
      if (!(req in value)) errors.push(`${here}: 缺少必填键 ${req}`);
    }
    if (schema.additionalProperties === false) {
      for (const k of Object.keys(value)) {
        if (!(k in props)) errors.push(`${here}: 存在契约外键 ${k}`);
      }
    }
    for (const [k, sub] of Object.entries(props)) {
      if (k in value) _validateSchema(sub, value[k], pathSeg ? `${pathSeg}.${k}` : k, errors);
    }
  }
}

const _ON_FAIL_ENUM = ["terminate", "rollback", "failed"];

const _VALIDATE_CHECK = {
  type: "object",
  required: ["id", "type"],
  properties: {
    id: { type: "string", minLength: 1 },
    type: {
      enum: [
        "required_fields", "file_exists", "file_min_size", "json_field",
        "regex", "min_ratio",
        "items_regex", "items_unique", "items_required_fields", "items_enum",
        "dir_glob_count", "dir_file_count_eq_json", "dir_file_hash_unique",
        "fields_distinct",
      ],
    },
    fields: { type: "array", items: { type: "string" } },
    text_source: { type: "string" },
    path: { type: "string" },
    min_size: { type: "integer", minimum: 1 },
    pattern: { type: "string" },
    numerator: {}, denominator: {}, min: { type: "number" },
    items_path: { type: "string" },
    field: { type: "string" },
    values: { type: "array", items: { type: "string" } },
    nonempty: { type: "boolean" },
    field_a: { type: "string" },
    field_b: { type: "string" },
    ignore_empty: { type: "boolean" },
    suffix: { type: "string" },
    json_file: { type: "string" },
    json_field: { type: "string" },
    algo: { type: "string" },
    on_fail: { enum: _ON_FAIL_ENUM },
    message: { type: "string" },
  },
  additionalProperties: false,
};

export const PAYLOAD_SCHEMA = {
  type: "object",
  required: ["artifact", "trace_id"],
  properties: {
    trace_id: { type: "string", minLength: 1 },
    parent_trace_id: { type: "string" },
    artifact: { type: ["object", "string"] },
    state_intercept: {
      type: "object",
      properties: {
        allow_transition: { type: "array", items: { type: "string" } },
        allowed_pairs: {
          type: "array",
          items: {
            type: "object",
            required: ["from", "to"],
            properties: { from: { type: "string" }, to: { type: "string" } },
            additionalProperties: false,
          },
        },
        target_state: { type: "string" },
        state_meta: { type: "object" },
        current_state: { type: "string" },
      },
      additionalProperties: false,
    },
    gate_guard: {
      type: "object",
      properties: {
        target_agent_id: { type: "string" },
        acl: { type: "array", items: { type: "string" } },
        rate_limit: { type: "integer" },
        rate_current: { type: "integer" },
        permission_scope: { type: "string" },
        route: { type: "string" },
        route_whitelist: { type: "array", items: { type: "string" } },
      },
      additionalProperties: false,
    },
    content_issue: {
      type: "object",
      properties: {
        sign: { type: "boolean" },
        sign_algo: { enum: ["sha256", "hmac-sha256"] },
        watermark: { type: "boolean" },
        attach_issue_meta: { type: "object" },
        secret: { type: "string" },
      },
      additionalProperties: false,
    },
    artifact_validate: {
      type: "object",
      required: ["checks"],
      properties: {
        checks: { type: "array", items: _VALIDATE_CHECK, minItems: 1 },
      },
      additionalProperties: false,
    },
    resource_control: {
      type: "object",
      properties: {
        token_limit: { type: "integer" },
        global_timeout_ms: { type: "integer" },
        hook_timeout_ms: { type: "integer" },
        priority: { type: "string", enum: ["low", "normal", "high"] },
        max_concurrent: { type: "integer" },
        cost_budget: { type: "number" },
        token_used: { type: "number" },
        concurrent_current: { type: "integer" },
        cost_used: { type: "number" },
        model_allow_list: { type: "array", items: { type: "string" } },
        model: { type: "string" },
      },
      additionalProperties: false,
    },
    failure_policy: {
      type: "object",
      properties: {
        max_retry: { type: "integer" },
        retry_delay_ms: { type: "integer" },
        fallback_target: { type: "string" },
        compensation_action: { enum: ["none", "revoke_issue", "rollback_state"] },
        alert_on_block: { type: "boolean" },
      },
      additionalProperties: false,
    },
    delivery: {
      type: "object",
      properties: {
        mode: { type: "string", enum: ["single", "async", "broadcast"] },
        next_handler: { type: ["string", "array"] },
        require_ack: { type: "boolean" },
        output_transform: {
          type: "object",
          properties: {
            include_fields: { type: "array", items: { type: "string" } },
            exclude_fields: { type: "array", items: { type: "string" } },
            mask_fields: { type: "array", items: { type: "string" } },
          },
          additionalProperties: false,
        },
      },
      additionalProperties: false,
    },
    audit_meta: {
      type: "object",
      properties: {
        tenant_id: { type: "string" },
        principal: { type: "string" },
        sensitivity_level: { enum: ["public", "internal", "sensitive", "confidential"] },
        audit_tags: { type: "array", items: { type: "string" } },
        retention_ttl_sec: { type: "integer" },
      },
      additionalProperties: false,
    },
    traffic_exp: {
      type: "object",
      properties: {
        experiment_id: { type: "string" },
        sample_rate: { type: "number", minimum: 0, maximum: 1 },
        traffic_tag: { type: "string" },
      },
      additionalProperties: false,
    },
    sandbox_policy: {
      type: "object",
      properties: {
        tool_allow_list: { type: "array", items: { type: "string" } },
        network_isolate: { type: "boolean" },
      },
      additionalProperties: false,
    },
    debug: { type: "boolean" },
  },
  additionalProperties: false,
};

/** 内核唯一前置动作：校验入参契约。不通过抛 ContractViolationError。 */
export function validatePayload(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ContractViolationError([`payload 必须是 dict，实际: ${_typeOf(payload)}`]);
  }
  const errors = [];
  _validateSchema(PAYLOAD_SCHEMA, payload, "", errors);
  if (errors.length) throw new ContractViolationError(errors);
  return payload;
}

// ── 出参契约 ──

const _GATE_RESULT_OUT = {
  type: ["object", "null"],
  required: ["pass", "reason"],
  properties: { pass: { type: "boolean" }, reason: { type: "string" } },
};
const _FAILURE_INFO_OUT = {
  type: ["object", "null"],
  required: ["error_msg"],
  properties: {
    error_msg: { type: "string" },
    fallback_target: { type: ["string", "null"] },
    max_retry: { type: "integer" },
    retry_delay_ms: { type: "integer" },
    compensation_action: { enum: ["none", "revoke_issue", "rollback_state"] },
    alert: { type: "boolean" },
  },
};
const _DELIVERY_OUT = {
  type: ["object", "null"],
  required: ["next_handler", "require_ack"],
  properties: {
    next_handler: { type: ["string", "array", "null"] },
    require_ack: { type: "boolean" },
    mode: { enum: ["single", "async", "broadcast"] },
    payload: {},
  },
};
const _RESOURCE_OUT = {
  type: ["object", "null"],
  required: ["pass", "violations"],
  properties: {
    pass: { type: "boolean" },
    violations: { type: "array", items: { type: "string" } },
    priority: { enum: ["low", "normal", "high"] },
  },
};
const _VALIDATE_RESULT_OUT = {
  type: ["object", "null"],
  required: ["pass", "results", "failures"],
  properties: {
    pass: { type: "boolean" },
    results: { type: "array" },
    failures: { type: "array" },
  },
};

export const OUTPUT_SCHEMA = {
  type: "object",
  required: ["code", "trace_id"],
  properties: {
    code: { type: "string", enum: ["success", "block", "reject", "timeout", "error"] },
    trace_id: { type: "string" },
    parent_trace_id: { type: ["string", "null"] },
    new_task_state: { type: ["string", "null"] },
    signed_artifact: { type: ["object", "string", "null"] },
    gate_result: _GATE_RESULT_OUT,
    validate_result: _VALIDATE_RESULT_OUT,
    resource: _RESOURCE_OUT,
    issue_meta: { type: ["object", "null"] },
    delivery: _DELIVERY_OUT,
    failure_info: _FAILURE_INFO_OUT,
    audit_meta: { type: ["object", "null"] },
    _debug: { type: "object" },
  },
  additionalProperties: false,
};

/** 内核返回前自验出参契约。不符合说明内核实现有 bug，抛 OutputContractError。 */
export function validateOutput(output) {
  const errors = [];
  _validateSchema(OUTPUT_SCHEMA, output, "", errors);
  if (errors.length) throw new OutputContractError(errors);
  return output;
}

// ═══════════════════════════════════════════════════════════════
// audit.py 移植 — 审计事件（本地 jsonl，写失败不炸主流程）
// ═══════════════════════════════════════════════════════════════

export const AuditEventType = Object.freeze({
  STATE_INTERCEPT: "state_intercept_event",
  GATE_GUARD: "gate_guard_event",
  CONTENT_ISSUE: "content_issue_event",
  ARTIFACT_VALIDATE: "artifact_validate_event",
});

const _HOOK_EVENT_MAP = {
  artifact_validate: AuditEventType.ARTIFACT_VALIDATE,
  state_intercept: AuditEventType.STATE_INTERCEPT,
  gate_guard: AuditEventType.GATE_GUARD,
  content_issue: AuditEventType.CONTENT_ISSUE,
};

function _normalizeEventType(eventType) {
  const allowed = Object.values(AuditEventType);
  if (allowed.includes(eventType)) return eventType;
  throw new Error(`非法 event_type: ${JSON.stringify(eventType)}，允许值: ${JSON.stringify(allowed)}`);
}

/**
 * 构造并持久化一条标准审计事件（追加 jsonl 一行），返回完整事件对象。
 * 与 Python 版差异：存储为本地 jsonl 而非 SQL 表；id 为行序号（由读取方行号代替）。
 * 写盘失败只告警并返回 null（旁路审计不阻断裁决）。
 */
export function emitAudit(
  eventType,
  traceId,
  {
    instanceId = "",
    decision = "",
    ruleHits = [],
    reason = "",
    extra = {},
    auditFile = DEFAULT_AUDIT_FILE,
  } = {}
) {
  const etValue = _normalizeEventType(eventType);
  if (typeof traceId !== "string" || !traceId) {
    throw new Error(`trace_id 非法: ${JSON.stringify(traceId)}`);
  }
  const event = {
    event_type: etValue,
    trace_id: traceId,
    instance_id: instanceId || "",
    decision: decision || "",
    rule_hits: ruleHits || [],
    reason: reason || "",
    extra: extra || {},
    created_at: new Date().toISOString(),
  };
  try {
    _ensureDir(path.dirname(auditFile));
    fs.appendFileSync(auditFile, JSON.stringify(event) + "\n", "utf-8");
    return event;
  } catch (exc) {
    _warn(`审计事件写入失败（不影响主流程）: ${exc.message || exc}`);
    return null;
  }
}

/** 内核四钩子判定事件便捷写入（hook 名 → 事件类型机械映射）。 */
export function emitHookEvent(hook, traceId, opts = {}) {
  if (!(hook in _HOOK_EVENT_MAP)) {
    throw new Error(`非法 hook: ${JSON.stringify(hook)}，允许值: ${JSON.stringify(Object.keys(_HOOK_EVENT_MAP).sort())}`);
  }
  return emitAudit(_HOOK_EVENT_MAP[hook], traceId, opts);
}

/** 按 trace_id 全链检索本地 jsonl，按写入序返回全部事件。 */
export function queryByTrace(traceId, { auditFile = DEFAULT_AUDIT_FILE } = {}) {
  if (typeof traceId !== "string" || !traceId) {
    throw new Error(`trace_id 非法: ${JSON.stringify(traceId)}`);
  }
  let text;
  try {
    text = fs.readFileSync(auditFile, "utf-8");
  } catch {
    return [];
  }
  const out = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const ev = JSON.parse(line);
      if (ev.trace_id === traceId) out.push(ev);
    } catch { /* 跳过坏行 */ }
  }
  return out;
}

// ═══════════════════════════════════════════════════════════════
// state_store.py 移植 — 实例状态存取（本地 JSON 文件 + 乐观锁版本）
// ═══════════════════════════════════════════════════════════════

export class StateStoreError extends Error {
  constructor(message) {
    super(message);
    this.name = "StateStoreError";
  }
}

export class StateConflictError extends StateStoreError {
  constructor(message) {
    super(message);
    this.name = "StateConflictError";
  }
}

function _instanceFile(stateDir, instanceId) {
  // instance_id 任意字符串 → 安全文件名（% 编码，保留原文于文件内）
  return path.join(stateDir, encodeURIComponent(instanceId) + ".json");
}

function _validateTransition(instanceId, fromState, toState, operator, expectedVersion, meta) {
  if (typeof instanceId !== "string" || !instanceId) {
    throw new StateStoreError(`instance_id 非法: ${JSON.stringify(instanceId)}`);
  }
  if (fromState !== null && fromState !== undefined && (typeof fromState !== "string" || !fromState)) {
    throw new StateStoreError(`from_state 非法: ${JSON.stringify(fromState)}`);
  }
  if (typeof toState !== "string" || !toState) {
    throw new StateStoreError(`to_state 非法: ${JSON.stringify(toState)}`);
  }
  if (typeof operator !== "string" || !operator) {
    throw new StateStoreError(`operator 非法: ${JSON.stringify(operator)}`);
  }
  if (typeof expectedVersion !== "number" || !Number.isInteger(expectedVersion) || expectedVersion < 0) {
    throw new StateStoreError(`expected_version 非法: ${JSON.stringify(expectedVersion)}`);
  }
  if (meta !== null && meta !== undefined) {
    if (typeof meta !== "object" || Array.isArray(meta)) {
      throw new StateStoreError(`meta 必须是 dict 或 null: ${_typeOf(meta)}`);
    }
    try {
      JSON.stringify(meta);
    } catch (exc) {
      throw new StateStoreError(`meta 不可 JSON 序列化: ${exc.message || exc}`);
    }
  }
}

/**
 * JsonFileStateStore — StateStore 的本地 JSON 文件实现。
 * 每实例一个文件：<stateDir>/<encodeURIComponent(instance_id)>.json：
 *   { instance_id, state, version, updated_at, history: [...] }
 * 乐观锁语义与 SqliteStateStore 一致（单进程内读改写串行，原子落盘 tmp+rename）。
 */
export class JsonFileStateStore {
  constructor(stateDir = DEFAULT_STATE_DIR) {
    this.stateDir = stateDir;
    _ensureDir(stateDir);
  }

  _read(instanceId) {
    const file = _instanceFile(this.stateDir, instanceId);
    try {
      return JSON.parse(fs.readFileSync(file, "utf-8"));
    } catch {
      return null;
    }
  }

  _write(rec) {
    const file = _instanceFile(this.stateDir, rec.instance_id);
    const tmp = file + `.tmp-${process.pid}`;
    fs.writeFileSync(tmp, JSON.stringify(rec, null, 2), "utf-8");
    fs.renameSync(tmp, file);
  }

  /** 返回 {state, version}；实例不存在抛 StateStoreError。 */
  getState(instanceId) {
    if (typeof instanceId !== "string" || !instanceId) {
      throw new StateStoreError(`instance_id 非法: ${JSON.stringify(instanceId)}`);
    }
    const rec = this._read(instanceId);
    if (rec === null) throw new StateStoreError(`实例不存在: ${instanceId}`);
    return { state: rec.state, version: rec.version };
  }

  /** 登记实例初始状态（幂等）。已存在则返回当前 {state, version}。 */
  ensureInstance(instanceId, initialState) {
    if (typeof instanceId !== "string" || !instanceId) {
      throw new StateStoreError(`instance_id 非法: ${JSON.stringify(instanceId)}`);
    }
    if (typeof initialState !== "string" || !initialState) {
      throw new StateStoreError(`initial_state 非法: ${JSON.stringify(initialState)}`);
    }
    let rec = this._read(instanceId);
    if (rec === null) {
      rec = {
        instance_id: instanceId,
        state: initialState,
        version: 0,
        updated_at: new Date().toISOString(),
        history: [],
      };
      this._write(rec);
    }
    return { state: rec.state, version: rec.version };
  }

  /**
   * 乐观锁状态流转。成功返回 {state, version}（新版本号）。
   * 版本冲突 → StateConflictError；源状态不匹配/实例不存在/参数非法 → StateStoreError。
   * 成功时同文件追加 history 一行（对齐 engine_state_history 语义）。
   */
  transition(instanceId, fromState, toState, operator, expectedVersion, meta = null, traceId = null) {
    _validateTransition(instanceId, fromState, toState, operator, expectedVersion, meta);
    if (traceId === null && meta && typeof meta === "object") {
      traceId = meta.trace_id || "";
    }
    const rec = this._read(instanceId);
    if (rec === null) throw new StateStoreError(`实例不存在: ${instanceId}`);
    if (rec.version !== expectedVersion) {
      throw new StateConflictError(
        `版本冲突: 实例 [${instanceId}] 当前版本 ${rec.version}，` +
        `期望 ${expectedVersion}（状态未变更，请重读后重试）`
      );
    }
    if (fromState !== null && fromState !== undefined && rec.state !== fromState) {
      throw new StateStoreError(
        `源状态不匹配: 实例 [${instanceId}] 当前状态 [${rec.state}]，` +
        `声明 from_state [${fromState}]`
      );
    }
    const newVersion = expectedVersion + 1;
    rec.history.push({
      from_state: rec.state,
      to_state: toState,
      operator,
      version: newVersion,
      trace_id: traceId || "",
      meta: meta || {},
      created_at: new Date().toISOString(),
    });
    rec.state = toState;
    rec.version = newVersion;
    rec.updated_at = new Date().toISOString();
    this._write(rec);
    return { state: toState, version: newVersion };
  }

  /** 按时间序返回实例的全部变更历史。 */
  history(instanceId) {
    const rec = this._read(instanceId);
    if (rec === null) throw new StateStoreError(`实例不存在: ${instanceId}`);
    return (rec.history || []).map((h, i) => ({ id: i + 1, instance_id: instanceId, ...h }));
  }
}

// ═══════════════════════════════════════════════════════════════
// state_wiring.py 移植 — 状态收口双写
// ═══════════════════════════════════════════════════════════════

/**
 * 增量双写一次状态迁移。返回 true=已落账，false=跳过或接线失败（已告警）。
 * 含存量滞后 resync 对齐：StateStore 追踪状态落后于声明 from_state 时，
 * 先补一行 resync 追赶轨迹再记录本次迁移，保证历史链连续可复现。
 */
export function wireStateTransition(
  instanceId,
  fromState,
  toState,
  operator,
  { source, meta = null, stateDir = DEFAULT_STATE_DIR, auditFile = DEFAULT_AUDIT_FILE } = {}
) {
  if (typeof instanceId !== "string" || !instanceId) return false;
  if (fromState !== null && fromState !== undefined && fromState === toState) {
    return false; // 同状态无迁移
  }
  try {
    const store = new JsonFileStateStore(stateDir);
    store.ensureInstance(instanceId, fromState || toState);
    let cur = store.getState(instanceId);

    if (fromState !== null && fromState !== undefined && cur.state !== fromState) {
      store.transition(
        instanceId, cur.state, fromState, operator,
        cur.version,
        { source, resync: true },
        `${source}-${instanceId}-v${cur.version}-resync`
      );
      cur = store.getState(instanceId);
    }

    const traceId = `${source}-${instanceId}-v${cur.version}`;
    store.transition(
      instanceId, fromState ?? null, toState, operator,
      cur.version,
      { source, ...(meta || {}) },
      traceId
    );
    emitAudit(AuditEventType.STATE_INTERCEPT, traceId, {
      instanceId,
      decision: "pass",
      ruleHits: [`${fromState}->${toState}`],
      reason: `${source} 接线落账`,
      extra: { operator, ...(meta || {}) },
      auditFile,
    });
    return true;
  } catch (exc) {
    _warn(`StateStore 双写接线失败（不影响主流程）[${instanceId}]: ${exc.message || exc}`);
    return false;
  }
}

/** 实例创建时登记初始状态（幂等）。已存在则不动，返回 true。 */
export function wireStateRegistration(instanceId, initialState, { source, stateDir = DEFAULT_STATE_DIR } = {}) {
  if (typeof instanceId !== "string" || !instanceId) return false;
  try {
    new JsonFileStateStore(stateDir).ensureInstance(instanceId, initialState);
    return true;
  } catch (exc) {
    _warn(`StateStore 实例登记失败（不影响主流程）[${instanceId}] source=${source}: ${exc.message || exc}`);
    return false;
  }
}

// ═══════════════════════════════════════════════════════════════
// kernel.py 移植 — et() 统一执行入口
// ═══════════════════════════════════════════════════════════════

/** FIX-SECRET：debug payload_snapshot 落出前递归掩码 secret 字段。 */
function _maskSnapshot(obj) {
  if (obj !== null && typeof obj === "object" && !Array.isArray(obj)) {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      out[k] = (k === "secret" && typeof v === "string") ? `[MASKED len=${v.length}]` : _maskSnapshot(v);
    }
    return out;
  }
  if (Array.isArray(obj)) return obj.map(_maskSnapshot);
  return obj;
}

/** 固定钩子时序（artifact_validate 为平台扩展校验钩子，先于状态拦截）。 */
const HOOK_ORDER = ["artifact_validate", "state_intercept", "gate_guard", "content_issue"];

const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const _now = () => performance.now();

// ── 服务端权威计量（进程内；单线程无需锁） ──

let _IN_FLIGHT = 0;                    // 内核自测并发：当前 et() 在飞请求数
const _RATE_WINDOW_SEC = 60.0;         // 速率滑窗（固定 60s）
const _RATE_EVENTS = new Map();        // key -> 请求时间戳数组（内核自计数）
const _USAGE_LEDGER = new Map();       // identity -> {token,cost} 单调高水位台账

function _quotaIdentity(payload) {
  const meta = payload.audit_meta || {};
  return String(meta.principal || meta.tenant_id || "anon");
}

function _kernelConcurrency() {
  return _IN_FLIGHT;
}

/** 记录本次请求并返回滑窗内请求数（内核侧自计数，ET 无法伪造）。 */
function _kernelRate(key) {
  const now = _now() / 1000.0;
  let dq = _RATE_EVENTS.get(key);
  if (!dq) { dq = []; _RATE_EVENTS.set(key, dq); }
  const cutoff = now - _RATE_WINDOW_SEC;
  while (dq.length && dq[0] < cutoff) dq.shift();
  dq.push(now);
  return dq.length;
}

/** 单调高水位夹紧：有效用量 = max(ET 上报, 内核台账)，台账只增不减。 */
function _kernelUsageClamp(identity, field, reported) {
  let ledger = _USAGE_LEDGER.get(identity);
  if (!ledger) { ledger = {}; _USAGE_LEDGER.set(identity, ledger); }
  const effective = Math.max(Number(reported) || 0, ledger[field] || 0);
  ledger[field] = effective;
  return effective;
}

function _emitHookAudit(hook, traceId, decision, ruleHits, reason, elapsedMs, auditFile) {
  // 移植版：审计存储恒绑定本地 jsonl（对齐「审计事件写本地 jsonl」契约）；
  // 落盘异常仅告警不阻断裁决——审计是旁路留痕，不反向影响门禁判定。
  try {
    emitHookEvent(hook, traceId, {
      decision,
      ruleHits: ruleHits || [],
      reason: reason || "",
      extra: { hook, elapsed_ms: elapsedMs },
      auditFile,
    });
  } catch (exc) {
    _warn(`hook [${hook}] 审计落盘失败（裁决不受影响）: ${exc.message || exc}`);
  }
}

// ── artifact 点号路径工具（支持 a[].b 一层嵌套通配） ──

function _resolvePath(cur, parts, def) {
  if (!parts.length) return cur;
  const part = parts[0];
  if (part.endsWith("[]")) {
    const key = part.slice(0, -2);
    if (cur === null || typeof cur !== "object" || Array.isArray(cur) || !(key in cur)) return def;
    const seq = cur[key];
    if (!Array.isArray(seq)) return def;
    const rest = parts.slice(1);
    if (!rest.length) return seq;
    return seq.map((item) => _resolvePath(item, rest, def));
  }
  if (cur !== null && typeof cur === "object" && !Array.isArray(cur) && part in cur) {
    return _resolvePath(cur[part], parts.slice(1), def);
  }
  return def;
}

function _getPath(obj, dotted, def = undefined) {
  return _resolvePath(obj, String(dotted).split("."), def);
}

// ── Python 风格小工具（消息文本对齐） ──

function _pyRepr(v) {
  if (typeof v === "string") {
    if (!v.includes("'")) return `'${v.replace(/\\/g, "\\\\")}'`;
    return `"${v.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  return String(v);
}

const _pct = (x) => `${(x * 100).toFixed(2)}%`;

// ── artifact_validate：交付物校验原语（14 个，全部零业务常量） ──

function _checkRequiredFields(check, artifact) {
  const fields = check.fields || [];
  const textSource = check.text_source;
  let missing;
  if (textSource) {
    const text = String(_getPath(artifact, textSource, ""));
    missing = fields.filter((f) => !text.includes(f));
  } else if (artifact !== null && typeof artifact === "object" && !Array.isArray(artifact)) {
    missing = fields.filter((f) => !(f in artifact));
  } else {
    missing = fields;
  }
  return [missing.length === 0, missing.length ? `缺少必要字段: ${missing.join(", ")}` : ""];
}

function _absPath(p) {
  let expanded = String(p || "");
  if (expanded === "~") expanded = os.homedir();
  else if (expanded.startsWith("~/")) expanded = path.join(os.homedir(), expanded.slice(2));
  return path.resolve(expanded);
}

function _checkFileExists(check) {
  const p = _absPath(check.path || "");
  let st;
  try { st = fs.statSync(p); } catch { return [false, `文件不存在或不是文件: ${p}`]; }
  if (!st.isFile()) return [false, `文件不存在或不是文件: ${p}`];
  if (st.size === 0) return [false, `文件为空（0 字节）: ${p}`];
  return [true, ""];
}

function _checkFileMinSize(check) {
  const p = _absPath(check.path || "");
  let st;
  try { st = fs.statSync(p); } catch { return [false, `文件不存在: ${p}`]; }
  if (!st.isFile()) return [false, `文件不存在: ${p}`];
  const minSize = check.min_size ?? 1;
  if (st.size < minSize) return [false, `文件大小 ${st.size}B 低于阈值 ${minSize}B: ${p}`];
  return [true, ""];
}

function _checkJsonField(check) {
  const p = _absPath(check.path || "");
  let data;
  try {
    data = JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch (exc) {
    return [false, `JSON 解析失败: ${p}（${exc.message || exc}）`];
  }
  const fields = check.fields || [];
  const missing = fields.filter(
    (f) => data === null || typeof data !== "object" || Array.isArray(data) || !(f in data)
  );
  return [missing.length === 0, missing.length ? `JSON 缺少字段: ${missing.join(", ")}` : ""];
}

function _checkRegex(check, artifact) {
  const text = String(_getPath(artifact, check.text_source || "", ""));
  const re = new RegExp(check.pattern || "", "m"); // Python re.MULTILINE
  if (!re.test(text)) return [false, `文本未命中必需模式: ${check.pattern}`];
  return [true, ""];
}

function _checkMinRatio(check) {
  let num, den;
  try {
    num = Number(check.numerator);
    den = Number(check.denominator);
    if (Number.isNaN(num) || Number.isNaN(den)) throw new Error("NaN");
  } catch {
    return [false, "min_ratio 参数非法（numerator/denominator 须为数值）"];
  }
  if (check.numerator === undefined || check.denominator === undefined) {
    return [false, "min_ratio 参数非法（numerator/denominator 须为数值）"];
  }
  if (den <= 0) return [false, "min_ratio 分母必须为正数"];
  const ratio = num / den;
  const minV = check.min ?? 0;
  return [ratio >= minV, ratio >= minV ? "" : `比率 ${_pct(ratio)} 低于阈值 ${_pct(minV)}`];
}

const _MISSING = Symbol("missing"); // 区别于 null 的「键缺失」哨兵

function _iterItems(check, artifact) {
  const items = _getPath(artifact, check.items_path || "", []);
  return Array.isArray(items) ? items : [];
}

function _checkItemsRegex(check, artifact) {
  const items = _iterItems(check, artifact);
  const field = check.field || "";
  const pattern = check.pattern || "";
  const re = new RegExp(pattern);
  const bad = [];
  items.forEach((item, i) => {
    const value = (item !== null && typeof item === "object") ? _getPath(item, field, "") : "";
    const text = value === null || value === undefined ? "" : String(value);
    if (!re.test(text)) bad.push(`#${i}[${field}]=${_pyRepr(text)}`);
  });
  if (bad.length) return [false, `${bad.length} 项未命中正则 ${pattern}: ${bad.join("; ")}`];
  return [true, ""];
}

function _checkItemsUnique(check, artifact) {
  const items = _iterItems(check, artifact);
  const field = check.field || "";
  const seen = new Set();
  const dups = [];
  for (const item of items) {
    const value = (item !== null && typeof item === "object") ? _getPath(item, field) : null;
    if (value === null || value === undefined || value === "") continue; // 空值不参与去重
    const key = String(value);
    if (seen.has(key) && !dups.includes(key)) dups.push(key);
    seen.add(key);
  }
  if (dups.length) return [false, `字段 ${field} 存在重复值: ${dups.join(", ")}`];
  return [true, ""];
}

function _checkItemsRequiredFields(check, artifact) {
  const items = _iterItems(check, artifact);
  const fields = check.fields || [];
  const nonempty = Boolean(check.nonempty);
  const problems = [];
  items.forEach((item, i) => {
    const missing = [];
    for (const f of fields) {
      const value = (item !== null && typeof item === "object") ? _getPath(item, f, _MISSING) : _MISSING;
      if (value === _MISSING || (nonempty && !value)) missing.push(f);
    }
    if (missing.length) problems.push(`#${i} 缺 ${missing.join(",")}`);
  });
  if (problems.length) {
    return [false, `数组 ${check.items_path || ""} 存在缺字段项: ${problems.join("; ")}`];
  }
  return [true, ""];
}

function _checkItemsEnum(check, artifact) {
  const items = _iterItems(check, artifact);
  const field = check.field || "";
  const values = check.values || [];
  const bad = [];
  items.forEach((item, i) => {
    if (field.includes("[]")) {
      const resolved = _getPath(item, field, _MISSING);
      if (resolved === _MISSING) return; // 通配序列缺失 → 无值可裁
      const seq = Array.isArray(resolved) ? resolved : [resolved];
      seq.forEach((v, j) => {
        const vv = v === null || v === undefined ? "" : v;
        if (!values.includes(vv)) bad.push(`#${i}.${j}=${_pyRepr(vv)}`);
      });
    } else {
      const v = (item !== null && typeof item === "object") ? _getPath(item, field, null) : null;
      const vv = v === null || v === undefined ? "" : v;
      if (!values.includes(vv)) bad.push(`#${i}=${_pyRepr(vv)}`);
    }
  });
  if (bad.length) return [false, `字段 ${field} 存在枚举外取值: ${bad.join("; ")}`];
  return [true, ""];
}

// ── 零依赖 glob（支持 * ? **，对齐 Python glob recursive=True 常用语义） ──

function _globSegmentToRe(seg) {
  let out = "";
  for (const ch of seg) {
    if (ch === "*") out += "[^/]*";
    else if (ch === "?") out += "[^/]";
    else out += ch.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp("^" + out + "$");
}

function _globCount(rootDir, pattern) {
  const segs = String(pattern).split("/").filter((s) => s !== "");
  let count = 0;
  const walk = (dir, idx) => {
    if (idx >= segs.length) { count++; return; }
    const seg = segs[idx];
    if (seg === "**") {
      walk(dir, idx + 1); // ** 匹配零层
      let entries;
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        if (e.isDirectory()) walk(path.join(dir, e.name), idx); // ** 匹配任意深度
      }
      return;
    }
    const re = _globSegmentToRe(seg);
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (re.test(e.name)) walk(path.join(dir, e.name), idx + 1);
    }
  };
  walk(rootDir, 0);
  return count;
}

function _checkDirGlobCount(check) {
  const p = _absPath(check.path || "");
  let st;
  try { st = fs.statSync(p); } catch { return [false, `目录不存在: ${p}`]; }
  if (!st.isDirectory()) return [false, `目录不存在: ${p}`];
  const pattern = check.pattern || "*";
  const minCount = check.min ?? 1;
  const count = _globCount(p, pattern);
  if (count < minCount) return [false, `目录匹配数 ${count} 低于下限 ${minCount}: ${p}/${pattern}`];
  return [true, ""];
}

function _checkDirFileCountEqJson(check) {
  const p = _absPath(check.path || "");
  let st;
  try { st = fs.statSync(p); } catch { return [false, `目录不存在: ${p}`]; }
  if (!st.isDirectory()) return [false, `目录不存在: ${p}`];
  const jsonPath = path.join(p, check.json_file || "");
  let data;
  try {
    data = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));
  } catch (exc) {
    return [false, `JSON 解析失败: ${jsonPath}（${exc.message || exc}）`];
  }
  const jsonField = check.json_field || "";
  const expected = (data !== null && typeof data === "object" && !Array.isArray(data)) ? data[jsonField] : null;
  if (typeof expected !== "number" || Number.isNaN(expected)) {
    return [false, `JSON 字段 ${jsonField} 缺失或非数值: ${jsonPath}`];
  }
  const suffix = check.suffix || "";
  const count = fs.readdirSync(p).filter(
    (name) => name.endsWith(suffix) && fs.statSync(path.join(p, name)).isFile()
  ).length;
  if (count !== expected) {
    return [false, `目录文件数 ${count} != 声明值 ${expected}（${jsonField}）: ${p}`];
  }
  return [true, ""];
}

function _checkDirFileHashUnique(check) {
  const p = _absPath(check.path || "");
  let st;
  try { st = fs.statSync(p); } catch { return [false, `目录不存在: ${p}`]; }
  if (!st.isDirectory()) return [false, `目录不存在: ${p}`];
  const algo = check.algo || "md5";
  try {
    crypto.createHash(algo);
  } catch (exc) {
    return [false, `不支持的哈希算法 ${algo}: ${exc.message || exc}`];
  }
  const suffix = check.suffix || "";
  const files = fs.readdirSync(p)
    .filter((name) => name.endsWith(suffix) && fs.statSync(path.join(p, name)).isFile())
    .sort();
  const digests = new Set();
  const reused = [];
  for (const name of files) {
    const digest = crypto.createHash(algo).update(fs.readFileSync(path.join(p, name))).digest("hex");
    if (digests.has(digest)) reused.push(name);
    digests.add(digest);
  }
  if (reused.length) return [false, `文件内容哈希复用（${algo}）: ${reused.join(", ")}`];
  return [true, ""];
}

function _checkFieldsDistinct(check, artifact) {
  const fieldA = check.field_a || "";
  const fieldB = check.field_b || "";
  const a = _getPath(artifact, fieldA);
  const b = _getPath(artifact, fieldB);
  const empty = (v) => v === null || v === undefined || v === "";
  if (check.ignore_empty && (empty(a) || empty(b))) return [true, ""];
  if (a === b) {
    return [false, `字段 ${fieldA} 与 ${fieldB} 取值相同（${_pyRepr(a)}），违反相异约束`];
  }
  return [true, ""];
}

const _VALIDATE_DISPATCH = {
  required_fields: _checkRequiredFields,
  file_exists: _checkFileExists,
  file_min_size: _checkFileMinSize,
  json_field: _checkJsonField,
  regex: _checkRegex,
  min_ratio: _checkMinRatio,
  items_regex: _checkItemsRegex,
  items_unique: _checkItemsUnique,
  items_required_fields: _checkItemsRequiredFields,
  items_enum: _checkItemsEnum,
  dir_glob_count: _checkDirGlobCount,
  dir_file_count_eq_json: _checkDirFileCountEqJson,
  dir_file_hash_unique: _checkDirFileHashUnique,
  fields_distinct: _checkFieldsDistinct,
};

function _runArtifactValidate(spec, artifact) {
  const results = [];
  const failures = [];
  for (const check of spec.checks) {
    const handler = _VALIDATE_DISPATCH[check.type];
    const [ok, reason] = handler(check, artifact);
    const item = {
      id: check.id,
      type: check.type,
      passed: ok,
      message: check.message || reason,
    };
    results.push(item);
    if (!ok) failures.push(item);
  }
  return { pass: failures.length === 0, results, failures };
}

// ── state_intercept：状态拦截 & 跃迁 ──

function _runStateIntercept(spec, artifact) {
  let current = spec.current_state;
  if ((current === undefined || current === null) &&
      artifact !== null && typeof artifact === "object" && !Array.isArray(artifact)) {
    current = artifact.state;
  }
  const target = spec.target_state;
  const pairs = spec.allowed_pairs;
  if (pairs !== undefined && pairs !== null) {
    const pairSet = new Set(pairs.map((p) => JSON.stringify([p.from, p.to])));
    if (!pairSet.has(JSON.stringify([current, target]))) {
      return [false, null, artifact,
        `跃迁对 [${current} → ${target}] 不在 allowed_pairs 合法集合内`];
    }
  } else {
    // 弱模式回退：只校验源状态，不校验目标（契约已标注不推荐）
    const allow = spec.allow_transition;
    if (allow !== undefined && allow !== null && !allow.includes(current)) {
      return [false, null, artifact,
        `源状态 [${current}] 不在允许跃迁集合 ${JSON.stringify(allow)}`];
    }
  }
  if (spec.state_meta && artifact !== null && typeof artifact === "object" && !Array.isArray(artifact)) {
    artifact = { ...artifact, state_meta: spec.state_meta };
  }
  return [true, target, artifact, `${current} → ${target} 合法`];
}

// ── gate_guard：门禁准入 ──

function _runGateGuard(spec) {
  if (spec.acl !== undefined && spec.acl !== null) {
    const target = spec.target_agent_id || "";
    if (!spec.acl.includes(target)) {
      return { pass: false, reason: `下游 Agent [${target}] 不在 ACL: ${JSON.stringify(spec.acl)}` };
    }
  }
  if (spec.rate_limit !== undefined && spec.rate_limit !== null) {
    // 服务端权威计量：内核按 key 自维护 60s 滑窗计数，ET 上报 rate_current
    // 仅作参考——有效速率 = max(ET上报, 内核实测)，报低无法穿透限流
    const key = spec.target_agent_id || spec.route || "global";
    const measured = _kernelRate(key);
    const reported = spec.rate_current;
    const effective = Math.max(reported !== undefined && reported !== null ? reported : 0, measured);
    if (effective >= spec.rate_limit) {
      return { pass: false,
        reason: `速率超限: ${effective}/${spec.rate_limit}` +
                `（内核 60s 滑窗实测 ${measured}，ET 上报 ${reported}）` };
    }
  }
  if (spec.route_whitelist !== undefined && spec.route_whitelist !== null) {
    const route = spec.route || "";
    if (!spec.route_whitelist.includes(route)) {
      return { pass: false, reason: `路由 [${route}] 不在白名单: ${JSON.stringify(spec.route_whitelist)}` };
    }
  }
  return { pass: true, reason: "" };
}

// ── content_issue：内容签发 / 防篡改 ──

/** 内容指纹：sha256(canonical(artifact))[:12]，水印派生源（ENG-WM-ASYMM）。 */
function _contentFingerprint(artifact) {
  return crypto.createHash("sha256").update(canonicalStringify(artifact), "utf-8").digest("hex").slice(0, 12);
}

function _runContentIssue(spec, artifact, traceId, stateSpec = null) {
  const issueMeta = { ...(spec.attach_issue_meta || {}) };
  let signed = artifact;

  if (spec.sign) {
    const algo = spec.sign_algo || "sha256";
    const signState = stateSpec
      ? { current_state: stateSpec.current_state, target_state: stateSpec.target_state }
      : {};
    let secret = spec.secret; // string | undefined；缺省且 hmac 时走内核默认密钥（签名时刻惰性解析）
    if (!secret && algo === "hmac-sha256") {
      secret = defaultSecret(); // 缺 AGENT_ENGINE_SECRET 在此 raise → 内核异常通道 code=error
    }
    if (spec.watermark) {
      // ENG-WM-ASYMM：水印先于签名注入，派生自内容指纹（与签名解耦）；
      // 签名覆盖含水印终态 → 交付物逐字节可验，水印篡改即验签失败。
      const wm = `wm:${traceId}:${_contentFingerprint(artifact)}`;
      if (signed !== null && typeof signed === "object" && !Array.isArray(signed)) {
        signed = { ...signed, _watermark: wm };
      }
      issueMeta.watermark = wm;
    }
    const signature = computeSignature(signed, traceId, signState, algo, secret);
    issueMeta.algo = algo;
    issueMeta.signature = signature;
    issueMeta.issued_at = new Date().toISOString();
  }
  return [signed, issueMeta];
}

// ── resource_control：资源 & 配额前置检查（服务端权威计量版） ──

function _runResourceControl(spec, identity = "anon") {
  const violations = [];
  const metering = {};
  if (spec.token_limit !== undefined && spec.token_limit !== null) {
    const reported = spec.token_used;
    const effective = _kernelUsageClamp(identity, "token", reported || 0);
    metering.token = { reported: reported ?? null, kernel_ledger: effective };
    if (effective >= spec.token_limit) {
      violations.push(`token 超限: ${effective}/${spec.token_limit}（ET 上报 ${reported}，内核台账夹紧）`);
    }
  }
  if (spec.max_concurrent !== undefined && spec.max_concurrent !== null) {
    const reported = spec.concurrent_current;
    const measured = _kernelConcurrency();
    const effective = Math.max(reported !== undefined && reported !== null ? reported : 0, measured);
    metering.concurrent = { reported: reported ?? null, kernel_measured: measured };
    if (effective >= spec.max_concurrent) {
      violations.push(`并发超限: ${effective}/${spec.max_concurrent}（内核实测 ${measured}，ET 上报 ${reported}）`);
    }
  }
  if (spec.cost_budget !== undefined && spec.cost_budget !== null) {
    const reported = spec.cost_used;
    const effective = _kernelUsageClamp(identity, "cost", reported || 0);
    metering.cost = { reported: reported ?? null, kernel_ledger: effective };
    if (effective >= spec.cost_budget) {
      violations.push(`成本超预算: ${effective}/${spec.cost_budget}（ET 上报 ${reported}，内核台账夹紧）`);
    }
  }
  if (spec.model_allow_list && spec.model_allow_list.length) {
    const model = spec.model || "";
    if (!spec.model_allow_list.includes(model)) {
      violations.push(`模型 [${model}] 不在允许列表: ${JSON.stringify(spec.model_allow_list)}`);
    }
  }
  const out = { pass: violations.length === 0, violations, priority: spec.priority || "normal" };
  if (Object.keys(metering).length) out.metering = metering;
  return out;
}

// ── failure_policy / delivery ──

function _applyFailurePolicy(policy, errorMsg, executedRetry = 0) {
  const info = { error_msg: errorMsg };
  if (policy) {
    if (policy.fallback_target) info.fallback_target = policy.fallback_target;
    if (policy.max_retry !== undefined && policy.max_retry !== null) {
      info.max_retry = policy.max_retry;
      info.retry_delay_ms = policy.retry_delay_ms ?? 0;
      info.executed_retry = executedRetry;
    }
    if (policy.compensation_action) info.compensation_action = policy.compensation_action;
    if (policy.alert_on_block) {
      info.alert = true;
      _warn(`ALERT_ON_BLOCK: ${errorMsg}`);
    }
  }
  return info;
}

function _applyDelivery(spec, artifact, code) {
  const out = {
    next_handler: spec.next_handler ?? null,
    require_ack: Boolean(spec.require_ack ?? false),
    mode: spec.mode || "single",
    payload: null,
  };
  if (code !== "success") return out;
  const transform = spec.output_transform;
  let data = artifact;
  if (transform && artifact !== null && typeof artifact === "object" && !Array.isArray(artifact)) {
    data = { ...artifact };
    if (transform.include_fields) {
      const inc = {};
      for (const k of transform.include_fields) if (k in data) inc[k] = data[k];
      data = inc;
    }
    if (transform.exclude_fields) {
      const ex = new Set(transform.exclude_fields);
      data = Object.fromEntries(Object.entries(data).filter(([k]) => !ex.has(k)));
    }
    for (const field of transform.mask_fields || []) {
      if (typeof data[field] === "string") data[field] = "***";
    }
  }
  out.payload = data;
  return out;
}

// ── 内核唯一入口 ──

/**
 * 引擎内核统一入口（async）。
 *
 * 入参：符合 PAYLOAD_SCHEMA 的标准 Payload（内核只认契约）。
 * 出参：符合 OUTPUT_SCHEMA 的标准出参，code ∈ success/reject/block/timeout/error。
 * 契约不通过时抛 ContractViolationError / OutputContractError。
 *
 * options（移植版新增，全部可选）：
 *   auditFile  审计 jsonl 路径（默认 ~/.dsh/xujin-engine/audit.jsonl）
 *   audit      false 时跳过钩子审计落盘（默认 true）
 */
export async function et(payload, options = {}) {
  validatePayload(payload);
  _IN_FLIGHT += 1; // 服务端权威并发计量：进入即在飞
  try {
    return await _etInner(payload, options);
  } finally {
    _IN_FLIGHT -= 1;
  }
}

async function _etInner(payload, options) {
  const auditFile = options.auditFile || DEFAULT_AUDIT_FILE;
  const auditOn = options.audit !== false;

  let artifact = structuredClone(payload.artifact);
  const traceId = payload.trace_id;
  let code = "success";
  let errorMsg = "";

  let newTaskState = null;
  let gateResult = null;
  let validateResult = null;
  let resourceOut = null;
  let signedArtifact = null;
  let issueMeta = null;
  const hookElapsed = {};

  const rc = payload.resource_control || {};
  const hookTimeoutMs = rc.hook_timeout_ms;
  const globalTimeoutMs = rc.global_timeout_ms;
  const tStart = _now();
  let executedRetry = 0; // artifact_validate 实际已执行的重试次数（failure_policy 消费）

  // ── 前置：资源 & 配额（服务端权威计量：ET 自报仅作参考） ──
  if (payload.resource_control) {
    resourceOut = _runResourceControl(payload.resource_control, _quotaIdentity(payload));
    if (!resourceOut.pass) {
      code = "block";
      errorMsg = resourceOut.violations.join("; ");
    }
  }

  // ── 固定钩子时序 ──
  if (code === "success") {
    for (const hook of HOOK_ORDER) {
      const spec = payload[hook];
      if (spec === undefined || spec === null) continue;
      if (globalTimeoutMs && (_now() - tStart) > globalTimeoutMs) {
        code = "timeout";
        errorMsg = `全局超时: 已超过 ${globalTimeoutMs}ms（hook [${hook}] 未执行）`;
        break;
      }
      // ── 抢占式时限：hook_timeout_ms 与全局剩余预算取小 ──
      let effTimeoutMs = null;
      if (hookTimeoutMs !== undefined && hookTimeoutMs !== null) {
        effTimeoutMs = Number(hookTimeoutMs);
      }
      if (globalTimeoutMs) {
        const remainingMs = globalTimeoutMs - (_now() - tStart);
        effTimeoutMs = effTimeoutMs !== null ? Math.min(effTimeoutMs, remainingMs) : remainingMs;
      }

      const invokeHook = () => {
        if (hook === "state_intercept") {
          const [ok, nts, art, reason] = _runStateIntercept(spec, artifact);
          newTaskState = nts;
          artifact = art;
          if (!ok) {
            code = "block";
            errorMsg = reason;
          }
        } else if (hook === "gate_guard") {
          gateResult = _runGateGuard(spec);
          if (!gateResult.pass) {
            code = "block";
            errorMsg = gateResult.reason;
          }
        } else if (hook === "content_issue") {
          const [sa, im] = _runContentIssue(spec, artifact, traceId, payload.state_intercept || null);
          signedArtifact = sa;
          issueMeta = im;
        }
      };

      // artifact_validate 的 retry_delay：同步闭包无法 sleep，若声明了
      // retry_delay_ms 且需要重试，在异步侧先补一次带 sleep 的重试。
      const invokeHookAsync = async () => {
        if (hook === "artifact_validate") {
          const policy = payload.failure_policy || {};
          const maxRetry = policy.max_retry || 0;
          const retryDelayMs = policy.retry_delay_ms || 0;
          while (true) {
            validateResult = _runArtifactValidate(spec, artifact);
            if (validateResult.pass || executedRetry >= maxRetry) break;
            if (globalTimeoutMs &&
                (_now() - tStart) + retryDelayMs > globalTimeoutMs) {
              break; // 再等会越全局超时上限，停止重试，维持本次失败结论
            }
            if (retryDelayMs) await _sleep(retryDelayMs);
            executedRetry += 1;
          }
          if (!validateResult.pass) {
            code = "reject";
            errorMsg = validateResult.failures.map((f) => f.message).join("; ");
          }
          return;
        }
        invokeHook();
      };

      const t0 = _now();
      let completed = true;
      if (effTimeoutMs !== null && effTimeoutMs <= 0) {
        // 预算已耗尽：钩子不再执行，确定性判超时（0 预算场景无调度竞态）
        completed = false;
      } else if (effTimeoutMs === null) {
        try {
          await invokeHookAsync();
        } catch (exc) { // 内核/签发异常
          code = "error";
          errorMsg = `hook [${hook}] 执行异常: ${exc.message || exc}`;
        }
      } else {
        try {
          completed = await Promise.race([
            (async () => { await invokeHookAsync(); return true; })(),
            _sleep(Math.max(effTimeoutMs, 0)).then(() => false),
          ]);
        } catch (exc) { // 内核/签发异常
          code = "error";
          errorMsg = `hook [${hook}] 执行异常: ${exc.message || exc}`;
        }
      }
      if (!completed) {
        code = "timeout";
        errorMsg = `hook [${hook}] 超时（抢占式）: 超过 ${Math.max(effTimeoutMs || 0, 0).toFixed(0)}ms 预算未完成，其产出不再被消费`;
      }
      const elapsedMs = _now() - t0;
      hookElapsed[hook] = Math.round(elapsedMs * 1000) / 1000;

      if (code === "success" && hookTimeoutMs !== undefined && hookTimeoutMs !== null && elapsedMs > hookTimeoutMs) {
        // 兜底复检：正常已被抢占拦截，仅计时抖动时兜底，语义同前
        code = "timeout";
        errorMsg = `hook [${hook}] 超时: ${elapsedMs.toFixed(3)}ms > ${hookTimeoutMs}ms`;
      }

      // ── 钩子判定审计落盘（旁路，异常不阻断裁决） ──
      if (auditOn) {
        if (code === "success") {
          _emitHookAudit(hook, traceId, "pass", [], "", hookElapsed[hook], auditFile);
        } else {
          let hits = [];
          if (hook === "artifact_validate" && validateResult !== null) {
            hits = [...(validateResult.failures || [])];
          } else if (hook === "gate_guard" && gateResult !== null) {
            hits = [{ message: gateResult.reason || "" }];
          }
          _emitHookAudit(hook, traceId, code, hits, errorMsg, hookElapsed[hook], auditFile);
        }
      }

      if (code !== "success") break;
    }
  }

  // ── P1-1 状态脏写修复：非 success 出参不得携带目标态 ──
  if (code !== "success") {
    newTaskState = null;
  }

  // ── 失败策略（阻断 ≠ 直接死掉） ──
  const failureInfo = code !== "success"
    ? _applyFailurePolicy(payload.failure_policy || null, errorMsg, executedRetry)
    : null;

  // ── 投递装配 ──
  const deliveryOut = payload.delivery
    ? _applyDelivery(payload.delivery, signedArtifact !== null ? signedArtifact : artifact, code)
    : null;

  // ── failure_policy 实执行：fallback_target 改写投递目标（兜底分流） ──
  if (
    (code === "block" || code === "reject") &&
    deliveryOut !== null &&
    (payload.failure_policy || {}).fallback_target
  ) {
    deliveryOut.next_handler = payload.failure_policy.fallback_target;
  }

  const out = {
    code,
    trace_id: traceId,
    parent_trace_id: payload.parent_trace_id ?? null,
    new_task_state: newTaskState,
    signed_artifact: signedArtifact,
    gate_result: gateResult,
    validate_result: validateResult !== null
      ? { pass: validateResult.pass, results: validateResult.results, failures: validateResult.failures }
      : null,
    resource: resourceOut,
    issue_meta: issueMeta,
    delivery: deliveryOut,
    failure_info: failureInfo,
    audit_meta: payload.audit_meta ?? null,
  };
  if (payload.debug) {
    out._debug = {
      hook_elapsed_ms: hookElapsed,
      payload_snapshot: _maskSnapshot(payload),
    };
  }
  return validateOutput(out);
}

// ═══════════════════════════════════════════════════════════════
// harness-step-sync.sh 移植 — stepSync 本地版（无 HTTP，直调内核）
// ═══════════════════════════════════════════════════════════════

/**
 * stepSync — harness-step-sync.sh 语义的本地版。
 *
 * 原脚本时序（HTTP 版）：健康检查 → 查项目实例 → 读 current_state →
 * 拉 transitions 编译 allowed_pairs → POST /api/engine/et 判定 →
 * code==success 才 POST transition 落库 → 步骤日志 best-effort。
 *
 * 本地版时序（同语义，无 HTTP）：
 *   1. 按 project 查本地实例注册表（stateDir/_projects.json），
 *      未注册时按 options.initialState 登记（缺省 initialState=newState
 *      视为首次登记直接落态，对齐本地无建项流程的现实，见报告偏差节）；
 *   2. 读实例 current_state（本地 StateStore）；
 *   3. 调用方注入 transitions（{from: [to,...]}，规则 yaml 由宿主预解析）；
 *   4. 组装 ET Payload（与原脚本逐字段一致：artifact 含项目/阶段/说明/角色，
 *      state_intercept 强校验 allowed_pairs，content_issue 申请 sha256 签发），
 *      直调本模块 et()；
 *   5. code==success → StateStore 乐观锁 transition 落账 + 审计；
 *      非 success → 原样透出 failure_info，不落账，ok=false；
 *   6. 步骤日志追加 steps.jsonl（best-effort，失败仅告警）。
 *
 * @param {string} project   项目名称（必填）
 * @param {string} newState  目标状态（必填）
 * @param {object} options
 *   stepTitle   步骤标题（默认取 newState）
 *   operator    执行角色（默认 "PM"）
 *   transitions 状态机 {from: [to,...]}（必填；引擎规则由调用方预解析注入）
 *   instanceId  显式实例 ID（缺省查注册表/自动登记 inst-<project>）
 *   initialState 首次登记初始状态（缺省 = newState）
 *   stateDir / auditFile / stepsFile  落盘位置覆盖（默认 ~/.dsh/xujin-engine/）
 * @returns {Promise<{ok:boolean, ...}>} 成功 {ok:true, instanceId, from, to, version, signature, output}；
 *   失败 {ok:false, reason, code?, output?}
 */
export async function stepSync(project, newState, options = {}) {
  const {
    stepTitle = newState,
    operator = "PM",
    transitions,
    instanceId: optInstanceId,
    initialState,
    stateDir = DEFAULT_STATE_DIR,
    auditFile = DEFAULT_AUDIT_FILE,
    stepsFile = DEFAULT_STEPS_FILE,
  } = options;

  if (typeof project !== "string" || !project) {
    throw new StateStoreError(`project 非法: ${JSON.stringify(project)}`);
  }
  if (typeof newState !== "string" || !newState) {
    throw new StateStoreError(`new_state 非法: ${JSON.stringify(newState)}`);
  }
  _ensureDir(stateDir);

  // ── Step 1: 查找/登记项目实例 ──
  const registryFile = path.join(stateDir, "_projects.json");
  let registry = {};
  try {
    registry = JSON.parse(fs.readFileSync(registryFile, "utf-8"));
  } catch { /* 无注册表按空处理 */ }

  const store = new JsonFileStateStore(stateDir);
  let instanceId = optInstanceId || registry[project] || null;

  if (!instanceId) {
    // 本地版无独立建项流程：首次同步即登记（语义偏差见报告）
    instanceId = `inst-${project}`;
    const init = initialState || newState;
    store.ensureInstance(instanceId, init);
    registry[project] = instanceId;
    try {
      fs.writeFileSync(registryFile, JSON.stringify(registry, null, 2), "utf-8");
    } catch (exc) {
      _warn(`实例注册表写入失败（不影响主流程）: ${exc.message || exc}`);
    }
    if (init === newState) {
      // 初始态即目标态：登记即完成，无需走跃迁判定
      const stepLog = {
        event_name: "PMProcessStep",
        step_title: stepTitle,
        step_content: `项目 [${project}] 进入状态 ${newState}`,
        instance_id: instanceId,
        agent_role: operator,
        registration: true,
        created_at: new Date().toISOString(),
      };
      _appendStepLog(stepsFile, stepLog);
      emitAudit(AuditEventType.STATE_INTERCEPT, `step-sync-${instanceId}-register`, {
        instanceId,
        decision: "pass",
        ruleHits: [`<register>->${newState}`],
        reason: "harness-step-sync 首次登记",
        extra: { operator, registration: true },
        auditFile,
      });
      const cur = store.getState(instanceId);
      return {
        ok: true, registered: true, instanceId,
        from: init, to: newState, version: cur.version, signature: null,
      };
    }
  }

  // ── Step 2: 读取实例当前状态 ──
  const cur = store.getState(instanceId); // 不存在抛 StateStoreError（对齐脚本「无法读取即失败」）
  const currentState = cur.state;

  // ── Step 3: transitions → allowed_pairs（调用方注入，缺省即失败） ──
  if (!transitions || typeof transitions !== "object" || Array.isArray(transitions) ||
      Object.keys(transitions).length === 0) {
    return { ok: false, reason: "无法获取状态机 transitions（须由调用方注入 options.transitions）" };
  }
  const pairs = [];
  for (const [from, tos] of Object.entries(transitions)) {
    for (const to of tos || []) pairs.push({ from, to });
  }

  // ── Step 4: 组装 ET Payload 并直调内核判定（与原脚本逐字段一致） ──
  const traceId = `step-sync-${instanceId}-${Math.floor(Date.now() / 1000)}`;
  const payload = {
    trace_id: traceId,
    artifact: {
      project,
      step: newState,
      title: stepTitle,
      operator,
      state: newState,
    },
    state_intercept: {
      current_state: currentState,
      target_state: newState,
      allowed_pairs: pairs,
    },
    content_issue: { sign: true, sign_algo: "sha256" },
    audit_meta: {
      principal: operator,
      audit_tags: ["harness-step-sync"],
    },
  };
  const out = await et(payload, { auditFile });

  // ── Step 5: 仅 code==success 落账；非 success 原样透出 failure_info ──
  if (out.code !== "success") {
    return {
      ok: false,
      code: out.code,
      instanceId,
      reason: `引擎门禁未通过: code=${out.code}，状态不落账`,
      failure_info: out.failure_info,
      output: out,
    };
  }

  const signature = (out.issue_meta && out.issue_meta.signature) || null;
  const settled = store.transition(
    instanceId, currentState, newState, operator, cur.version,
    {
      source: "harness-step-sync",
      comment: `${stepTitle} (via harness-step-sync)`,
      signature,
      trace_id: traceId,
    },
    traceId
  );
  emitAudit(AuditEventType.STATE_INTERCEPT, traceId, {
    instanceId,
    decision: "pass",
    ruleHits: [`${currentState}->${newState}`],
    reason: "harness-step-sync 落账",
    extra: { operator, signature, step_title: stepTitle },
    auditFile,
  });

  // ── Step 6: 步骤日志（best-effort，失败仅告警不阻断） ──
  _appendStepLog(stepsFile, {
    event_name: "PMProcessStep",
    step_title: stepTitle,
    step_content: `项目 [${project}] 进入状态 ${newState}`,
    instance_id: instanceId,
    agent_role: operator,
    task_id: `step-${instanceId}-${Math.floor(Date.now() / 1000)}`,
    trace_id: traceId,
    created_at: new Date().toISOString(),
  });

  return {
    ok: true,
    registered: false,
    instanceId,
    from: currentState,
    to: newState,
    version: settled.version,
    signature,
    output: out,
  };
}

function _appendStepLog(stepsFile, entry) {
  try {
    _ensureDir(path.dirname(stepsFile));
    fs.appendFileSync(stepsFile, JSON.stringify(entry) + "\n", "utf-8");
  } catch (exc) {
    _warn(`步骤日志记录失败（状态已落账，仅告警）: ${exc.message || exc}`);
  }
}