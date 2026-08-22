#!/bin/bash
# wrench-skill 一键安装脚本（macOS / Linux，小白零密钥零配置）
#
# 用法：
#   bash install.sh                  # 默认装入 web profile
#   bash install.sh default          # 装入指定 profile
#   bash install.sh web /path/to/wrench-skill-1.0.0.tgz   # 安装已下载的插件包
#
# 做的事（全自动）：
#   1. 把插件装进指定 DSH profile（底层走 dsh plugin add → pnpm）；
#   2. 向该 profile 的 cordis.patch.yml 幂等写入插件装载条目；
#   3. 列出已装插件，确认安装结果。
set -euo pipefail

PROFILE="${1:-${DSH_PROFILE:-web}}"
PKG_REF="${2:-}"
PKG_NAME="@xu-jin-cs/dsh-cordis-wrench-skill"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="${DSH_HOME:-$HOME/.dsh}/profiles/${PROFILE}"
PATCH_FILE="${PROFILE_DIR}/cordis.patch.yml"

echo "==> 目标 profile：${PROFILE}"

# 第 1 步：安装插件包
if [ -z "${PKG_REF}" ]; then
  echo "==> 未指定插件包，正在从当前目录打包…"
  TGZ=$(cd "${PLUGIN_DIR}" && npm pack --silent 2>/dev/null | tail -1)
  PKG_REF="${PLUGIN_DIR}/${TGZ}"
  echo "    已打包：${PKG_REF}"
fi
echo "==> 安装插件到 profile ${PROFILE}…"
dsh plugin --profile "${PROFILE}" add "${PKG_REF}"

# 第 2 步：幂等写入 cordis.patch.yml 装载条目
echo "==> 注册插件装载条目 → ${PATCH_FILE}"
PATCH_FILE="${PATCH_FILE}" PKG_NAME="${PKG_NAME}" node --input-type=module -e '
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const file = process.env.PATCH_FILE;
const pkg = process.env.PKG_NAME;
const entry = `- insert:\n    - id: wrench-skill\n      name: ${JSON.stringify(pkg)}\n`;
let text = existsSync(file) ? readFileSync(file, "utf8") : "";
if (text.includes("id: wrench-skill")) {
  console.log("    条目已存在，跳过（幂等）");
} else if (text.trim() === "" || text.trim() === "[]") {
  writeFileSync(file, "# dsh profile patch layer\n" + entry);
  console.log("    已创建 patch 文件并写入条目");
} else {
  if (!text.endsWith("\n")) text += "\n";
  writeFileSync(file, text + "\n" + entry);
  console.log("    已追加装载条目");
}
'

# 第 3 步：校验
echo "==> 已安装插件列表："
dsh plugin --profile "${PROFILE}" list 2>/dev/null | grep -i "wrench" || true
echo ""
echo "✅ 安装完成。重启 DSH（或等待热重载）后，插件将自动解密并在内存中注册技能。"
echo "   校验方式：在 DSH 会话中输入 /wrench-demo 或「扳手自检」。"
