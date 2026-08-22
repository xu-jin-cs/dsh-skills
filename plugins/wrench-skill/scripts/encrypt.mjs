#!/usr/bin/env node
/**
 * wrench-skill 开发者侧加密打包工具（不随插件分发给小白用户的必需物，但开源可见）。
 *
 * 用法：
 *   node scripts/encrypt.mjs --manifest manifest.example.json --out assets/rules.enc.json
 *
 * 流程：
 *   1. 读取 manifest（技能清单：name/description/whenToUse/file）；
 *   2. 逐条读取技能 Markdown 正文，组装资产 bundle；
 *   3. 与插件运行时完全相同的链路派生密钥（Embedding Salt → HKDF → AES-256-GCM）；
 *   4. 加密写出密文资产包，并做一次解密 roundtrip 自检 + 明文泄露扫描。
 */

import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deriveSalt } from '../lib/embedding.mjs';
import { deriveKey, encryptBundle, decryptBundle, zeroize } from '../lib/crypto.mjs';
import { PAYLOAD_VERSION } from '../lib/constants.mjs';

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs(argv) {
  const args = { manifest: null, out: resolve(PLUGIN_ROOT, 'assets', 'rules.enc.json') };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === '--manifest') args.manifest = argv[++i];
    else if (argv[i] === '--out') args.out = argv[++i];
  }
  if (!args.manifest) {
    console.error('用法：node scripts/encrypt.mjs --manifest <清单.json> [--out <输出路径>]');
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

  // 1. 组装资产 bundle
  const skills = [];
  for (const entry of manifest.skills) {
    const filePath = resolve(dirname(manifestPath), entry.file);
    const content = await readFile(filePath, 'utf8');
    skills.push({
      name: entry.name,
      description: entry.description,
      whenToUse: entry.whenToUse,
      content,
      metadata: entry.metadata,
    });
    console.log(`  ✓ 收录技能 ${entry.name}（${content.length} 字符）`);
  }
  const bundle = { v: PAYLOAD_VERSION, generatedAt: new Date().toISOString(), skills };

  // 2. 与运行时一致的密钥派生链路
  console.log('→ 执行 Embedding 派生 Salt（首次运行需下载冻结模型，请保持网络畅通）…');
  const salt = await deriveSalt();
  const key = deriveKey(salt);
  zeroize(salt);

  // 3. 加密
  const payload = encryptBundle(key, bundle);
  const outPath = resolve(process.cwd(), args.out);
  await writeFile(outPath, JSON.stringify(payload, null, 2) + '\n', 'utf8');
  console.log(`→ 密文资产包已写出：${outPath}`);

  // 4. 自检一：解密 roundtrip
  const roundtrip = decryptBundle(key, payload);
  if (JSON.stringify(roundtrip.skills) !== JSON.stringify(skills)) {
    throw new Error('自检失败：解密 roundtrip 与原文不一致！');
  }
  zeroize(key);
  console.log('  ✓ 自检通过：解密 roundtrip 与原文一致');

  // 5. 自检二：明文泄露扫描（密文包中不得出现任何技能正文片段）
  const cipherText = JSON.stringify(payload);
  for (const s of skills) {
    const probe = s.content.replace(/\s+/g, '').slice(0, 32);
    if (probe && cipherText.includes(probe)) {
      throw new Error(`自检失败：密文包中检出技能 ${s.name} 的明文片段！`);
    }
  }
  console.log('  ✓ 自检通过：密文包未检出明文泄露');
  console.log(`完成：共加密 ${skills.length} 项技能 → ${outPath}`);
}

main().catch((err) => {
  console.error(`加密打包失败：${err?.message ?? err}`);
  process.exit(1);
});
