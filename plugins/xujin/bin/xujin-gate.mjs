#!/usr/bin/env node
// Copyright (c) 2024-2026 xu-jin-cs
// Source-Available License
// Personal / internal non-public usage is permitted.
// Public forked redistribution and commercial service release are prohibited without written authorization.

/**
 * xujin-gate —— 扳闸 CLI（替代 python3 gate_switch.py 的插件内执行入口）。
 *
 * 用法：
 *   xujin-gate <spec名> [--set k=v ...]            # spec 从加密资产内存解密
 *   xujin-gate --spec-file <路径> [--set k=v ...]  # 显式 spec 文件（调试用）
 *
 * 退出码（与原 python 版一致）：0=A 放行 / 2=B 阻断 / 3=CLARIFY / 4=VIOLATION
 */

import { readFile } from 'node:fs/promises';
import { AssetStore } from '../lib/asset-store.mjs';
import { runGate } from '../lib/gate-engine.mjs';

const EXIT_CODES = { A: 0, B: 2, CLARIFY: 3, VIOLATION: 4 };

function parseArgs(argv) {
  const args = { specName: null, specFile: null, set: {} };
  const rest = argv.slice(2);
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--set' && rest[i + 1]) {
      const eq = rest[++i].indexOf('=');
      if (eq > 0) args.set[rest[i].slice(0, eq)] = rest[i].slice(eq + 1);
    } else if (rest[i] === '--spec-file') {
      args.specFile = rest[++i];
    } else if (!rest[i].startsWith('--') && !args.specName) {
      args.specName = rest[i];
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
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
