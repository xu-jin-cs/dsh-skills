/**
 * 资产访问层：直读明文 assets/rules.json 并提供结构化只读访问。
 * 插件入口（lib/index.js）与 CLI（bin/*）共用。
 * v3 起为 Source-Available 明文分发（2026-08-23 用户裁定），不再有解密链路。
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const DEFAULT_ASSET_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'assets', 'rules.json');

export class AssetStore {
  #bundle;

  constructor(bundle) {
    this.#bundle = bundle;
  }

  /** 从明文资产文件加载。 */
  static async load(assetPath = DEFAULT_ASSET_PATH) {
    const raw = await readFile(assetPath, 'utf8');
    let bundle;
    try {
      bundle = JSON.parse(raw);
    } catch {
      throw new Error('[xujin] 资产包解析失败：assets/rules.json 不是合法 JSON。请重新下载完整插件包。');
    }
    if (!bundle || !Array.isArray(bundle.skills)) {
      throw new Error('[xujin] 资产包结构异常：缺少 skills 数组。请重新下载完整插件包。');
    }
    return new AssetStore(bundle);
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

  /** @returns {object} 引擎默认规则（如 transitions 跃迁表），构建期预解析注入 */
  getEngineDefaults() {
    return this.#bundle.engineDefaults ?? {};
  }

  /** 资产包生成时间（调试用）。 */
  get generatedAt() {
    return this.#bundle.generatedAt;
  }
}
