/**
 * 资产内存访问层：解密 rules.enc.json 并提供结构化只读访问。
 * 插件入口（lib/index.js）与 CLI（bin/*）共用；明文仅驻留本模块实例内，不落地。
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { deriveKey, decryptBundle, zeroize, DecryptError } from './crypto.mjs';

const DEFAULT_ASSET_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'rules.enc.json');

export class AssetStore {
  #bundle;

  constructor(bundle) {
    this.#bundle = bundle;
  }

  /** 从密文资产文件加载并解密（内存完成）。 */
  static async load(assetPath = DEFAULT_ASSET_PATH) {
    const raw = await readFile(assetPath, 'utf8');
    const payload = JSON.parse(raw);
    const key = deriveKey();
    try {
      const bundle = decryptBundle(key, payload);
      if (!bundle || !Array.isArray(bundle.skills)) {
        throw new DecryptError('[xujin] 资产包结构异常：缺少 skills 数组。请重新下载完整插件包。');
      }
      return new AssetStore(bundle);
    } finally {
      zeroize(key);
    }
  }

  /** @returns {Array} 全部技能条目（name/description/whenToUse/content/metadata） */
  listSkills() {
    return this.#bundle.skills;
  }

  /** @returns {object|undefined} 按名取闸 spec 对象（不含 .json 后缀） */
  getSpec(name) {
    return this.#bundle.specs?.[name];
  }

  /** @returns {string[]} 全部 spec 名 */
  listSpecs() {
    return Object.keys(this.#bundle.specs ?? {});
  }

  /** @returns {string|undefined} 按文件名取引擎规则 yaml 原文 */
  getEngineRule(fileName) {
    return this.#bundle.engineRules?.[fileName];
  }

  /** @returns {string[]} 全部引擎规则文件名 */
  listEngineRules() {
    return Object.keys(this.#bundle.engineRules ?? {});
  }

  /** 资产包生成时间（调试用）。 */
  get generatedAt() {
    return this.#bundle.generatedAt;
  }
}
