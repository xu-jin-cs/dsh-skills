/**
 * wrench-skill 冻结常量（开发者统一保管，加密/解密两侧共用同一份）。
 *
 * ⚠️ 版本冻结铁律：本文件任何字段变更都会改变派生密钥，
 *    变更后必须用 encrypt.mjs 全量重新加密所有规则资产，否则解密必失败。
 */

/** 内置加密种子：仅用于 HKDF 密钥派生，打包/发布全程使用同一种子。 */
export const EMBEDDED_SEED = 'wrench-skill::builtin-seed::7f3a9c1e-bd52-48f6-91d0-2e6c5a84f0b7';

/** 固定盐源文本：Embedding 编码输入，固化于插件内部，禁止改动。 */
export const SALT_SOURCE_TEXT = '求职ai agent专家，优先在家办公';

/**
 * Embedding 派生 Salt（16 字节，hex）。
 * 由开发者用本地冻结 1024 维 BGE-M3 经 scripts/derive_salt.py 一次性离线派生：
 * 盐源文本编码 → L2 归一化 → uint16 定点量化 → 截取前 16 字节。
 * 运行时仅消费本常量，不依赖任何模型，保持插件轻量化。
 * 派生模型：BAAI/bge-m3（本地 HF 缓存，离线）；重算校验：derive_salt.py --check。
 */
export const EMBEDDED_SALT_HEX = 'b77bfd80d97aa67fd57ebf81627b527d';

/** HKDF 固定业务标识 info。 */
export const HKDF_INFO = 'wrench-skill/agentpkg/v1';

/** AES-256-GCM 工作密钥长度（字节）。 */
export const KEY_BYTES = 32;

/** 资产包格式版本号：结构变更时 +1，插件解密前校验。 */
export const PAYLOAD_VERSION = 1;

/** 资产包算法标识，解密前校验防版本漂移。 */
export const PAYLOAD_ALG = 'AES-256-GCM/HKDF-SHA256/EMB-bge-m3-uint16';
