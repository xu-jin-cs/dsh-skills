#!/usr/bin/env node
// Copyright (c) 2024-2026 xu-jin-cs
// Source-Available License
// Personal / internal non-public usage is permitted.
// Public forked redistribution and commercial service release are prohibited without written authorization.

/**
 * build_assets.mjs — xujin 明文资产打包器（Source-Available 分发，2026-08-23 用户裁定替代加密分发）
 *
 * 用法：
 *   node scripts/build_assets.mjs --manifest manifest.real.json [--out assets/rules.json]
 *
 * 流程：
 *   1. 读取 manifest（skills + specs + engineRules + engineDefaults）；
 *   2. 逐条读取技能正文，组装资产 bundle（结构与加密批次一致，运行时零改动）；
 *   3. 明文写出 assets/rules.json 并自检（可解析 / skills 非空 / 正文抽检非空）。
 *
 * 与退役的 encrypt.mjs 差异：无密钥派生、无加密、无明文泄露扫描——明文即本意（Source-Available）。
 */

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BUNDLE_VERSION = 3; // v3 = Source-Available 明文批次（v2 = AES-256-GCM 加密批次，已退役）

function parseArgs(argv) {
  const args = { manifest: null, out: resolve(PLUGIN_ROOT, 'assets', 'rules.json') };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--manifest') args.manifest = argv[++i];
    else if (argv[i] === '--out') args.out = argv[++i];
  }
  if (!args.manifest) {
    console.error('用法：node scripts/build_assets.mjs --manifest <清单.json> [--out <输出路径>]');
    process.exit(2);
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
  const manifestPath = resolve(process.cwd(), args.manifest);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  if (!Array.isArray(manifest.skills) || manifest.skills.length === 0) {
    throw new Error('manifest 格式错误：skills 必须是非空数组。');
  }

  // 1. 组装资产 bundle（skills 支持 file 引用或 content 内联；specs/engineRules/engineDefaults 透传）
  const skills = [];
  for (const entry of manifest.skills) {
    const content = entry.content ?? await readFile(resolve(dirname(manifestPath), entry.file), 'utf8');
    const metadata = entry.metadata ? { ...entry.metadata } : undefined;
    if (metadata) delete metadata.sourcePath; // 脱敏：剔除本机绝对路径元数据
    skills.push({ name: entry.name, description: entry.description, whenToUse: entry.whenToUse, content, metadata });
    console.log(`  ✓ 收录技能 ${entry.name}（${content.length} 字符）`);
  }
  const bundle = {
    v: BUNDLE_VERSION,
    distribution: 'source-available',
    generatedAt: new Date().toISOString(),
    skills,
    specs: manifest.specs ?? {},
    engineRules: manifest.engineRules ?? {},
    engineDefaults: manifest.engineDefaults ?? {},
  };
  console.log(`  ✓ 收录闸 spec ${Object.keys(bundle.specs).length} 份 / 引擎规则 ${Object.keys(bundle.engineRules).length} 份`);

  // 2. 明文写出
  const outPath = resolve(process.cwd(), args.out);
  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(outPath, JSON.stringify(bundle, null, 2) + '\n', 'utf8');
  console.log(`→ 明文资产包已写出：${outPath}`);

  // 3. 自检：回读可解析 + skills 非空 + 正文抽检
  const parsed = JSON.parse(await readFile(outPath, 'utf8'));
  if (!Array.isArray(parsed.skills) || parsed.skills.length === 0) throw new Error('自检失败：回读 skills 为空');
  for (const s of parsed.skills.slice(0, 3)) {
    if (typeof s.content !== 'string' || s.content.length < 50) throw new Error(`自检失败：技能 ${s.name} 正文异常`);
  }
  console.log(`  ✓ 自检通过：明文可解析，${parsed.skills.length} 项技能正文完整`);
  console.log(`完成：共打包 ${parsed.skills.length} 项技能 → ${outPath}`);
}

main().catch((err) => {
  console.error(`打包失败：${err?.message ?? err}`);
  process.exit(1);
});
