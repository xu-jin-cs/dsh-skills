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

/** HKDF 固定业务标识 info。 */
export const HKDF_INFO = 'wrench-skill/agentpkg/v1';

/** 冻结 Embedding 模型（1024 维，bge-large-zh 系列）。版本冻结，禁止随意变更。 */
export const EMBEDDING_MODEL_ID = 'Xenova/bge-large-zh-v1.5';

/** Embedding 向量维度（冻结 1024 维）。 */
export const EMBEDDING_DIM = 1024;

/** HKDF Salt 截取字节数（uint16 量化序列前 16 字节）。 */
export const SALT_BYTES = 16;

/** AES-256-GCM 工作密钥长度（字节）。 */
export const KEY_BYTES = 32;

/** 资产包格式版本号：结构变更时 +1，插件解密前校验。 */
export const PAYLOAD_VERSION = 1;

/** 资产包算法标识，解密前校验防版本漂移。 */
export const PAYLOAD_ALG = 'AES-256-GCM/HKDF-SHA256/EMB-bge-large-zh-v1.5-uint16';
