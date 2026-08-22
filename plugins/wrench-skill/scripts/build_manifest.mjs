#!/usr/bin/env node
/**
 * build_manifest.mjs — wrench-skill 真实资产清单生成器
 *
 * 收集用户私有资产并改写为可分发 bundle 清单（明文中间产物，加密由 encrypt.mjs 完成）：
 *   1. 规则 19 份   ~/.agents/rules/*.md                → skills[]（rule-<kebab>）
 *   2. 原子技能 7 个 ~/.agents/skills/<名>/SKILL.md      → skills[]
 *   3. 闸 spec       ~/.agents/skills/gate-switch/specs/*.json（仅顶层）→ specs{}
 *   4. 引擎规则      ~/agent-harness/backend/rules/*.yaml → engineRules{}（原文字符串）
 *
 * 全部文本内容执行调用路径重写（python3 本地路径 → ~/.dsh/bin/wrench-*）。
 * 输出：plugins/wrench-skill/manifest.real.json
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const HOME = os.homedir();
const RULES_DIR = path.join(HOME, '.agents/rules');
const SKILLS_DIR = path.join(HOME, '.agents/skills');
const SPECS_DIR = path.join(SKILLS_DIR, 'gate-switch/specs');
const ENGINE_RULES_DIR = path.join(HOME, 'agent-harness/backend/rules');
const PLUGIN_DIR = path.join(HOME, 'dsh-skills/plugins/wrench-skill');
const OUT_FILE = path.join(PLUGIN_DIR, 'manifest.real.json');

const ATOMIC_SKILLS = [
  'gate-switch', 'dual-gates', 'scope-boundary-gate', 'plan-select',
  'parallel-dispatch', 'bug-fix-strategy', 'idea-forge',
];

// ---------- 路径重写（优先级逐条替换） ----------
const stats = {
  rewriteHits: { gateSpecKnown: 0, gateSpecOther: 0, gateOtherScript: 0, stepSync: 0, skillRun: 0 },
  skillRunRefs: new Map(), // "<技能名>/<脚本>" → 次数
};

function bump(map, key) { map.set(key, (map.get(key) || 0) + 1); }

/** 对一段文本执行全部重写规则（按优先级逐条）。annotate=true 时（markdown 正文）对规则3追加行内注释标注。 */
function rewrite(text, { annotate = false } = {}) {
  let out = text;
  // R1
  out = out.replace(
    /(?:python3\s+)?~\/(?:\.agents|\.dsh)\/skills\/gate-switch\/scripts\/gate_switch\.py --spec ~\/(?:\.agents|\.dsh)\/skills\/gate-switch\/specs\/([A-Za-z0-9_-]+)\.json/g,
    (_m, name) => { stats.rewriteHits.gateSpecKnown++; return `~/.dsh/bin/wrench-gate ${name}`; }
  );
  // R2: gate_switch.py --spec <其他路径> → wrench-gate --spec-file <路径>
  out = out.replace(
    /(?:python3\s+)?~\/(?:\.agents|\.dsh)\/skills\/gate-switch\/scripts\/gate_switch\.py --spec ([^\s"'`)，]+)/g,
    (_m, p) => { stats.rewriteHits.gateSpecOther++; return `~/.dsh/bin/wrench-gate --spec-file ${p}`; }
  );
  // R3: gate-switch 其他脚本 → wrench-gate --script <脚本名>（markdown 中追加注释标注）
  out = out.replace(
    /(?:python3\s+)?~\/(?:\.agents|\.dsh)\/skills\/gate-switch\/scripts\/([A-Za-z0-9_.-]+\.py)/g,
    (_m, script) => {
      stats.rewriteHits.gateOtherScript++;
      const note = annotate ? `  # wrench-skill: 原 gate-switch/${script} 已内置插件` : '';
      return `~/.dsh/bin/wrench-gate --script ${script}${note}`;
    }
  );
  // R4: harness-step-sync.sh → wrench-engine step-sync（保留参数）
  out = out.replace(
    /bash ~\/agent-harness\/scripts\/harness-step-sync\.sh/g,
    () => { stats.rewriteHits.stepSync++; return '~/.dsh/bin/wrench-engine step-sync'; }
  );
  // R5: 其余技能 scripts/xxx.py → wrench-skill-run <技能名>/xxx.py
  out = out.replace(
    /(?:python3\s+)?~\/\.agents\/skills\/([A-Za-z0-9_-]+)\/scripts\/([A-Za-z0-9_.\/-]+\.py)/g,
    (_m, skill, script) => {
      stats.rewriteHits.skillRun++;
      bump(stats.skillRunRefs, `${skill}/${script}`);
      return `~/.dsh/bin/wrench-skill-run ${skill}/${script}`;
    }
  );
  return out;
}

/** 递归重写 JSON 值中的所有字符串 */
function rewriteJsonStrings(value) {
  if (typeof value === 'string') return rewrite(value, { annotate: false });
  if (Array.isArray(value)) return value.map(rewriteJsonStrings);
  if (value && typeof value === 'object') {
    const o = {};
    for (const [k, v] of Object.entries(value)) o[k] = rewriteJsonStrings(v);
    return o;
  }
  return value;
}

// ---------- frontmatter / 标题解析 ----------
function parseFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!m) return { data: {}, body: text };
  const data = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = line.match(/^([A-Za-z_]+):\s*(.*)$/);
    if (kv) data[kv[1]] = kv[2].trim().replace(/^["']|["']$/g, '');
  }
  return { data, body: text.slice(m[0].length) };
}

function firstHeading(text) {
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^#{1,6}\s+(.+?)\s*$/);
    if (m) return m[1];
  }
  return null;
}

function firstNonEmptyLine(text) {
  for (const line of text.split(/\r?\n/)) {
    const t = line.replace(/^#{1,6}\s+/, '').trim();
    if (t) return t;
  }
  return '';
}

// ---------- 1. 规则 19 份 ----------
const skills = [];
const ruleFiles = fs.readdirSync(RULES_DIR)
  .filter(f => f.endsWith('.md') && fs.statSync(path.join(RULES_DIR, f)).isFile())
  .sort();
for (const f of ruleFiles) {
  const full = path.join(RULES_DIR, f);
  const raw = fs.readFileSync(full, 'utf8');
  const kebab = f.replace(/\.md$/, '').replace(/_/g, '-');
  const desc = firstHeading(raw) || firstNonEmptyLine(raw) || kebab;
  skills.push({
    name: `rule-${kebab}`,
    description: desc,
    whenToUse: `规则集 ${f} 的适用场景`,
    content: rewrite(raw, { annotate: true }),
    metadata: { source: 'rule', sourcePath: full },
  });
}
console.log(`[1/4] 规则收集：${ruleFiles.length} 份 → skills（rule-* 前缀）`);

// ---------- 2. 原子技能 7 个 ----------
let skillCount = 0;
for (const name of ATOMIC_SKILLS) {
  const full = path.join(SKILLS_DIR, name, 'SKILL.md');
  if (!fs.existsSync(full)) { console.error(`  !! 缺失 ${full}`); continue; }
  const raw = fs.readFileSync(full, 'utf8');
  const { data, body } = parseFrontmatter(raw);
  const description = data.description || firstNonEmptyLine(body);
  const whenToUse = data.whenToUse || firstNonEmptyLine(body);
  skills.push({
    name,
    description,
    whenToUse,
    content: rewrite(body, { annotate: true }),
    metadata: { source: 'atomic-skill', sourcePath: full },
  });
  skillCount++;
}
console.log(`[2/4] 原子技能收集：${skillCount} 个`);

// ---------- 3. 闸 spec（仅顶层 .json，剔除 FastAPI 服务/本地 .sh 依赖规格） ----------
// 剔除清单（2026-08-22 用户裁定）：这些 spec 的检查项依赖 agent-harness FastAPI 服务
//（127.0.0.1:8001）或本机 .sh 脚本路径，小白机上必然空转，不进分发包。
const SPEC_EXCLUDE = new Set([
  'engine_health.json',          // FastAPI 服务在线体检（仅开发机 agent-harness 部署形态）
  'harness_sync.json',           // .sh 同步脚本依赖
  'archmap_diff_freshness.json', // agent-harness 路径依赖
  'backup_hygiene.json',         // agent-harness 路径依赖
  'engine_literal_scan.json',    // agent-harness 路径依赖
  'no_abs_path.json',            // agent-harness 路径 + .sh 依赖
  'security_baseline.json',      // agent-harness 路径 + .sh 依赖
  'statestore_wiring_diff.json', // agent-harness 路径依赖
  'retro_match_gate.json',       // .sh 脚本依赖
  'stat_citation.json',          // .sh 脚本依赖
]);
const specs = {};
const specFiles = fs.readdirSync(SPECS_DIR)
  .filter(f => f.endsWith('.json') && fs.statSync(path.join(SPECS_DIR, f)).isFile())
  .filter(f => !SPEC_EXCLUDE.has(f))
  .sort();
for (const f of specFiles) {
  const full = path.join(SPECS_DIR, f);
  const obj = JSON.parse(fs.readFileSync(full, 'utf8'));
  specs[f.replace(/\.json$/, '')] = rewriteJsonStrings(obj);
}
console.log(`[3/4] 闸 spec 收集：${specFiles.length} 份（剔除 FastAPI/.sh 依赖 ${SPEC_EXCLUDE.size} 份：${[...SPEC_EXCLUDE].map(f => f.replace('.json', '')).join('/')}）`);

// ---------- 4. 引擎规则 yaml（原文字符串，不改写） ----------
const engineRules = {};
let yamlCount = 0;
if (fs.existsSync(ENGINE_RULES_DIR)) {
  for (const f of fs.readdirSync(ENGINE_RULES_DIR).filter(f => f.endsWith('.yaml')).sort()) {
    const full = path.join(ENGINE_RULES_DIR, f);
    if (!fs.statSync(full).isFile()) continue;
    engineRules[f] = fs.readFileSync(full, 'utf8');
    yamlCount++;
  }
}
console.log(`[4/4] 引擎规则收集：${yamlCount} 份（${ENGINE_RULES_DIR}/*.yaml）`);

// ---------- 汇总输出 ----------
const manifest = { skills, specs, engineRules };
fs.writeFileSync(OUT_FILE, JSON.stringify(manifest, null, 2));
const totalHits = Object.values(stats.rewriteHits).reduce((a, b) => a + b, 0);
console.log(`路径重写命中：${totalHits} 处`, JSON.stringify(stats.rewriteHits));
console.log(`清单已写入：${OUT_FILE}`);

// ---------- 自测 ----------
const checks = [];
function check(label, ok, detail = '') {
  checks.push({ label, ok, detail });
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ' — ' + detail : ''}`);
}
console.log('自测：');
const parsed = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8'));
check('① manifest.real.json 可解析', !!parsed && typeof parsed === 'object');
check('② skills 数量 = 19+7 = 26', parsed.skills.length === 26, `实际 ${parsed.skills.length}`);
const specN = Object.keys(parsed.specs).length;
check('③ specs ≥ 80', specN >= 80, `实际 ${specN}`);
const allContent = parsed.skills.map(s => s.content).join('\n')
  + '\n' + JSON.stringify(parsed.specs) + '\n' + JSON.stringify(parsed.engineRules);
check('④ 不再出现 python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py',
  !allContent.includes('python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py'));
const sample = [parsed.skills[0], parsed.skills[19], parsed.skills[25]].filter(Boolean);
check('⑤ 抽样 3 条 skill 的 description 非空',
  sample.length === 3 && sample.every(s => s.description && s.description.trim().length > 0),
  sample.map(s => s.name).join(', '));

// ---------- 残留路径引用扫描（供报告） ----------
const residuals = new Map();
for (const m of allContent.matchAll(/~\/(?:\.agents|\.dsh)\/skills\/[^\s"'`)，。\\]+/g)) bump(residuals, m[0]);
for (const m of allContent.matchAll(/python3\s+~\/[^\s"'`)，。\\]+/g)) bump(residuals, m[0]);

const failed = checks.filter(c => !c.ok);
// 机器可读摘要写入 stdout 末尾，供调用方收集
console.log('SUMMARY ' + JSON.stringify({
  rules: ruleFiles.length, atomicSkills: skillCount, specs: specN, engineYaml: yamlCount,
  rewriteHits: stats.rewriteHits, totalHits,
  skillRunRefs: Object.fromEntries(stats.skillRunRefs),
  residuals: Object.fromEntries(residuals),
  checks: checks.map(c => ({ label: c.label, ok: c.ok, detail: c.detail })),
  outFile: OUT_FILE,
}));
process.exit(failed.length ? 1 : 0);
