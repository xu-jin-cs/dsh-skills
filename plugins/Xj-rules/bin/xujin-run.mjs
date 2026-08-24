// Copyright (c) 2024-2026 xu-jin-cs
// Source-Available License
// Personal / internal non-public usage is permitted.
// Public forked redistribution and commercial service release are prohibited without written authorization.

/**
 * xujin-run —— 技能脚本执行入口（v1.5.0 新增，脚本实体随包 payload/skill-scripts/）。
 *
 * 用法：
 *   xujin-run <skill>/<script> [args...]
 *   示例：xujin-run parallel-dispatch/dispatch_switch.py --files 2 --units 1 --desc "任务"
 *
 * 行为：从 ~/.dsh/xujin-scripts/skills/<skill>/scripts/<script> 以系统 python3 执行，
 * 透传全部参数与退出码（0=A / 2=B / 3=CLARIFY / 4=VIOLATION 语义由脚本自身决定）。
 */

import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import os from 'node:os';

const HOME = os.homedir();
const SCRIPTS_HOME = process.env.XUJIN_SCRIPTS_HOME || join(HOME, '.dsh', 'xujin-scripts', 'skills');

function main() {
  const arg = process.argv[2];
  const m = arg && arg.match(/^([A-Za-z0-9_-]+)\/([A-Za-z0-9_.\/-]+\.py)$/);
  if (!m) {
    console.error('用法：xujin-run <skill>/<script.py> [args...]');
    process.exit(3);
  }
  const [, skill, script] = m;
  if (script.includes('..')) {
    console.error('[xujin-run] 非法脚本路径（禁路径穿越）');
    process.exit(4);
  }
  const full = join(SCRIPTS_HOME, skill, 'scripts', script);
  if (!existsSync(full)) {
    let available = [];
    try { available = readdirSync(SCRIPTS_HOME); } catch { /* 忽略 */ }
    console.error(`[xujin-run] 脚本不存在：${full}\n已安装技能脚本目录：${available.join(' / ') || '（空——请先安装/重装插件）'}`);
    process.exit(3);
  }
  const r = spawnSync('python3', [full, ...process.argv.slice(3)], { stdio: 'inherit' });
  if (r.error) {
    console.error(`[xujin-run] python3 执行失败：${r.error.message}（技能脚本运行时需要系统 python3）`);
    process.exit(4);
  }
  process.exit(r.status ?? 4);
}

main();
