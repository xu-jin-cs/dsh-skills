#!/usr/bin/env node
/**
 * wrench-engine —— 引擎机制内核 CLI（签发/验签/状态同步/et 执行，插件内执行，无数据库）。
 *
 * 用法：
 *   wrench-engine sign --artifact <json|@文件> [--trace-id <id>] [--state-meta <json>] [--algo sha256|hmac-sha256]
 *   wrench-engine verify --artifact <json|@文件> --signature <sig> --trace-id <id> [--state-meta <json>] [--algo ...]
 *   wrench-engine step-sync <项目> <阶段> [说明] [角色] [--transitions <json|@文件>] [--initial-state <态>]
 *   wrench-engine et <payload.json|@文件>
 *
 * hmac-sha256 密钥只从环境变量 AGENT_ENGINE_SECRET 读取（与原 python 内核一致，无内置回落）。
 * 内核不写死业务规则：step-sync 的合法跃迁表须由 --transitions 注入（如 '{"INIT":["DEV"],"DEV":["DONE"]}'），
 * 未注入时按内核语义 block 并给出中文原因。
 */

import { readFile } from 'node:fs/promises';
import { computeSignature, verifySignature, stepSync, et } from '../lib/engine-kernel.mjs';

async function readJsonArg(v) {
  if (v?.startsWith('@')) return JSON.parse(await readFile(v.slice(1), 'utf8'));
  return JSON.parse(v);
}

function flag(argv, name) {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
}

async function main() {
  const [, , cmd, ...rest] = process.argv;
  let out;
  switch (cmd) {
    case 'sign': {
      const traceId = flag(rest, '--trace-id') ?? `cli-${Date.now()}`;
      const artifact = await readJsonArg(flag(rest, '--artifact') ?? rest[0]);
      const stateMeta = flag(rest, '--state-meta') ? await readJsonArg(flag(rest, '--state-meta')) : null;
      const algo = flag(rest, '--algo') ?? 'sha256';
      out = { trace_id: traceId, algo, signature: computeSignature(artifact, traceId, stateMeta, algo) };
      break;
    }
    case 'verify': {
      const traceId = flag(rest, '--trace-id');
      const artifact = await readJsonArg(flag(rest, '--artifact') ?? rest[0]);
      const stateMeta = flag(rest, '--state-meta') ? await readJsonArg(flag(rest, '--state-meta')) : null;
      const algo = flag(rest, '--algo') ?? 'sha256';
      const issueMeta = { signature: flag(rest, '--signature'), algo };
      out = { valid: verifySignature(artifact, issueMeta, traceId, stateMeta) };
      break;
    }
    case 'step-sync': {
      // 先剥离 --flag value 对，剩余为位置参数
      const FLAG_WITH_VALUE = new Set(['--transitions', '--initial-state']);
      const positional = [];
      for (let i = 0; i < rest.length; i++) {
        if (FLAG_WITH_VALUE.has(rest[i])) { i++; continue; }
        positional.push(rest[i]);
      }
      const [project, stage, desc, role] = positional;
      if (!project || !stage) {
        console.error('用法：wrench-engine step-sync <项目> <阶段> [说明] [角色] [--transitions <json|@文件>] [--initial-state <态>]');
        process.exit(3);
      }
      const transitions = flag(rest, '--transitions') ? await readJsonArg(flag(rest, '--transitions')) : undefined;
      const initialState = flag(rest, '--initial-state');
      out = await stepSync(project, stage, { stepTitle: desc ?? stage, operator: role ?? 'cli', transitions, initialState });
      break;
    }
    case 'et': {
      const payload = await readJsonArg(rest[0]);
      out = await et(payload);
      break;
    }
    default:
      console.error('用法：wrench-engine <sign|verify|step-sync|et> …（见文件头注释）');
      process.exit(3);
  }
  console.log(JSON.stringify(out, null, 2));
}

main().catch((err) => {
  console.error(`[wrench-engine] 执行失败：${err?.message ?? err}`);
  process.exit(1);
});
