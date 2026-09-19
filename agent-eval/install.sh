#!/bin/bash
# agent-eval 一键下载安装（独立可 curl 直跑，无需 clone 整仓库）
#
# 一键安装：
#   curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/agent-eval/install.sh | bash
#
# 可选环境变量：
#   AGENT_EVAL_TARGET  安装目标根（默认 ~/.agents/skills；DSH 用户可设 ~/.dsh/skills）
#   AGENT_EVAL_REF     分支/标签（默认 main）
set -euo pipefail

REPO="xu-jin-cs/dsh-skills"
REF="${AGENT_EVAL_REF:-main}"
TARGET_ROOT="${AGENT_EVAL_TARGET:-$HOME/.agents/skills}"
DEST="${TARGET_ROOT}/agent-eval"

echo "[agent-eval] 一键安装 → ${DEST}"

# 1. 下载仓库 zipball 并抽取 agent-eval 子目录
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
echo "[agent-eval] 下载 ${REPO}@${REF} ..."
curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${REF}.zip" -o "${TMP}/repo.zip"
python3 - "${TMP}/repo.zip" "${TMP}/extract" <<'PY'
import sys, zipfile, os
zpath, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zpath) as z:
    members = [m for m in z.namelist() if "/agent-eval/" in m and not m.endswith("/")]
    if not members:
        sys.exit("[agent-eval] ✗ 仓库中未找到 agent-eval 目录")
    for m in members:
        rel = m.split("/agent-eval/", 1)[1]
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with z.open(m) as s, open(dst, "wb") as d:
            d.write(s.read())
print(f"[agent-eval] 抽取 {len(members)} 个文件")
PY

# 2. 安装到技能发现根（原子替换）
mkdir -p "${TARGET_ROOT}"
[ -d "${DEST}" ] && rm -rf "${DEST}.bak" && mv "${DEST}" "${DEST}.bak"
mkdir -p "${DEST}"
cp -R "${TMP}/extract/" "${DEST}/"
rm -rf "${DEST}.bak" 2>/dev/null || true
chmod +x "${DEST}/scripts/eval_agents.py" 2>/dev/null || true
echo "[agent-eval] 已安装到 ${DEST}"

# 3. 依赖检查（matplotlib + numpy）
PYBIN="python3"
if ! python3 -c "import matplotlib, numpy" 2>/dev/null; then
  if [ -x "$HOME/.browser-use-env/bin/python3" ] && "$HOME/.browser-use-env/bin/python3" -c "import matplotlib, numpy" 2>/dev/null; then
    PYBIN="$HOME/.browser-use-env/bin/python3"
    echo "[agent-eval] 系统 python3 缺依赖，将使用 ${PYBIN}（脚本运行时也会自动回退到它）"
  else
    echo "[agent-eval] 安装依赖 matplotlib numpy ..."
    python3 -m pip install --user matplotlib numpy || {
      echo "[agent-eval] ✗ 依赖安装失败，请手动执行: python3 -m pip install matplotlib numpy" >&2
      exit 1
    }
  fi
fi

# 4. 冒烟验证（语法+帮助）
"${PYBIN}" -c "import ast; ast.parse(open('${DEST}/scripts/eval_agents.py').read())" \
  && echo "[agent-eval] ✓ 脚本语法校验通过"

echo ""
echo "[agent-eval] ✅ 安装完成。使用："
echo "  ${PYBIN} ${DEST}/scripts/eval_agents.py            # 一键评估出报告"
echo "  或对 Agent 说：agent能力评估 / /agenteval"
