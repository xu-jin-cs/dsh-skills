#!/bin/bash
# wrench-skill 一键卸载脚本（macOS / Linux）
#
# 用法：
#   bash uninstall.sh            # 默认从 web profile 卸载
#   bash uninstall.sh default    # 从指定 profile 卸载
#
# 做的事（全自动）：
#   1. 从指定 DSH profile 移除插件包；
#   2. 从 cordis.patch.yml 移除插件装载条目；
#   3. DSH 重载插件时自动注销技能注册并清空内存中的密钥与明文缓存。
set -euo pipefail

PROFILE="${1:-${DSH_PROFILE:-web}}"
PKG_NAME="@xu-jin-cs/dsh-cordis-wrench-skill"
PROFILE_DIR="${DSH_HOME:-$HOME/.dsh}/profiles/${PROFILE}"
PATCH_FILE="${PROFILE_DIR}/cordis.patch.yml"

echo "==> 目标 profile：${PROFILE}"

# 第 1 步：移除插件包
echo "==> 移除插件包…"
dsh plugin --profile "${PROFILE}" rm "${PKG_NAME}" || echo "    （插件包本就不在依赖中，跳过）"

# 第 2 步：移除 cordis.patch.yml 中的装载条目
if [ -f "${PATCH_FILE}" ]; then
  echo "==> 清理装载条目 → ${PATCH_FILE}"
  PATCH_FILE="${PATCH_FILE}" node --input-type=module -e '
import { readFileSync, writeFileSync } from "node:fs";
const file = process.env.PATCH_FILE;
const lines = readFileSync(file, "utf8").split("\n");
const out = [];
let removed = false;
for (let i = 0; i < lines.length; i++) {
  // 匹配由 install.sh 写入的独立 insert 块：
  //   - insert:
  //       - id: wrench-skill
  //         name: "..."
  if (/^- insert:\s*$/.test(lines[i])
      && /^\s+- id: wrench-skill\s*$/.test(lines[i + 1] ?? "")) {
    let j = i + 2; // 跳过 name 行及该条目后续缩进行
    while (j < lines.length && /^\s+\S/.test(lines[j])) j++;
    i = j - 1;
    removed = true;
    continue;
  }
  out.push(lines[i]);
}
writeFileSync(file, out.join("\n"));
console.log(removed ? "    已移除 wrench-skill 装载条目" : "    未找到装载条目（幂等跳过）");
'
fi

# 第 2.5 步：移除 CLI shim
rm -f "${HOME}/.dsh/bin/wrench-gate" "${HOME}/.dsh/bin/wrench-engine" 2>/dev/null && echo "==> 已移除 CLI shim（~/.dsh/bin/wrench-gate / wrench-engine）"

echo ""
echo "✅ 卸载完成。DSH 重载后将自动注销技能并清空内存中的密钥与明文缓存，无任何残留。"
