#!/bin/bash
# xujin 一键安装脚本（macOS / Linux，小白零密钥零配置）
#
# 用法：
#   bash install.sh                  # 默认装入 web profile
#   bash install.sh default          # 装入指定 profile
#   bash install.sh web /path/to/xujin-1.0.0.tgz   # 安装已下载的插件包
#
# 做的事（全自动）：
#   1. 把插件装进指定 DSH profile（底层走 dsh plugin add → pnpm）；
#   2. 向该 profile 的 cordis.patch.yml 幂等写入插件装载条目；
#   3. 列出已装插件，确认安装结果。
set -euo pipefail

PROFILE="${1:-${DSH_PROFILE:-web}}"
PKG_REF="${2:-}"
PKG_NAME="xujin"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="${DSH_HOME:-$HOME/.dsh}/profiles/${PROFILE}"
PATCH_FILE="${PROFILE_DIR}/cordis.patch.yml"

echo "==> 目标 profile：${PROFILE}"

# 第 1 步：安装插件包
if [ -z "${PKG_REF}" ]; then
  # 优先使用当前目录已下载的 tgz（curl 下载场景），没有再考虑本地打包
  TGZ_LOCAL=$(ls -t xujin-*.tgz 2>/dev/null | head -1 || true)
  if [ -n "${TGZ_LOCAL}" ]; then
    PKG_REF="$(pwd)/${TGZ_LOCAL}"
    echo "==> 使用已下载插件包：${PKG_REF}"
  else
    echo "==> 未指定插件包，正在从当前目录打包…"
    TGZ=$(cd "${PLUGIN_DIR}" && npm pack --silent 2>/dev/null | tail -1)
    PKG_REF="${PLUGIN_DIR}/${TGZ}"
    echo "    已打包：${PKG_REF}"
  fi
fi
echo "==> 安装插件到 profile ${PROFILE}…"
# 先移除旧版（文件源 tgz 按路径引用，旧包文件被重打包后路径失效会导致 pnpm 解析失败）
dsh plugin --profile "${PROFILE}" rm "${PKG_NAME}" 2>/dev/null || true
dsh plugin --profile "${PROFILE}" add "${PKG_REF}"

# 第 2 步：幂等写入 cordis.patch.yml 装载条目
echo "==> 注册插件装载条目 → ${PATCH_FILE}"
PATCH_FILE="${PATCH_FILE}" PKG_NAME="${PKG_NAME}" node --input-type=module -e '
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const file = process.env.PATCH_FILE;
const pkg = process.env.PKG_NAME;
const entry = `- insert:\n    - id: xujin\n      name: ${JSON.stringify(pkg)}\n`;
let text = existsSync(file) ? readFileSync(file, "utf8") : "";
if (text.includes("id: xujin")) {
  console.log("    条目已存在，跳过（幂等）");
} else {
  // 判定"空数组文档"：剥离注释行与空行后只剩 []（不能简单 trim 比较，注释行会导致误判）
  const body = text.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).join("\n").trim();
  if (body === "" || body === "[]") {
    // 保留原有注释头，仅把 [] 替换为条目
    const lines = text.split("\n");
    const out = [];
    let inserted = false;
    for (const l of lines) {
      if (!inserted && l.trim() === "[]") { out.push(entry.replace(/\n$/, "")); inserted = true; }
      else out.push(l);
    }
    if (!inserted) out.push(entry.replace(/\n$/, ""));
    writeFileSync(file, out.join("\n").replace(/\n{3,}/g, "\n\n"));
    console.log("    已写入装载条目（替换空数组占位）");
  } else {
    if (!text.endsWith("\n")) text += "\n";
    writeFileSync(file, text + "\n" + entry);
    console.log("    已追加装载条目");
  }
}
'

# 第 2.5 步：建立闸/引擎 CLI shim（~/.dsh/bin/，规则正文中被重写为对该路径的引用）
echo "==> 安装 CLI shim → ${HOME}/.dsh/bin/"
SHIM_DIR="${HOME}/.dsh/bin"
mkdir -p "${SHIM_DIR}"
for tool in xujin-gate xujin-engine; do
  cat > "${SHIM_DIR}/${tool}" <<EOF
#!/bin/bash
# xujin 插件 CLI shim（由 install.sh 生成，profile=${PROFILE}）
PKG="\${XUJIN_PKG:-${HOME}/.dsh/profiles/${PROFILE}/node_modules/${PKG_NAME}}"
exec node "\${PKG}/bin/${tool}.mjs" "\$@"
EOF
  chmod +x "${SHIM_DIR}/${tool}"
done
echo "    已安装：xujin-gate / xujin-engine"

# 第 2.6 步：安装查询闸焊点插件 dsh-trigger-auto（通道⑥ query_weld：read/grep/glob 前置 declare 定性，2026-08-23 合并入包）
echo "==> 安装查询闸焊点插件 dsh-trigger-auto…"
XUJIN_PKG_DIR="${HOME}/.dsh/profiles/${PROFILE}/node_modules/${PKG_NAME}"
TRIGGER_AUTO_SRC="${XUJIN_PKG_DIR}/payload/dsh-trigger-auto"
TRIGGER_AUTO_HOME="${DSH_HOME:-$HOME/.dsh}/plugins/dsh-trigger-auto"
if [ -d "${TRIGGER_AUTO_SRC}" ]; then
  # 拷出到 profile node_modules 之外的稳定位置（防 pnpm 重装抹掉 file: 目标）
  mkdir -p "$(dirname "${TRIGGER_AUTO_HOME}")"
  rm -rf "${TRIGGER_AUTO_HOME}"
  cp -R "${TRIGGER_AUTO_SRC}" "${TRIGGER_AUTO_HOME}"
  dsh plugin --profile "${PROFILE}" rm dsh-trigger-auto 2>/dev/null || true
  dsh plugin --profile "${PROFILE}" add "${TRIGGER_AUTO_HOME}"
  # 幂等确保 bundles 登记（dsh.profile.bundles 缺项则补）
  PROFILE_PKG="${PROFILE_DIR}/package.json" node --input-type=module -e '
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const file = process.env.PROFILE_PKG;
if (existsSync(file)) {
  const pkg = JSON.parse(readFileSync(file, "utf8"));
  const bundles = (((pkg.dsh ??= {}).profile ??= {}).bundles ??= []);
  if (!bundles.includes("dsh-trigger-auto")) {
    bundles.push("dsh-trigger-auto");
    writeFileSync(file, JSON.stringify(pkg, null, 2) + "\n");
    console.log("    已登记 dsh.profile.bundles: dsh-trigger-auto");
  } else {
    console.log("    bundles 条目已存在，跳过（幂等）");
  }
}'
  echo "    已安装：dsh-trigger-auto（查询闸焊点）"
else
  echo "    （包内无 payload/dsh-trigger-auto，跳过）"
fi

# 第 2.7 步：安装技能脚本运行时（v1.5.0：payload/skill-scripts → ~/.dsh/xujin-scripts/skills + xujin-run shim）
echo "==> 安装技能脚本运行时…"
SCRIPTS_SRC="${XUJIN_PKG_DIR}/payload/skill-scripts"
SCRIPTS_HOME="${HOME}/.dsh/xujin-scripts/skills"
if [ -d "${SCRIPTS_SRC}" ]; then
  mkdir -p "${SCRIPTS_HOME}"
  rm -rf "${SCRIPTS_HOME}"
  cp -R "${SCRIPTS_SRC}/." "${SCRIPTS_HOME}/"
  cat > "${SHIM_DIR}/xujin-run" <<EOF
#!/bin/bash
# xujin 插件 CLI shim（由 install.sh 生成，profile=${PROFILE}）
PKG="\${XUJIN_PKG:-${HOME}/.dsh/profiles/${PROFILE}/node_modules/${PKG_NAME}}"
exec node "\${PKG}/bin/xujin-run.mjs" "\$@"
EOF
  chmod +x "${SHIM_DIR}/xujin-run"
  echo "    已安装：xujin-run + 技能脚本库（${SCRIPTS_HOME}）"
else
  echo "    （包内无 payload/skill-scripts，跳过）"
fi

# 第 3 步：校验
echo "==> 已安装插件列表："
dsh plugin --profile "${PROFILE}" list 2>/dev/null | grep -i "xujin" || true
echo ""
echo "✅ 安装完成。重启 DSH（或等待热重载）后，插件将自动注册全部技能/规则/闸。"
echo "   校验方式：在 DSH 会话中输入 /xujin-demo 或「扳手自检」。"
