/**
 * wrench-skill —— DSH Cordis 私有 Skill/规则插件（内置种子二道混淆加密分发，开源小白友好版）。
 *
 * 定位：非独立 Agent、非完整工作流；仅向 DeepSeek Harness 引擎提供
 * 可被模型/用户调用的校验规则与原子 Skill 能力。
 *
 * 加载链路（全自动，零密钥零配置、零模型依赖）：
 *   读取 assets/rules.enc.json 密文资产
 *   → 内置种子 + 内置 Embedding 派生 Salt 常量（开发期由本地 BGE-M3 离线派生）
 *   → HKDF-SHA256 派生 AES-256-GCM 工作密钥（见 lib/crypto.mjs）
 *   → 内存解密 → ctx.skills.register 以 runtime 源注册 Skill/规则
 *   → 明文仅驻留内存，不落地任何文件；插件卸载时自动清空密钥与明文缓存。
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { deriveKey, decryptBundle, zeroize, DecryptError } from './crypto.mjs';

export const name = 'wrench-skill';

/** 声明服务依赖：skill 注册表（dsh-skill）。 */
export const inject = ['skills'];

const ASSET_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'rules.enc.json');

const KEBAB_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function validateSkill(entry, index) {
  if (!entry || typeof entry !== 'object') return `第 ${index + 1} 条技能不是有效对象`;
  if (!KEBAB_RE.test(entry.name ?? '')) return `第 ${index + 1} 条技能名称非法（需 kebab-case）：${entry.name}`;
  if (typeof entry.description !== 'string' || !entry.description) return `技能 ${entry.name} 缺少 description`;
  if (typeof entry.content !== 'string' || !entry.content) return `技能 ${entry.name} 缺少 content 正文`;
  return null;
}

export async function apply(ctx) {
  let key = null;
  /** @type {Array<() => void>} */
  let disposers = [];
  /** @type {string[] | null} */
  let registeredNames = null;

  try {
    const raw = await readFile(ASSET_PATH, 'utf8');
    const payload = JSON.parse(raw);

    key = deriveKey();
    const bundle = decryptBundle(key, payload);

    const skills = bundle?.skills;
    if (!Array.isArray(skills) || skills.length === 0) {
      throw new DecryptError('[wrench-skill] 资产包内容为空：解密成功但没有任何技能条目。请重新下载完整插件包。');
    }
    for (let i = 0; i < skills.length; i++) {
      const problem = validateSkill(skills[i], i);
      if (problem) throw new DecryptError(`[wrench-skill] 资产包校验失败：${problem}。请联系开发者重新打包。`);
    }

    // 内存注册：明文 content 直接交给注册表，不写入任何本地文件。
    registeredNames = [];
    for (const s of skills) {
      disposers.push(ctx.skills.register({
        name: s.name,
        description: s.description,
        whenToUse: s.whenToUse,
        content: s.content,
        source: 'runtime',
        metadata: s.metadata,
      }));
      registeredNames.push(s.name);
    }

    console.info(`[wrench-skill] 插件加载成功：已注册 ${registeredNames.length} 项加密技能（内存运行，明文不落地）。`);
  } catch (err) {
    // 解密/加载异常：输出中文友好提示后抛出，让 DSH 面板可见加载失败原因。
    const message = err instanceof DecryptError ? err.message :
      `[wrench-skill] 插件加载失败：${err?.message ?? err}\n` +
      '排查指引：①确认插件包完整（重新下载）；②确认插件版本与资产包为同一批次；③确认 DSH/Node 版本满足要求。';
    console.error(message);
    throw err instanceof DecryptError ? err : new DecryptError(message);
  }

  // 插件卸载/重载：注销全部技能 + 清零内存中的密钥与敏感引用。
  ctx.on('dispose', () => {
    for (const dispose of disposers) {
      try { dispose(); } catch { /* 忽略注销异常，保证清理继续 */ }
    }
    disposers = [];
    registeredNames = null;
    zeroize(key);
    key = null;
    console.info('[wrench-skill] 插件已卸载：技能注册已注销，内存密钥与明文缓存已清空。');
  });
}
