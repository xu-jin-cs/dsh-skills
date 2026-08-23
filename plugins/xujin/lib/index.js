/**
 * xujin —— DSH Cordis 私有 Skill/规则插件（Source-Available 明文分发，开源小白友好版）。
 *
 * 定位：非独立 Agent、非完整工作流；仅向 DeepSeek Harness 引擎提供
 * 可被调用的校验规则、闸开关与原子 Skill 能力。
 *
 * 加载链路（全自动，零配置、零模型依赖）：
 *   直读 assets/rules.json 明文资产（v3 起 Source-Available 明文分发，2026-08-23 用户裁定）
 *   → ctx.skills.register 以 runtime 源注册全部规则/原子技能。
 *
 * 闸开关与引擎内核不走技能注册，由 CLI 入口独立加载执行：
 *   ~/.dsh/bin/xujin-gate  <spec名> [--set k=v]   —— 扳闸（四态退出码）
 *   ~/.dsh/bin/xujin-engine <sign|verify|step-sync|et> … —— 签发/状态同步内核
 */

class AssetError extends Error {}
import { AssetStore } from './asset-store.mjs';

export const name = 'xujin';

/** 声明服务依赖：skill 注册表（dsh-skill）。 */
export const inject = ['skills'];

const KEBAB_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function validateSkill(entry, index) {
  if (!entry || typeof entry !== 'object') return `第 ${index + 1} 条技能不是有效对象`;
  if (!KEBAB_RE.test(entry.name ?? '')) return `第 ${index + 1} 条技能名称非法（需 kebab-case）：${entry.name}`;
  if (typeof entry.description !== 'string' || !entry.description) return `技能 ${entry.name} 缺少 description`;
  if (typeof entry.content !== 'string' || !entry.content) return `技能 ${entry.name} 缺少 content 正文`;
  return null;
}

export async function apply(ctx) {
  /** @type {Array<() => void>} */
  let disposers = [];
  /** @type {AssetStore | null} */
  let store = null;

  try {
    store = await AssetStore.load();
    const skills = store.listSkills();
    if (skills.length === 0) {
      throw new AssetError('[xujin] 资产包内容为空：没有任何技能条目。请重新下载完整插件包。');
    }
    for (let i = 0; i < skills.length; i++) {
      const problem = validateSkill(skills[i], i);
      if (problem) throw new AssetError(`[xujin] 资产包校验失败：${problem}。请联系开发者重新打包。`);
    }

    // 内存注册：content 直接交给注册表，不写入任何本地文件。
    for (const s of skills) {
      disposers.push(ctx.skills.register({
        name: s.name,
        description: s.description,
        whenToUse: s.whenToUse,
        content: s.content,
        source: 'runtime',
        metadata: s.metadata,
      }));
    }

    console.info(
      `[xujin] 插件加载成功：已注册 ${skills.length} 项技能/规则；` +
      `闸 spec ${store.listSpecs().length} 份、引擎规则 ${store.listEngineRules().length} 份可由 xujin-gate / xujin-engine 调用。`
    );
  } catch (err) {
    // 加载异常：输出中文友好提示后抛出，让 DSH 面板可见加载失败原因。
    const message = err instanceof AssetError ? err.message :
      `[xujin] 插件加载失败：${err?.message ?? err}\n` +
      '排查指引：①确认插件包完整（重新下载）；②确认 DSH/Node 版本满足要求。';
    console.error(message);
    throw err instanceof AssetError ? err : new AssetError(message);
  }

  // 插件卸载/重载：注销全部技能注册。
  ctx.on('dispose', () => {
    for (const dispose of disposers) {
      try { dispose(); } catch { /* 忽略注销异常，保证清理继续 */ }
    }
    disposers = [];
    store = null;
    console.info('[xujin] 插件已卸载：技能注册已注销。');
  });
}
