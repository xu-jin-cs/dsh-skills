// Copyright (c) 2024-2026 xu-jin-cs
// Source-Available License
// Personal / internal non-public usage is permitted.
// Public forked redistribution and commercial service release are prohibited without written authorization.

/**
 * gate-engine.mjs — 通用概率执行门禁骨架（实证族 L2 引擎）Node.js 移植版
 *
 * 忠实移植自 ~/.agents/skills/gate-switch/scripts/gate_switch.py（214 行），
 * 零第三方依赖，仅用 node: 内置模块。
 *
 * 与 python 版差异（按移植契约）：
 *   - 输入为已解析的 spec 对象（宿主从加密资产内存解密后传入），不再是文件路径；
 *     占位符注入仍在「序列化后的原始文本」上进行，保持与 python 原版同语义。
 *   - 留痕：目录不存在则跳过不写、不报错（小白机无 ~/.agents/logs），
 *     python 原版是 makedirs 强制建目录——此处按契约改为静默跳过。
 *
 * 四态退出码（供 CLI 层映射）：
 *   0 = A（全部检查通过，放行）   2 = B（有违例，阻断）
 *   3 = CLARIFY（输入信号不足）   4 = VIOLATION（spec 本身非法）
 *
 * 检查原语（冻结集，与 python 版逐项对齐）：
 *   file_exists   {path}                                  文件/目录存在
 *   file_min_size {path, bytes}                           文件大小下限
 *   json_field    {path, field, op, value}                JSON 字段断言（a.b.0.c 点路径）
 *                 op: exists|not_empty|equals|in|min_len|min|max
 *   glob_count    {pattern, op: min|max|eq, value}        文件计数（自实现 recursive glob）
 *   grep_count    {pattern, path, op: min|max|eq, value}  正则命中行数计数（JS RegExp 逐行）
 *   mtime_after   {path, ref_path}                        产物新于参照
 *   script_exit   {cmd, expect}                           外部脚本退出码（sh 逐字执行 cmd）
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';

export const DEFAULT_LOG = path.join(os.homedir(), '.agents', 'logs', 'gate_switch.jsonl');

/** 四态退出码：A=0 / B=2 / CLARIFY=3 / VIOLATION=4 */
export const EXIT_CODES = { A: 0, B: 2, CLARIFY: 3, VIOLATION: 4 };

export class SpecError extends Error {}

/** 缺失哨兵（对应 python _MISS）。 */
const MISS = Symbol('MISS');

// ---------------------------------------------------------------------------
// 内部工具
// ---------------------------------------------------------------------------

/** 按 a.b.0.c 点路径取值，缺失返回 MISS（对齐 python _dig，含负索引）。 */
function dig(obj, dotted) {
  let cur = obj;
  for (const part of String(dotted).split('.')) {
    if (Array.isArray(cur)) {
      const idx = Number(part);
      if (!Number.isInteger(idx) || idx >= cur.length || idx < -cur.length) return MISS;
      cur = cur[idx < 0 ? cur.length + idx : idx];
    } else if (cur !== null && typeof cur === 'object' &&
               Object.prototype.hasOwnProperty.call(cur, part)) {
      cur = cur[part];
    } else {
      return MISS;
    }
  }
  return cur;
}

/** python == 语义（JSON 值域内深比较）。 */
function pyEquals(a, b) {
  if (a === MISS || b === MISS) return false;
  if (a === b) return true;
  if (typeof a !== typeof b) {
    // python True == 1；JSON 场景从 spec 来的布尔/数字对齐此语义
    if (typeof a === 'boolean' && typeof b === 'number') return Number(a) === b;
    if (typeof a === 'number' && typeof b === 'boolean') return a === Number(b);
    return false;
  }
  if (a !== null && b !== null && typeof a === 'object') {
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    if (Array.isArray(a)) {
      return a.length === b.length && a.every((v, i) => pyEquals(v, b[i]));
    }
    const ka = Object.keys(a), kb = Object.keys(b);
    return ka.length === kb.length && ka.every(k => pyEquals(a[k], b[k]));
  }
  return false;
}

function isEmptyValue(v) {
  if (v === null) return true;
  if (v === '') return true;
  if (Array.isArray(v)) return v.length === 0;
  if (v !== null && typeof v === 'object') return Object.keys(v).length === 0;
  return false;
}

/** python len() 语义；不可计长返回 null。 */
function lenOf(v) {
  if (typeof v === 'string' || Array.isArray(v)) return v.length;
  if (v !== null && typeof v === 'object') return Object.keys(v).length;
  return null;
}

/** python repr 近似（仅用于 detail 文案，不影响判定）。 */
function pyRepr(v) {
  if (v === MISS) return '<MISS>';
  if (v === undefined) return 'None';
  if (v === null) return 'None';
  if (v === true) return 'True';
  if (v === false) return 'False';
  if (typeof v === 'string') return `'${v}'`;
  return JSON.stringify(v);
}

/** 对齐 python _cmp。未知 op 抛 SpecError → VIOLATION。 */
function cmp(op, actual, value) {
  switch (op) {
    case 'exists': return actual !== MISS;
    case 'not_empty': return actual !== MISS && !isEmptyValue(actual);
    case 'equals': return pyEquals(actual, value);
    case 'in':
      if (Array.isArray(value)) return value.some(v => pyEquals(v, actual));
      if (typeof value === 'string' && typeof actual === 'string') return value.includes(actual);
      throw new TypeError(`argument of type '${typeof value}' is not iterable`);
    case 'min_len': { const n = lenOf(actual); return n !== null && n >= value; }
    case 'min': return typeof actual === 'number' && actual >= value;
    case 'max': return typeof actual === 'number' && actual <= value;
    case 'eq': return pyEquals(actual, value);
    default: throw new SpecError(`未知比较符: ${op}`);
  }
}

// ---------------------------------------------------------------------------
// 自实现 recursive glob（对齐 python glob.glob(pattern, recursive=True) 语义子集：
// 支持 * ? [...] **；* 不匹配段首隐藏文件（段模式以 . 开头除外）；** 不进隐藏目录）
// ---------------------------------------------------------------------------

const HAS_GLOB = /[*?[]/;

function segmentRegex(seg) {
  let re = '';
  for (let i = 0; i < seg.length; i++) {
    const ch = seg[i];
    if (ch === '*') { re += '[^/]*'; continue; }
    if (ch === '?') { re += '[^/]'; continue; }
    if (ch === '[') {
      const j = seg.indexOf(']', i + 1);
      if (j === -1) { re += '\\['; continue; }
      let cls = seg.slice(i + 1, j);
      if (cls.startsWith('!')) cls = '^' + cls.slice(1);
      re += '[' + cls.replace(/\\/g, '\\\\') + ']';
      i = j;
      continue;
    }
    re += ch.replace(/[.+^${}()|\\]/g, '\\$&');
  }
  return new RegExp('^' + re + '$');
}

function joinPath(dir, name) {
  return dir === '/' ? '/' + name : dir === '.' ? name : dir + '/' + name;
}

/** 同步 glob，返回匹配路径数组（文件与目录都算，对齐 python glob）。 */
export function globSync(pattern) {
  const isAbs = pattern.startsWith('/');
  const segs = pattern.split('/');
  if (isAbs) segs.shift(); // 去掉前导空段
  const results = [];

  if (!segs.some(s => HAS_GLOB.test(s))) {
    const p = (isAbs ? '/' : '') + segs.join('/');
    if (fs.existsSync(p)) results.push(p);
    return results;
  }

  function walk(dir, i) {
    if (i === segs.length) { results.push(dir); return; }
    const seg = segs[i];
    if (seg === '**') {
      walk(dir, i + 1); // 匹配零层目录
      let entries;
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        if (e.name.startsWith('.')) continue; // python ** 不递归隐藏目录
        if (e.isDirectory()) walk(joinPath(dir, e.name), i);
      }
      return;
    }
    if (HAS_GLOB.test(seg)) {
      const re = segmentRegex(seg);
      let entries;
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of entries) {
        if (!seg.startsWith('.') && e.name.startsWith('.')) continue; // python 隐藏文件语义
        if (!re.test(e.name)) continue;
        const p = joinPath(dir, e.name);
        if (i === segs.length - 1) results.push(p);
        else if (e.isDirectory()) walk(p, i + 1);
      }
      return;
    }
    // 字面段
    const p = joinPath(dir, seg);
    if (i === segs.length - 1) {
      if (fs.existsSync(p)) results.push(p);
    } else {
      try { if (fs.statSync(p).isDirectory()) walk(p, i + 1); } catch { /* 不存在即无匹配 */ }
    }
  }

  walk(isAbs ? '/' : '.', 0);
  return results;
}

// ---------------------------------------------------------------------------
// 检查原语（与 python run_check 逐项对齐）
// ---------------------------------------------------------------------------

/** 必填字段校验：缺失即抛 TypeError（对齐 python c["path"] KeyError → VIOLATION）。 */
function req(c, ...fields) {
  for (const f of fields) {
    if (c[f] === undefined || c[f] === null) {
      throw new TypeError(`检查项字段缺失: '${f}'`);
    }
  }
}

/** 执行单条检查，返回 {ok, detail}。未知类型抛 SpecError；字段缺失抛 TypeError。 */
export function runCheck(c) {
  const t = c.type;
  const label = c.label ?? t;

  if (t === 'file_exists') {
    req(c, 'path');
    const ok = fs.existsSync(c.path);
    return { ok, detail: `${label}: ${c.path} ${ok ? '存在' : '不存在'}` };
  }

  if (t === 'file_min_size') {
    req(c, 'path', 'bytes');
    if (!fs.existsSync(c.path) || !fs.statSync(c.path).isFile()) {
      return { ok: false, detail: `${label}: ${c.path} 不存在` };
    }
    const size = fs.statSync(c.path).size;
    return { ok: size >= c.bytes, detail: `${label}: ${size}B（下限 ${c.bytes}B）` };
  }

  if (t === 'json_field') {
    req(c, 'path', 'field', 'op');
    if (!fs.existsSync(c.path) || !fs.statSync(c.path).isFile()) {
      return { ok: false, detail: `${label}: ${c.path} 不存在` };
    }
    let data;
    try {
      data = JSON.parse(fs.readFileSync(c.path, 'utf8'));
    } catch (e) {
      return { ok: false, detail: `${label}: JSON 解析失败 ${e.message}` };
    }
    const actual = dig(data, c.field);
    const ok = cmp(c.op, actual, c.value);
    return { ok, detail: `${label}: ${c.field}=${pyRepr(actual)} op=${c.op} expect=${pyRepr(c.value)}` };
  }

  if (t === 'glob_count') {
    req(c, 'pattern', 'op', 'value');
    const n = globSync(c.pattern).length;
    return { ok: cmp(c.op, n, c.value), detail: `${label}: 计数=${n} op=${c.op} expect=${c.value}` };
  }

  if (t === 'grep_count') {
    req(c, 'pattern', 'path', 'op', 'value');
    const re = new RegExp(c.pattern);
    let n = 0;
    for (const p of globSync(c.path)) {
      let st;
      try { st = fs.statSync(p); } catch { continue; }
      if (!st.isFile()) continue;
      const text = fs.readFileSync(p, 'utf8'); // 非法字节 → U+FFFD，对齐 errors="ignore" 的容错语义
      for (const line of text.split(/\r\n|\r|\n/)) {
        if (re.test(line)) n++;
      }
    }
    return { ok: cmp(c.op, n, c.value), detail: `${label}: 命中=${n} op=${c.op} expect=${c.value}` };
  }

  if (t === 'mtime_after') {
    req(c, 'path', 'ref_path');
    if (!fs.existsSync(c.path)) {
      return { ok: false, detail: `${label}: ${c.path} 不存在` };
    }
    if (!fs.existsSync(c.ref_path)) {
      return { ok: false, detail: `${label}: 参照 ${c.ref_path} 不存在` };
    }
    const ok = fs.statSync(c.path).mtimeMs > fs.statSync(c.ref_path).mtimeMs;
    return { ok, detail: `${label}: 产物${ok ? '新于' : '不新于'}参照` };
  }

  if (t === 'script_exit') {
    req(c, 'cmd');
    // 对齐 python subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
    const r = spawnSync(c.cmd, {
      shell: true,
      timeout: 300_000,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    });
    const expect = c.expect ?? 0;
    const code = r.status === null ? -1 : r.status; // 超时/信号 → 必不等于 expect
    const ok = code === expect;
    const out = (r.stdout ? r.stdout : (r.stderr || '')).trim();
    const lines = out ? out.split(/\r\n|\r|\n/) : [];
    const tail = lines.length ? lines[lines.length - 1] : '';
    return { ok, detail: `${label}: exit=${code} expect=${expect} ${tail}` };
  }

  throw new SpecError(`未知检查类型: ${t}`);
}

// ---------------------------------------------------------------------------
// 留痕（契约 §4：目录不存在则跳过不写，不报错）
// ---------------------------------------------------------------------------

function isoLocalSeconds(d) {
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** 追加留痕；目录不存在静默跳过。返回实际写入路径或 null。 */
export function appendLog(logPath, entry) {
  if (!logPath) return null;
  const dir = path.dirname(logPath);
  if (!fs.existsSync(dir)) return null; // 小白机无此目录：跳过不写，不报错
  try {
    fs.appendFileSync(logPath, JSON.stringify(entry) + '\n', 'utf8');
    return logPath;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// 核心入口
// ---------------------------------------------------------------------------

/**
 * 扳动门禁。
 * @param {object} specObject 已解析的 spec 对象（宿主从加密资产解密后传入，非文件路径）
 * @param {Record<string,string>} setVars 占位符注入（对应原版 --set key=value）
 * @param {object} [options]
 * @param {string|null} [options.log] 留痕 jsonl 路径；默认 ~/.agents/logs/gate_switch.jsonl；
 *                                    传 null 关闭留痕；目录不存在静默跳过。
 * @param {string} [options.specName] 留痕 entry.spec 字段（原版记 spec 文件路径）
 * @returns 结果对象：
 *   A: {verdict:'A', throw:'A', gate, passed[], failed:[], directive, exitCode:0, logged}
 *   B: {verdict:'B', throw:'B', gate, violations[], failed[], passed[], directive, exitCode:2, logged}
 *   CLARIFY:   {verdict:'CLARIFY', reasons[], exitCode:3, logged}
 *   VIOLATION: {verdict:'VIOLATION', reasons[], exitCode:4, logged}
 *   （failed 与 violations 为同一数组引用：failed 是移植契约字段名，violations 保留 python 同构名）
 */
export function runGate(specObject, setVars = {}, options = {}) {
  const logPath = Object.prototype.hasOwnProperty.call(options, 'log') ? options.log : DEFAULT_LOG;

  let result;
  let spec = null;

  // 占位符注入：在序列化后的原始文本上进行（对齐 python 对 spec 原文做 str.replace 的语义）
  try {
    if (specObject === null || specObject === undefined) {
      throw new Error('spec 为空');
    }
    let raw = JSON.stringify(specObject);
    for (const [k, v] of Object.entries(setVars)) {
      raw = raw.split(`{${k}}`).join(String(v));
    }
    const unresolved = raw.match(/\{[a-zA-Z_][a-zA-Z0-9_]*\}/g);
    if (unresolved) {
      result = { verdict: 'CLARIFY',
                 reasons: [`spec 存在未注入占位符 ${JSON.stringify(unresolved)}，用 setVars 补齐`] };
    } else {
      spec = JSON.parse(raw);
    }
  } catch (e) {
    result = { verdict: 'CLARIFY', reasons: [`spec 解析失败: ${e.message}`] };
  }

  if (!result) {
    const checks = spec.checks;
    if (!Array.isArray(checks) || checks.length === 0) {
      result = { verdict: 'CLARIFY', reasons: ['spec 无 checks 检查项'] };
    } else {
      const violations = [];
      const passed = [];
      try {
        for (const c of checks) {
          const { ok, detail } = runCheck(c);
          (ok ? passed : violations).push(detail);
        }
      } catch (e) {
        if (e instanceof SpecError) {
          result = { verdict: 'VIOLATION', reasons: [e.message] };
        } else if (e instanceof TypeError) {
          result = { verdict: 'VIOLATION', reasons: [`检查项字段缺失/类型错误: ${e.message}`] };
        } else {
          throw e;
        }
      }
      if (!result) {
        if (violations.length === 0) {
          result = { verdict: 'A', throw: 'A', gate: spec.gate,
                     passed, failed: [],
                     directive: '全部机械核验通过，照抄本结论放行' };
        } else {
          result = { verdict: 'B', throw: 'B', gate: spec.gate,
                     violations, failed: violations, passed,
                     directive: '存在违例，阻断；violations 即 B 档理由，修复后重新扳动' };
        }
      }
    }
  }

  result.exitCode = EXIT_CODES[result.verdict];

  // 留痕（与 python 同 entry 结构；spec 字段因无文件路径，记 specName 或 gate 名）
  const entry = {
    ts: isoLocalSeconds(new Date()),
    spec: options.specName ?? (spec && spec.gate) ?? null,
    bindings: Object.keys(setVars).length ? setVars : null,
    verdict: result.verdict,
    violations: result.violations ?? null,
  };
  result.logged = appendLog(logPath, entry);

  return result;
}

export default { runGate, runCheck, globSync, appendLog, SpecError, EXIT_CODES, DEFAULT_LOG };
