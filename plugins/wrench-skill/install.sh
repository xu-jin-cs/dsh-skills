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
for tool in wrench-gate wrench-engine; do
  cat > "${SHIM_DIR}/${tool}" <<EOF
#!/bin/bash
# wrench-skill 插件 CLI shim（由 install.sh 生成，profile=${PROFILE}）
PKG="\${WRENCH_PKG:-${HOME}/.dsh/profiles/${PROFILE}/node_modules/@xu-jin-cs/dsh-cordis-wrench-skill}"
exec node "\${PKG}/bin/${tool}.mjs" "\$@"
EOF
  chmod +x "${SHIM_DIR}/${tool}"
done
echo "    已安装：wrench-gate / wrench-engine"

# 第 3 步：校验
echo "==> 已安装插件列表："
dsh plugin --profile "${PROFILE}" list 2>/dev/null | grep -i "wrench" || true
echo ""
echo "✅ 安装完成。重启 DSH（或等待热重载）后，插件将自动解密并在内存中注册技能。"
echo "   校验方式：在 DSH 会话中输入 /wrench-demo 或「扳手自检」。"
