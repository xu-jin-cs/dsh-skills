#!/usr/bin/env node
// Copyright (c) 2024-2026 xu-jin-cs
// Source-Available License
// Personal / internal non-public usage is permitted.
// Public forked redistribution and commercial service release are prohibited without written authorization.

/**
 * xujin-gate —— 扳闸 CLI（替代 python3 gate_switch.py 的插件内执行入口）。
 *
 * 用法：
 *   xujin-gate <spec名> [--set k=v ...]            # spec 从明文资产包读取（v3 起 Source-Available）
 *   xujin-gate --spec-file <路径> [--set k=v ...]  # 显式 spec 文件（调试用）
 *   xujin-gate --script <脚本.py> [args...]        # v1.5.0：执行 gate-switch 收割脚本（如 reform_layer_check.py）
 *
 * 退出码（与原 python 版一致）：0=A 放行 / 2=B 阻断 / 3=CLARIFY / 4=VIOLATION
 */

import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import os from 'node:os';
import { AssetStore } from '../lib/asset-store.mjs';
import { runGate } from '../lib/gate-engine.mjs';

const SCRIPTS_HOME = process.env.XUJIN_SCRIPTS_HOME || join(os.homedir(), '.dsh', 'xujin-scripts', 'skills');

const EXIT_CODES = { A: 0, B: 2, CLARIFY: 3, VIOLATION: 4 };

function parseArgs(argv) {
  const args = { specName: null, specFile: null, scriptName: null, scriptArgs: [], set: {} };
  const rest = argv.slice(2);
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--set' && rest[i + 1]) {
      const eq = rest[++i].indexOf('=');
      if (eq > 0) args.set[rest[i].slice(0, eq)] = rest[i].slice(eq + 1);
    } else if (rest[i] === '--spec-file') {
      args.specFile = rest[++i];
    } else if (rest[i] === '--script') {
      args.scriptName = rest[++i];
      args.scriptArgs = rest.slice(i + 1);
      break;
    } else if (!rest[i].startsWith('--') && !args.specName) {
      args.specName = rest[i];
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.scriptName) {
    // --script 通道：执行收割的 gate-switch 脚本（v1.5.0），透传参数与退出码
    const name = String(args.scriptName);
    if (!/^[A-Za-z0-9_.-]+\.py$/.test(name) || name.includes('..')) {
      console.error('[xujin-gate] --script 仅接受 <脚本名>.py（禁路径穿越）');
      process.exit(4);
    }
    const full = join(SCRIPTS_HOME, 'gate-switch', 'scripts', name);
    if (!existsSync(full)) {
      console.error(`[xujin-gate] 脚本不存在：${full}（请先安装/重装插件）`);
      process.exit(3);
    }
    const r = spawnSync('python3', [full, ...args.scriptArgs], { stdio: 'inherit' });
    if (r.error) {
      console.error(`[xujin-gate] python3 执行失败：${r.error.message}（--script 运行时需要系统 python3）`);
      process.exit(4);
    }
    process.exit(r.status ?? 4);
  }
  let spec;
  if (args.specFile) {
    spec = JSON.parse(await readFile(args.specFile, 'utf8'));
  } else if (args.specName) {
    const store = await AssetStore.load();
    spec = store.getSpec(args.specName);
    if (!spec) {
      console.error(`[xujin-gate] 资产包中不存在 spec：${args.specName}\n可用 spec 共 ${store.listSpecs().length} 份，示例：${store.listSpecs().slice(0, 8).join(' / ')} …`);
      process.exit(3);
    }
  } else {
    console.error('用法：xujin-gate <spec名> [--set k=v ...] ｜ xujin-gate --spec-file <路径> [--set k=v ...]');
    process.exit(3);
  }

  const result = await runGate(spec, args.set);
  console.log(JSON.stringify(result, null, 2));
  process.exit(EXIT_CODES[result.verdict] ?? 2);
}

main().catch((err) => {
  console.error(`[xujin-gate] 执行失败：${err?.message ?? err}`);
  process.exit(4);
});
