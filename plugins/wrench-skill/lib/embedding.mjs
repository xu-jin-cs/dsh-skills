/**
 * Embedding 派生 Salt 模块（二道混淆之第一道）。
 *
 * 链路：固定盐源文本 → 冻结 1024 维 Embedding 编码（CLS pooling）
 *      → L2 归一化 → uint16 定点量化（消除浮点误差）→ 截取前 16 字节作为 HKDF Salt。
 *
 * 加密（开发者 encrypt.mjs）与解密（插件运行时）共用本模块，保证两侧派生一致。
 */

import { EMBEDDING_MODEL_ID, EMBEDDING_DIM, SALT_BYTES, SALT_SOURCE_TEXT } from './constants.mjs';

let _extractorPromise = null;

/**
 * 懒加载并缓存冻结版本的 feature-extraction pipeline。
 * 常驻运行场景复用同一实例，避免重复加载模型开销。
 */
function getExtractor() {
  if (!_extractorPromise) {
    _extractorPromise = (async () => {
      const { pipeline, env } = await import('@huggingface/transformers');
      // 冻结行为：禁止远程 Hub 动态拉取未固定分支之外的模型文件；
      // 模型版本由 package.json 中 @huggingface/transformers 精确版本 + 模型 ID 双重冻结。
      env.allowLocalModels = true;
      env.allowRemoteModels = true; // 首次运行需下载模型至本地缓存，之后离线可用
      return pipeline('feature-extraction', EMBEDDING_MODEL_ID, { quantized: true });
    })();
  }
  return _extractorPromise;
}

/**
 * 对固定盐源文本编码，输出 L2 归一化后的 1024 维浮点向量。
 * @returns {Promise<Float32Array>}
 */
export async function embedSaltSource() {
  const extractor = await getExtractor();
  const output = await extractor(SALT_SOURCE_TEXT, { pooling: 'cls', normalize: false });
  const vec = output.data;
  if (!(vec instanceof Float32Array) || vec.length !== EMBEDDING_DIM) {
    throw new Error(
      `[wrench-skill] Embedding 输出维度异常：期望 ${EMBEDDING_DIM} 维，实际 ${vec?.length ?? '未知'}。\n` +
      `可能原因：Embedding 模型版本被更换。请核对插件包完整性，或联系开发者重新加密资产。`
    );
  }
  // L2 归一化
  let norm = 0;
  for (let i = 0; i < vec.length; i++) norm += vec[i] * vec[i];
  norm = Math.sqrt(norm) || 1;
  const out = new Float32Array(vec.length);
  for (let i = 0; i < vec.length; i++) out[i] = vec[i] / norm;
  return out;
}

/**
 * uint16 定点量化：将 [-1,1] 浮点向量映射到 [0,65535] 整数序列（四舍五入），
 * 消除跨平台浮点误差，保证加密/解密两侧字节级一致。
 * @param {Float32Array} normalizedVec L2 归一化后的向量
 * @returns {Buffer} uint16 小端字节序列
 */
export function quantizeUint16(normalizedVec) {
  const buf = Buffer.alloc(normalizedVec.length * 2);
  for (let i = 0; i < normalizedVec.length; i++) {
    const q = Math.round(((normalizedVec[i] + 1) / 2) * 65535);
    buf.writeUInt16LE(Math.min(65535, Math.max(0, q)), i * 2);
  }
  return buf;
}

/**
 * 派生 HKDF Salt：Embedding → L2 归一化 → uint16 量化 → 截取前 16 字节。
 * @returns {Promise<Buffer>} 16 字节 Salt
 */
export async function deriveSalt() {
  const vec = await embedSaltSource();
  const quantized = quantizeUint16(vec);
  return quantized.subarray(0, SALT_BYTES);
}
