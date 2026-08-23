// dsh-trigger-auto — 触发面全扳手化核心载体（M1：插件 + L0 硬命中投递，2026-08-22 设计 v3 落地）
// 通道① 用户输入：agent/pre-step 首 step 检测新 user 消息（user/message 仅为 session 追加事件，
//       不支持 additionalContexts 中间件改写，实证见 dsh-tool-cordis PostToolDecision 契约）
//       → spawn trigger_signal_scan.py --text <原文> → verdict=HITS 时把命中信号 must_pull
//       格式化为【声明块模板 v2 调试面板】以 user-source 消息注入 decision.messages；
//       v3 起 NO-HIT/纯成分命中注入常显精简行（扫描在岗状态），扫描失败才静默。
// 通道② 危险命令：tools/pre-execute 事前硬阻断（v5，实证 PreToolDecision allow/deny/ask）——
//       命中黑名单且无 danger_cmd_gate 留痕 → return {kind:"deny", reason:落盘+扳闸指引}，
//       放行唯一条件=留痕存在；post-execute 提醒保留兜底（已阻断命令跳过防双响）。
// 通道⑥ 查询闸：tools/pre-execute 拦检索三件套 read/grep/glob（v9 query_weld_hook）——
//       本 turn 无 dual_gates declare 留痕（dual_gates_audit.jsonl 内 timestamp>=turnStart
//       的 declaration_gate_start，5s 容差）即事前硬阻断 + 扳闸指引；扳完重试穿透放行。
// 工程纪律：扫描子进程超时 10s 强杀、一切失败静默返回 null（不拖垮主流程，事后审计闸兜底）。
// v1 残差（如实声明）：只提醒不阻断；bash 命令经变量拼接/包装脚本间接执行的形态不进正则视野。
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFileSync, mkdirSync, openSync, readSync, closeSync, statSync, readFileSync } from "node:fs";
import { dirname } from "node:path";

const name = "dsh-trigger-auto";

const SCAN_SCRIPT = "/Users/xujin/.agents/skills/gate-switch/scripts/trigger_signal_scan.py";
const GATE_LOG = process.env.TRIGGER_AUTO_GATE_LOG || "/Users/xujin/.agents/logs/gate_switch.jsonl";
const DANGER_DIR = process.env.TRIGGER_AUTO_DANGER_DIR || "/Users/xujin/.agents/logs/danger_cmd";
const SIGNALS_JSON = process.env.TRIGGER_AUTO_SIGNALS || "/Users/xujin/.agents/skills/gate-switch/data/trigger_signals.json";
const SCAN_TIMEOUT_MS = 10_000;
const DEDUP_TAIL_LINES = 20;
const TAIL_READ_BYTES = 16 * 1024;

// ===== v6 通道③：扇出焊点（块M fanout_weld_hook，reform_gate 判A 块 fanout_weld_20260822）=====
const DISPATCH_LOG = process.env.TRIGGER_AUTO_DISPATCH_LOG || "/Users/xujin/.agents/logs/dispatch_switch.jsonl";
const DISPATCH_WINDOW_MS = 10 * 60 * 1000; // 留痕有效窗口：近 10 分钟
const FANOUT_FALLBACK_LOG = process.env.TRIGGER_AUTO_FANOUT_FALLBACK_LOG || "/Users/xujin/.agents/logs/fanout_weld_fallback.jsonl";
const FANOUT_TOOLS = new Set(["subagent", "subagent_fork"]);

// ===== v7 通道④：收编焊点 merge_weld_hook（块R，reform_gate 判A 块 merge_weld_20260822）=====
// settle 通知特征：用户态消息文本含 "Background subagent" + reported/finished
const SETTLE_PATTERN = /background subagent/i;
const SETTLE_VERB = /(reported|finished)/i;
const SETTLE_ID = /background subagent\s*[:`"']?\s*([\w-]+)/i;

function settleInfo(message) {
  const text = extractUserText(message);
  if (!SETTLE_PATTERN.test(text) || !SETTLE_VERB.test(text)) return null;
  const verb = text.match(SETTLE_VERB)?.[1]?.toLowerCase() ?? "settled";
  const subId = text.match(SETTLE_ID)?.[1] ?? "unknown";
  return { subId, verb };
}

function mergeWeldMessage(subId, verb) {
  return noticeMessage(
    `[MERGE-WELD] 分身 ${subId} 已 ${verb}。收编前必扳（判定禁止手写，照抄执行）：\n` +
    `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/shard_result_gate.json --set result=<该片落盘路径> 判 A\n` +
    `单片失败/取消弃该片不连坐，禁止连坐丢弃其他分身已落盘成果。`,
    `merge-weld: ${subId} ${verb}`
  );
}

// ===== v9 通道⑥：查询焊点 query_weld_hook（reform_gate 判A 块 query_weld_20260823）=====
// 检索三件套 read/grep/glob 的 pre-execute 硬焊：本 turn 首个检索动作前必须已有
// dual_gates declare 留痕（dual_gates_audit.jsonl 内 timestamp >= turnStart 的
// declaration_gate_start），无则 deny + 扳闸指引，扳完重试即穿透放行。
// 闸只强制"定性发生过"，不强制"必须是查询"——is_query/not_query 分流是 declare 的职权。
const DUAL_GATES_AUDIT = process.env.TRIGGER_AUTO_DUAL_GATES_AUDIT || "/Users/xujin/.agents/logs/dual_gates_audit.jsonl";
const QUERY_FALLBACK_LOG = process.env.TRIGGER_AUTO_QUERY_FALLBACK_LOG || "/Users/xujin/.agents/logs/query_weld_fallback.jsonl";
const QUERY_WINDOW_MS = 10 * 60 * 1000; // 无 turn 状态（插件中途加载）时的窗口兜底，同 fanout 口径
const QUERY_TOOLS = new Set(["read", "grep", "glob"]);

// ===== v8 通道⑤：todo_write 附身计划闸（块Q v3 修订增补，reform_gate 判A 块 plan_gate_weld_20260822）=====
const ATTACHED_PLAN_SCRIPT = "/Users/xujin/.agents/skills/gate-switch/scripts/attached_plan.py";const ATTACHED_PLAN_FALLBACK =
  "[ATTACHED-PLAN] 方案形成中：须生成 3 维度槽位候选池落盘 ~/.agents/logs/plan_select/POOL-<ts>.md 并扳 " +
  "python3 ~/.agents/skills/plan-select/scripts/plan_select.py --pool <池文件>；chosen 后必跟收益闸（reform_gate 判A才执行）。" +
  "单路径无选择须显式声明豁免理由。";

// 取 attached_plan.py 文案（进程内缓存；失败/超时用内嵌 fallback，恒不炸宿主——同附身脚本族 exit 0 纪律）
let attachedPlanTextCache = null;
function attachedPlanText() {
  if (attachedPlanTextCache) return Promise.resolve(attachedPlanTextCache);
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn("python3", [ATTACHED_PLAN_SCRIPT], { stdio: ["ignore", "pipe", "ignore"] });
    } catch {
      return resolve(ATTACHED_PLAN_FALLBACK);
    }
    let out = "";
    const timer = setTimeout(() => { try { child.kill("SIGKILL"); } catch {} resolve(ATTACHED_PLAN_FALLBACK); }, SCAN_TIMEOUT_MS);
    child.stdout.on("data", (c) => { out += c; });
    child.on("error", () => { clearTimeout(timer); resolve(ATTACHED_PLAN_FALLBACK); });
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out);
        if (typeof parsed?.declaration === "string" && parsed.declaration.length > 0) {
          attachedPlanTextCache = parsed.declaration;
          return resolve(attachedPlanTextCache);
        }
      } catch { /* fallthrough */ }
      resolve(ATTACHED_PLAN_FALLBACK);
    });
  });
}

// todo_write 清单机械 diff：返回新任务条目（content 归一化后不在快照内）；T1/T2 重发=快照全覆盖 → 空数组豁免
function newTodoItems(args, snapshot) {
  const todos = Array.isArray(args?.todos) ? args.todos : [];
  const contents = todos.map((t) => String(t?.content ?? "").trim()).filter(Boolean);
  return { contents, fresh: contents.filter((c) => !snapshot.has(c)) };
}

// 与 repeat-tool-reminder 同约：注入消息必须打 plugin 源标签，否则在派生历史里会被渲染成用户 prompt
const PLUGIN_SOURCE = { kind: "plugin", plugin: name };

function deepFreeze(value) {
  if (value && typeof value === "object") {
    for (const key of Object.keys(value)) deepFreeze(value[key]);
    Object.freeze(value);
  }
  return value;
}

// dsh-llm createUserMessage 的最小内联（linked 插件无法可靠解析 dsh 内部包，与 repeat-tool-reminder 同款内联策略）
function createUserMessage(input) {
  return deepFreeze({ ...input, role: "user", id: randomUUID() });
}

function noticeMessage(text, summary) {
  return createUserMessage({
    content: [{ type: "text", text }],
    source: { ...PLUGIN_SOURCE, form: "notice", summary },
  });
}

// 危险命令模式：rm / mv / cp -r(R) / find … -delete（词边界起步，防 rumor/moved 误命中）
const DANGER_PATTERN =
  /(?:^|[\s;&|()`](?:sudo\s+)?)(?:rm|mv)\s|(?:^|[\s;&|()`](?:sudo\s+)?)cp\s+(?:[^;&|]*\s)?-[a-zA-Z]*[rR]|\bfind\b[^;&|]*\s-delete\b/;

function extractCommand(exec) {
  const tool = String(exec?.name ?? "").toLowerCase();
  if (!tool.includes("bash")) return null;
  const args = exec?.arguments;
  if (typeof args === "string") {
    try {
      const parsed = JSON.parse(args);
      if (typeof parsed?.command === "string") return parsed.command;
    } catch {
      if (DANGER_PATTERN.test(args)) return args;
    }
    return null;
  }
  if (typeof args?.command === "string") return args.command;
  return null;
}

// 去重：gate_switch.jsonl 尾部 N 行内已有 danger_cmd_gate 扳动留痕 → 本会话已提醒过，静默
function dangerGateAlreadyPulled() {
  const lines = readLogTail(GATE_LOG);
  if (!lines) return false; // 日志不可读 = 无留痕，照常提醒（宁提醒勿漏）
  return lines.some((line) => line.includes("danger_cmd_gate.json"));
}

function dumpDangerCommand(command) {
  try {
    mkdirSync(DANGER_DIR, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    const file = `${DANGER_DIR}/trigger_auto_${ts}.txt`;
    appendFileSync(file, command + "\n");
    return file;
  } catch {
    return null;
  }
}

// 读 jsonl 尾部（16KB / 末 N 行），文件不可读返回 null
function readLogTail(file, tailLines = DEDUP_TAIL_LINES) {
  try {
    const size = statSync(file).size;
    const fd = openSync(file, "r");
    try {
      const len = Math.min(size, TAIL_READ_BYTES);
      const buf = Buffer.alloc(len);
      readSync(fd, buf, 0, len, size - len);
      return buf.toString("utf8").split("\n").filter(Boolean).slice(-tailLines);
    } finally {
      closeSync(fd);
    }
  } catch {
    return null;
  }
}

// 近窗口 dispatch_switch 扳动留痕的最新 verdict："A" | "B" | "OTHER" | null（无留痕/日志不可读）
// 口径：尾部行倒序取窗口内最新一条；CLARIFY/VIOLATION 不算过闸（OTHER）
function recentDispatchVerdict(now = Date.now()) {
  const lines = readLogTail(DISPATCH_LOG);
  if (!lines) return null;
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const row = JSON.parse(lines[i]);
      const ts = new Date(row.ts).getTime(); // ts 为本机 ISO（无 Z），Date 按本地时区解析
      if (Number.isNaN(ts) || now - ts > DISPATCH_WINDOW_MS || ts - now > 60_000) continue;
      if (row.verdict === "A") return "A";
      if (row.verdict === "B") return "B";
      return "OTHER";
    } catch { /* 坏行跳过 */ }
  }
  return null;
}

function fanoutFallbackTrace(why) {
  try {
    appendFileSync(FANOUT_FALLBACK_LOG, JSON.stringify({ ts: new Date().toISOString(), why }) + "\n");
  } catch { /* 留痕失败也静默 */ }
}

// 通道⑥留痕核验：dual_gates_audit.jsonl 尾部找 timestamp >= turnStart 的 declaration_gate_start
// （允许 5s 容差，防 pre-step 打点与 declare 写盘的毫秒级错位）；日志不可读 = 无留痕照章阻断
function declarePulledSince(turnStart) {
  const lines = readLogTail(DUAL_GATES_AUDIT, 80); // declare 一次写多行事件，尾部窗口放宽
  if (!lines) return false;
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      const row = JSON.parse(lines[i]);
      if (row.event !== "declaration_gate_start") continue;
      const ts = new Date(row.timestamp).getTime(); // dual_gates.py now_iso 带 +08:00 偏移，Date 正确解析
      if (Number.isNaN(ts)) continue;
      if (ts >= turnStart - 5_000) return true;
    } catch { /* 坏行跳过 */ }
  }
  return false;
}

function queryFallbackTrace(why) {
  try {
    appendFileSync(QUERY_FALLBACK_LOG, JSON.stringify({ ts: new Date().toISOString(), why }) + "\n");
  } catch { /* 留痕失败也静默 */ }
}

function dangerReminder(command) {
  const cmdfile = dumpDangerCommand(command);
  const text =
    `[TRIGGER-AUTO] 危险命令检测（v1 只提醒不阻断）\n` +
    `命中命令原文：${command}\n` +
    (cmdfile ? `命令原文已落盘：${cmdfile}\n` : `（命令原文落盘失败，请手动落盘后扳闸）\n`) +
    `必扳开关（判定禁止手写，照抄输出）：\n` +
    `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/danger_cmd_gate.json --set cmdfile=${cmdfile ?? "<落盘文件>"}\n` +
    `判 A 才执行、判 B 即阻断（确需执行须用户显式批准）。`;
  return noticeMessage(text, `danger-cmd: ${command.slice(0, 60)}`);
}

// ===== v2 调试面板（reform_gate 判A，块 trigger_debug_panel_20260822；纯输出层，不改触发判定）=====

// 信号真源（id → 信号定义），模块加载时读一次；读取失败降级为无提示词表面板
const SIGNALS_BY_ID = (() => {
  try {
    const data = JSON.parse(readFileSync(SIGNALS_JSON, "utf8"));
    const map = new Map();
    for (const sig of data?.signals ?? []) if (sig?.id) map.set(sig.id, sig);
    return map;
  } catch {
    return new Map();
  }
})();

// 信号 → 所属闸 spec 文件名：从 must_pull 文本提取第一个 xxx.json，提取失败如实标注
function specOf(hit) {
  const text = (hit?.must_pull ?? []).join(" ");
  const m = text.match(/[\w-]+\.json/);
  return m ? m[0] : "见 must_pull（未显式命名 spec）";
}

// regex → 人类可读提示词表：取每条正则的 (...) 交替组 split('|')，
// 滤掉仍含正则元字符/环视的残片，组内 "/" 连接、组间 " × " 连接；提取失败 fallback 原正则文本
const REGEX_META = /[\\^$.*+?[\]{}]/;
function readableAlternation(regex) {
  const groups = [];
  const re = /\(([^()]*)\)/g;
  let m;
  while ((m = re.exec(regex)) !== null) {
    const body = m[1];
    if (body.startsWith("?")) continue; // 环视/非捕获组等不参与词表
    const words = body
      .split("|")
      .map((w) => w.trim())
      .filter((w) => w.length > 0 && !REGEX_META.test(w));
    if (words.length > 0) groups.push(words);
  }
  return groups;
}

function promptTableOf(signalId, hit) {
  const sig = SIGNALS_BY_ID.get(signalId);
  const patterns = sig?.match ?? hit?.matched ?? [];
  if (sig?.match_mode === "keyword") return patterns.join(" / ");
  const allGroups = [];
  for (const pattern of patterns) {
    for (const group of readableAlternation(String(pattern))) {
      const merged = [...new Set(group)];
      if (merged.length) allGroups.push(merged);
    }
  }
  // 跨正则组子集去重：某组词集合是前组子集（同一信号多条正则的变体组）则丢弃，防面板重复近义组
  const kept = [];
  for (const group of allGroups) {
    const set = new Set(group);
    if (kept.some((prev) => group.every((w) => prev.has(w)))) continue;
    kept.push(set);
  }
  if (kept.length === 0) return patterns.join(" ; ") || "（词表提取失败，见信号真源）"; // fallback 原正则文本
  return kept.map((set) => [...set].join("/")).join(" × ");
}

// L1 成分命中判定（M3 通道预留）：hit 带 component 字段时归 L1，其余为 L0 硬命中
const isL1 = (h) => Array.isArray(h?.components) || Array.isArray(h?.matched_components);

// 声明块模板 v2：调试面板（设计 v3 第 4 点：声明闸不独立设闸，强制填充语义保留为机械投递）
function triggerDeclarationBlock(scan) {
  const hits = scan?.hits ?? [];
  const soft = scan?.soft_reminders ?? [];
  const l1Hits = hits.filter(isL1);
  const l0Hits = hits.filter((h) => !isL1(h));
  const lines = [];
  lines.push("[TRIGGER-AUTO 调试面板]");
  lines.push(`命中层位: 插件通道①(agent/pre-step→scan) ｜ L0硬命中:${l0Hits.length} ｜ L1成分:${l1Hits.length} ｜ L2软:${soft.length}`);
  for (const hit of hits) {
    lines.push(`├─ ${hit.id}（${hit.name}）→ 所属闸: ${specOf(hit)}`);
    lines.push(`│   命中词: ${(hit.matched ?? []).join(" ; ") || "（scan 未回传 matched）"}`);
    lines.push(`│   提示词表: ${promptTableOf(hit.id, hit)}`);
    if (isL1(hit)) {
      const arr = hit.components ?? hit.matched_components;
      lines.push(`│   L1 成分命中: ${hit.id} ← 成分数组 [${arr.join(",")}] 命中成分: ${(hit.matched_components ?? arr).join(",")}（准 must_pull 文案沿用）`);
    }
    for (const pull of hit.must_pull ?? []) lines.push(`│   must_pull: ${pull}`);
  }
  if (soft.length > 0) {
    lines.push(`├─ L2 软层提醒（keyword 不可判信号，留软层自查）: ${soft.map((s) => s.id).join(" / ")}`);
  }
  const ids = hits.map((hit) => hit.id).join(" ");
  lines.push(`└─ 逐条扳完 must_pull 后回复首行声明: [TRIGGER-AUTO-CLEARED] ${ids}`);
  return noticeMessage(lines.join("\n"), `trigger-hits: ${ids}`);
}

// v3 常显精简行（用户指令"调试板常显"：NO-HIT 静默导致长期不可见 → 未命中也注入一行在岗状态）
// 与完整面板互斥：HITS 走 triggerDeclarationBlock，非 HITS 走本行；扫描失败（null）仍静默
function compactStatusLine(scan) {
  const hits = scan?.hits ?? [];
  const l1Hits = hits.filter(isL1);
  const l0Count = hits.length - l1Hits.length;
  let text = `[TRIGGER-AUTO] 扫描在岗 ｜ L0硬:${l0Count} ｜ L1成分:${l1Hits.length} ｜ L2软:0 ｜ 未命中`;
  if (l1Hits.length > 0) {
    const detail = l1Hits
      .map((h) => `${h.id}(${(h.matched_components ?? h.components ?? []).join(",")})`)
      .join(" ");
    text += ` ｜ 成分命中: ${detail}`;
  }
  return noticeMessage(text, "scan-alive: no-hit");
}

// 同步等待扫描结果：超时 10s 强杀，任何失败静默返回 null（不拖垮主流程）
function runScan(text) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn("python3", [SCAN_SCRIPT, "--text", text], { stdio: ["ignore", "pipe", "ignore"] });
    } catch {
      return resolve(null);
    }
    let out = "";
    const timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      resolve(null);
    }, SCAN_TIMEOUT_MS);
    child.stdout.on("data", (chunk) => { out += chunk; });
    child.on("error", () => { clearTimeout(timer); resolve(null); });
    // NO-HIT 退出码为 2 但 stdout 仍是合法 JSON：close 时优先解析 stdout，带 verdict 即采信，否则按失败静默
    child.on("close", () => {
      clearTimeout(timer);
      try {
        const parsed = JSON.parse(out);
        if (parsed && typeof parsed.verdict === "string") return resolve(parsed);
      } catch { /* fallthrough */ }
      resolve(null);
    });
  });
}

function extractUserText(message) {
  const parts = [];
  for (const block of message?.content ?? []) {
    if (block?.type === "text" && typeof block.text === "string") parts.push(block.text);
  }
  return parts.join("\n").trim();
}

function apply(ctx) {
  // 每 agent 已扫描过的 user 消息 id（防同 turn 后续 step 重复扫描）；cap 64 防膨胀
  const seenByAgent = new WeakMap();
  // 通道③状态：每 agent 本 turn 分身扇出计数 + 首发待提醒标记（turn 边界=通道①检出新 user 消息时重置）
  const fanoutByAgent = new WeakMap();
  // 通道⑥状态：每 agent 本 turn 起点 turnStart（打点于通道①检出新 user 消息时，与通道③同一边界）
  const queryByAgent = new WeakMap();
  const NO_AGENT = Object.freeze({ id: "no-agent" }); // exec.agent 缺席时的哨兵键
  const fanoutState = (agent) => {
    const key = agent ?? NO_AGENT;
    let s = fanoutByAgent.get(key);
    if (!s) { s = { count: 0, remindPending: false }; fanoutByAgent.set(key, s); }
    return s;
  };

  // 通道①：agent/pre-step 检测新 user 消息 → 扫描 → HITS 注入声明块
  // 通道④：merge_weld_hook — 同链识别分身 settle 通知 → 注入收编义务块（同分身同次 settle 签名去重）
  const settleSeenByAgent = new WeakMap();
  ctx.on("agent/pre-step", async (payload, next) => {
    const { agent, messages } = payload ?? {};
    let reminder = null;
    let mergeReminder = null;
    try {
      // 通道④：settle 通知检测（签名=分身id:消息id 去重，同次 settle 只注一次）
      const settleMsg = [...(messages ?? [])].reverse().find((m) => settleInfo(m) !== null);
      if (settleMsg?.id) {
        const info = settleInfo(settleMsg);
        let seen = settleSeenByAgent.get(agent ?? NO_AGENT);
        if (!seen) { seen = new Set(); settleSeenByAgent.set(agent ?? NO_AGENT, seen); }
        const sig = `${info.subId}:${settleMsg.id}`;
        if (!seen.has(sig)) {
          seen.add(sig);
          if (seen.size > 64) seen.delete(seen.values().next().value);
          mergeReminder = mergeWeldMessage(info.subId, info.verb);
        }
      }
      const lastUser = [...(messages ?? [])].reverse().find((m) => m?.source?.kind === "user");
      if (lastUser?.id && lastUser.id !== settleMsg?.id) { // settle 通知不走 trigger 扫描（非用户诉求文本）
        let seen = seenByAgent.get(agent);
        if (!seen) { seen = new Set(); seenByAgent.set(agent, seen); }
        if (!seen.has(lastUser.id)) {
          seen.add(lastUser.id);
          if (seen.size > 64) seen.delete(seen.values().next().value);
          fanoutByAgent.delete(agent ?? NO_AGENT); queryByAgent.set(agent ?? NO_AGENT, { turnStart: Date.now() }); // 通道③ turn 边界：扇出计数清零；通道⑥：declare 留痕窗口起点
          const text = extractUserText(lastUser);
          if (text) {
            const scan = await runScan(text);
            if (scan?.verdict === "HITS" && Array.isArray(scan.hits) && scan.hits.length > 0) {
              reminder = triggerDeclarationBlock(scan); // HITS：完整调试面板
            } else if (scan && typeof scan.verdict === "string") {
              reminder = compactStatusLine(scan); // 非 HITS（NO-HIT/成分命中）：v3 常显精简行
            } // scan=null（失败/超时）保持静默
          }
        }
      }
    } catch { /* 静默：检测失败不阻断 pre-step */ }
    const decision = await next();
    const extra = [reminder, mergeReminder].filter(Boolean);
    if (extra.length === 0 || decision?.kind !== "enter") return decision;
    return { ...decision, messages: [...(decision.messages ?? []), ...extra] };
  });

  // 通道③：扇出焊点 fanout_weld_hook（块M）——pre-execute 拦 subagent/subagent_fork
  // 同 turn 第 1 个分身调用：放行 + 标记 post-execute 注入"先扳 dispatch_switch"提醒；
  // 第 2 个起：近 10 分钟 dispatch_switch 留痕 verdict=A → 穿透放行；verdict=B → deny（掷点B判串行）；
  //           无留痕/CLARIFY/VIOLATION → deny（先扳闸指引）；阻断器异常 → 降级放行+留痕（不拖垮主流程）
  ctx.on("tools/pre-execute", async (exec, next) => {
    try {
      const tool = String(exec?.name ?? "").toLowerCase();
      if (!FANOUT_TOOLS.has(tool)) return next();      const state = fanoutState(exec?.agent);
      state.count += 1;
      if (state.count === 1) {
        state.remindPending = true; // 首发放行，提醒走 post-execute（PreToolDecision 无 additionalContexts 槽）
        return next();
      }
      const verdict = recentDispatchVerdict();
      if (verdict === "A") return next();
      if (verdict === "B") {
        return {
          kind: "deny",
          reason:
            `[TRIGGER-AUTO] 扇出阻断（fanout_weld_hook）：近 10 分钟 dispatch_switch 留痕 verdict=B（掷点B=合法串行），` +
            `本就不该扇出——请按串行推进；确属并行误判请重新扳闸：\n` +
            `python3 ~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py --files <文件数> --units <无依赖单元数> --desc "<任务>"（判 A 再来）`,
        };
      }
      return {
        kind: "deny",
        reason:
          `[TRIGGER-AUTO] 扇出阻断（fanout_weld_hook）：同 turn 第 ${state.count} 个分身调用，近 10 分钟无 dispatch_switch 判A留痕` +
          (verdict === "OTHER" ? "（仅有 CLARIFY/VIOLATION 留痕，不算过闸）" : "") +
          `。并行闸机械判定优先于扇出（判定禁止手写，照抄执行）：\n` +
          `python3 ~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py --files <文件数> --units <无依赖单元数> --desc "<任务>"\n` +
          `判 A 后重试本调用即放行。`,
      };
    } catch (error) {
      fanoutFallbackTrace(`pre-execute 阻断器异常降级放行: ${String(error?.message ?? error)}`);
      return next();
    }
  });

  // 通道⑥：查询焊点 query_weld_hook（v9，reform_gate 判A 块 query_weld_20260823）——
  // pre-execute 拦检索三件套 read/grep/glob：本 turn 须有 dual_gates declare 定性留痕
  // （dual_gates_audit.jsonl 尾部 timestamp >= turnStart 的 declaration_gate_start，5s 容差）→ 穿透放行；
  // 无留痕 → deny + 扳闸指引（扳完重试即穿透）；无 turn 状态（插件中途加载）→ QUERY_WINDOW_MS 窗口兜底；
  // 阻断器异常 → queryFallbackTrace 留痕 + 降级放行（不拖垮主流程，同通道③口径）。
  // 闸只强制"定性发生过"，不强制"必须是查询"——is_query/not_query 分流是 declare 的职权。
  ctx.on("tools/pre-execute", async (exec, next) => {
    try {
      const tool = String(exec?.name ?? "").toLowerCase();
      if (!QUERY_TOOLS.has(tool)) return next();
      const state = queryByAgent.get(exec?.agent ?? NO_AGENT);
      const turnStart = state?.turnStart ?? Date.now() - QUERY_WINDOW_MS;
      if (declarePulledSince(turnStart)) return next();
      return {
        kind: "deny",
        reason:
          `[TRIGGER-AUTO] 检索阻断（query_weld_hook）：本 turn 尚无 dual_gates declare 定性留痕，` +
          `检索三件套（read/grep/glob）事前须先过声明闸（判定禁止手写，照抄执行）：\n` +
          `python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py declare --raw "<本turn用户原始诉求>" --session-id "$DSH_SESSION_ID"\n` +
          `is_query 续扳 query 闸；not_query 直接重试本调用即放行。`,
      };
    } catch (error) {
      queryFallbackTrace(`pre-execute 阻断器异常降级放行: ${String(error?.message ?? error)}`);
      return next();
    }
  });


  // 通道⑤：todo_write 附身计划闸（块Q v3 修订增补）——pre-execute 机械 diff 标记，post-execute 注入
  // （PreToolDecision 无 additionalContexts 槽，同 v6 首发提醒模式）；只提醒不阻断
  const planByAgent = new WeakMap();
  const planState = (agent) => {
    const key = agent ?? NO_AGENT;
    let s = planByAgent.get(key);
    if (!s) { s = { snapshot: new Set(), pending: false }; planByAgent.set(key, s); }
    return s;
  };
  ctx.on("tools/pre-execute", async (exec, next) => {
    try {
      if (String(exec?.name ?? "").toLowerCase() === "todo_write") {
        const state = planState(exec?.agent);
        const { contents, fresh } = newTodoItems(exec?.arguments, state.snapshot);
        if (fresh.length > 0) {
          state.snapshot = new Set(contents); // 快照升级为本清单全量
          state.pending = true;
        } // 全新条目为空 = T1/T2 重发/同内容重复提交 → 豁免不注入
      }
    } catch { /* 静默：标记失败不阻断 todo_write */ }
    return next();
  });

  // 实证 tools/pre-execute 为 waterfall，PreToolDecision = allow/deny(reason)/ask（dsh-tool-cordis:5407），
  // deny 物化为工具错误结果（dsh-tools:3116 reason→"Error: <reason>"），模型读指引扳闸后重试即放行。
  // 放行唯一条件：gate_switch.jsonl 尾部有 danger_cmd_gate 扳动留痕（同 post-execute 去重口径）。
  const deniedByAgent = new WeakMap(); // 已被阻断的命令签名（post-execute 不再重复提醒）
  ctx.on("tools/pre-execute", async (exec, next) => {
    try {
      const command = extractCommand(exec);
      if (command && DANGER_PATTERN.test(command) && !dangerGateAlreadyPulled()) {
        const cmdfile = dumpDangerCommand(command);
        let denied = deniedByAgent.get(exec?.agent);
        if (!denied) { denied = new Set(); if (exec?.agent) deniedByAgent.set(exec.agent, denied); }
        denied.add(command);
        if (denied.size > 32) denied.delete(denied.values().next().value);
        return {
          kind: "deny",
          reason:
            `[TRIGGER-AUTO] 危险命令事前阻断（v5，danger_cmd_gate 前置硬阻断）\n` +
            `命中命令原文：${command}\n` +
            (cmdfile ? `命令原文已落盘：${cmdfile}\n` : `（落盘失败，请手动落盘命令原文后扳闸）\n`) +
            `放行唯一通道（判定禁止手写，照抄执行）：\n` +
            `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/danger_cmd_gate.json --set cmdfile=${cmdfile ?? "<落盘文件>"}\n` +
            `判 A 后重试本命令即放行；判 B 维持阻断（确需执行须用户显式批准）。`,
        };
      }
    } catch { /* 静默：阻断器自身故障降级放行，不拖垮主流程 */ }
    return next();
  });

  // 通道②兜底：tools/post-execute 拦 bash 危险命令 → 落盘 + additionalContexts 注入提醒（去重）；
  // 已被 pre-execute 阻断的命令（deny 物化的错误结果也流经 post-execute）跳过提醒防双响。
  // 通道③首发提醒：同 turn 第 1 个分身调用执行后注入"先扳 dispatch_switch"提醒
  ctx.on("tools/post-execute", async (exec, _result, next) => {
    let reminder = null;
    try {
      const tool = String(exec?.name ?? "").toLowerCase();
      if (tool === "todo_write") {
        // 通道⑤：pre-execute 已 diff 出新任务条目 → 注入 [ATTACHED-PLAN] 义务块（一次性消费）
        const state = planByAgent.get(exec?.agent ?? NO_AGENT);
        if (state?.pending) {
          state.pending = false;
          reminder = noticeMessage(await attachedPlanText(), "attached-plan: todo_write 新清单");
        }
      } else if (FANOUT_TOOLS.has(tool)) {
        const state = fanoutByAgent.get(exec?.agent);
        if (state?.remindPending) {
          state.remindPending = false;
          reminder = noticeMessage(
            `[TRIGGER-AUTO] 分身扇出提醒（fanout_weld_hook）：本 turn 首个分身已放行；` +
            `同 turn 第 2 个 subagent/subagent_fork 调用起，须有 dispatch_switch 判A留痕（近 10 分钟），否则 pre-execute 阻断。` +
            `未扳请补扳：python3 ~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py --files <文件数> --units <无依赖单元数> --desc "<任务>"`,
            "fanout-first: remind dispatch_switch"
          );
        }
      } else {
        const command = extractCommand(exec);
        if (command && DANGER_PATTERN.test(command)) {
          const denied = deniedByAgent.get(exec?.agent);
          if (denied?.delete(command)) {
            // 本命令已被 pre-execute deny 并给了指引，post-execute 不再重复提醒
          } else if (!dangerGateAlreadyPulled()) {
            reminder = dangerReminder(command);
          }
        }
      }
    } catch { /* 静默 */ }
    const downstream = await next();
    if (!reminder) return downstream;
    if (downstream?.kind === "block") {
      return {
        kind: "block",
        feedback: downstream.feedback,
        additionalContexts: [reminder, ...(downstream.additionalContexts ?? [])],
      };
    }
    return { ...downstream, additionalContexts: [reminder, ...(downstream?.additionalContexts ?? [])] };
  });
}

export { apply, name, triggerDeclarationBlock, compactStatusLine };
