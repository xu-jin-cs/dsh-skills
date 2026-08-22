/**
 * 密钥派生与负载加解密模块（二道混淆之第二道）。
 *
 * 链路：内置加密种子 + Embedding 派生 Salt + 固定业务标识 info
 *      → HKDF-SHA256 派生 AES-256-GCM 工作密钥 → 负载加解密。
 *
 * 安全约束：派生 Salt、AES 工作密钥、解密后明文禁止输出至任何日志。
 */

import { hkdfSync, createCipheriv, createDecipheriv, randomBytes, timingSafeEqual } from 'node:crypto';
import { EMBEDDED_SEED, HKDF_INFO, KEY_BYTES, PAYLOAD_VERSION, PAYLOAD_ALG } from './constants.mjs';

/**
 * HKDF-SHA256 派生 AES-256-GCM 工作密钥。
 * @param {Buffer} salt Embedding 派生的 16 字节 Salt
 * @returns {Buffer} 32 字节工作密钥
 */
export function deriveKey(salt) {
  return Buffer.from(hkdfSync('sha256', Buffer.from(EMBEDDED_SEED, 'utf8'), salt, Buffer.from(HKDF_INFO, 'utf8'), KEY_BYTES));
}

/**
 * 加密规则资产包。
 * @param {Buffer} key deriveKey 派生的工作密钥
 * @param {object} bundle 规则资产对象（将被 JSON 序列化）
 * @returns {object} 可分发的密文资产包 {v, alg, iv, tag, data}（全 base64）
 */
export function encryptBundle(key, bundle) {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  const plaintext = Buffer.from(JSON.stringify(bundle), 'utf8');
  const data = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    v: PAYLOAD_VERSION,
    alg: PAYLOAD_ALG,
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    data: data.toString('base64'),
  };
}

/** 中文友好解密异常。 */
export class DecryptError extends Error {}

/**
 * 解密规则资产包（全部在内存完成，明文不落地）。
 * @param {Buffer} key deriveKey 派生的工作密钥
 * @param {object} payload encryptBundle 产出的密文资产包
 * @returns {object} 解密后的规则资产对象
 */
export function decryptBundle(key, payload) {
  if (!payload || typeof payload !== 'object') {
    throw new DecryptError('[wrench-skill] 解密失败：资产包格式为空或损坏。请重新下载完整插件包。');
  }
  if (payload.v !== PAYLOAD_VERSION || payload.alg !== PAYLOAD_ALG) {
    throw new DecryptError(
      `[wrench-skill] 解密失败：资产包版本不匹配（包内 v=${payload.v} alg=${payload.alg}，插件期望 v=${PAYLOAD_VERSION}）。\n` +
      `可能原因：插件与资产包不是同一批次发布。请核对 DSH 版本与插件包完整性，或联系开发者获取匹配版本。`
    );
  }
  try {
    const iv = Buffer.from(payload.iv, 'base64');
    const tag = Buffer.from(payload.tag, 'base64');
    const data = Buffer.from(payload.data, 'base64');
    const decipher = createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(data), decipher.final()]);
    return JSON.parse(plaintext.toString('utf8'));
  } catch (e) {
    if (e instanceof DecryptError) throw e;
    throw new DecryptError(
      '[wrench-skill] 解密失败：密文校验未通过（AuthTag 不匹配）。\n' +
      '可能原因：①插件包在传输中损坏，请重新下载；②Embedding 模型版本漂移，请核对插件依赖版本；③插件包被篡改。'
    );
  }
}

/**
 * 敏感缓冲清零（插件卸载/重载时调用）。
 * @param {...(Buffer|Uint8Array|null)} bufs
 */
export function zeroize(...bufs) {
  for (const b of bufs) {
    if (b && typeof b.fill === 'function') b.fill(0);
  }
}
