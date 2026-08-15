#!/bin/bash
# dsh-skill —— dsh-skills 发布仓命令行集成器
# 面向 DeepSeek Harness 用户：一键下载技能并集成本地 DSH 发现链。
#
# 远程一键使用（无需先 clone）：
#   curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap
#
# 子命令：
#   list                          列出发布仓全部技能
#   install <技能...|--all>       安装技能（默认符号链接进 ~/.dsh/skills，DSH 热加载即生效）
#   uninstall <技能...>           卸载（移除符号链接；拷贝模式需 --force）
#   update                        git pull 同步上游最新技能（符号链接模式即时生效）
#   doctor                        体检：发现根、链接完整性、依赖声明
#
# 选项：
#   --target DIR    安装目标根（默认 ~/.dsh/skills；可用项目级 <proj>/.dsh/skills 或 ~/.agents/skills）
#   --copy          拷贝模式（脱离仓库独立存在，update 后需重装）
#   --with-deps     引擎类技能自动执行 pip3 install -r requirements.txt
#   --yes           跳过确认
#
# 环境变量：
#   DSH_SKILLS_HOME   远程自举时仓库落地位置（默认 ~/.dsh/dsh-skills）
set -euo pipefail

REPO_URL="https://github.com/xu-jin-cs/dsh-skills.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"

# ---------- 远程自举：脚本不在仓内（curl|bash 场景）→ 浅克隆后续跑 ----------
bootstrap_if_needed() {
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/../skills.json" ]; then
    REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    return
  fi
  REPO_DIR="${DSH_SKILLS_HOME:-$HOME/.dsh/dsh-skills}"
  if [ ! -d "$REPO_DIR/.git" ]; then
    echo "[dsh-skill] 首次使用，克隆发布仓到 $REPO_DIR ..."
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  fi
  exec "$REPO_DIR/scripts/dsh-skill.sh" "$@"
}

# ---------- 参数解析 ----------
CMD="${1:-help}"; [ $# -gt 0 ] && shift || true
TARGET="$HOME/.dsh/skills"
MODE="link"
WITH_DEPS=0
ASSUME_YES=0
ITEMS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --copy) MODE="copy"; shift ;;
    --with-deps) WITH_DEPS=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --all) ITEMS+=("--all"); shift ;;
    *) ITEMS+=("$1"); shift ;;
  esac
done

bootstrap_if_needed "$CMD" ${ITEMS[@]+"${ITEMS[@]}"} --target "$TARGET" $([ "$MODE" = copy ] && echo --copy) $([ $WITH_DEPS = 1 ] && echo --with-deps) $([ $ASSUME_YES = 1 ] && echo --yes)

MANIFEST="$REPO_DIR/skills.json"

# ---------- 工具函数 ----------
json_get() {  # 极简 JSON 取值：json_get <key-path-ish> ；依赖 python3（DSH 运行必备）
  python3 -c "
import json,sys
d=json.load(open('$MANIFEST'))
cur=d
for k in sys.argv[1].split('.'):
    cur=cur[k]
print(cur if not isinstance(cur,(list,dict)) else json.dumps(cur,ensure_ascii=False))
" "$1"
}

skill_names() { python3 -c "import json;print('\n'.join(json.load(open('$MANIFEST'))['skills'].keys()))"; }

confirm() {
  [ $ASSUME_YES = 1 ] && return 0
  printf "%s [y/N] " "$1"; read -r ans
  case "$ans" in y|Y|yes) return 0 ;; *) return 1 ;; esac
}

install_one() {
  local name="$1"
  if ! skill_names | grep -qx "$name"; then
    echo "[dsh-skill] ✗ 技能不存在：$name（用 list 查看可用技能）" >&2; return 1
  fi
  local src="$REPO_DIR/$name" dst="$TARGET/$name"
  [ -d "$src" ] || { echo "[dsh-skill] ✗ 仓库内缺少目录：$src" >&2; return 1; }
  mkdir -p "$TARGET"
  if [ -L "$dst" ] || [ -d "$dst" ]; then
    echo "[dsh-skill] · 已存在，跳过：$dst（如需重装请先 uninstall）"; return 0
  fi
  if [ "$MODE" = link ]; then
    ln -s "$src" "$dst"
    echo "[dsh-skill] ✓ 链接安装：$dst → $src"
  else
    cp -R "$src" "$dst"
    echo "[dsh-skill] ✓ 拷贝安装：$dst"
  fi
  # 引擎类技能依赖
  if [ -f "$src/requirements.txt" ]; then
    if [ $WITH_DEPS = 1 ]; then
      echo "[dsh-skill]   安装依赖：pip3 install -r $name/requirements.txt"
      pip3 install -r "$src/requirements.txt" || echo "[dsh-skill]   ⚠ 依赖安装失败，可稍后手动执行" >&2
    else
      echo "[dsh-skill]   提示：该技能含 requirements.txt，可加 --with-deps 自动安装（archmap 缺失依赖时自动回退本地向量化，仍可用）"
    fi
  fi
}

uninstall_one() {
  local name="$1" dst="$TARGET/$name"
  if [ -L "$dst" ]; then
    rm "$dst"; echo "[dsh-skill] ✓ 已移除链接：$dst"
  elif [ -d "$dst" ]; then
    if confirm "拷贝目录 $dst 将被删除，确认？"; then
      rm -rf "$dst"; echo "[dsh-skill] ✓ 已删除：$dst"
    else
      echo "[dsh-skill] · 取消：$name"
    fi
  else
    echo "[dsh-skill] · 未安装：$name"
  fi
}

# ---------- 子命令 ----------
case "$CMD" in
  list)
    echo "dsh-skills 发布仓技能清单（$REPO_DIR）："
    python3 -c "
import json
d=json.load(open('$MANIFEST'))['skills']
for name,meta in d.items():
    print(f\"  {name:<20} [{meta['type']}] {meta['summary']}\")
"
    ;;
  install)
    if [ ${#ITEMS[@]} -eq 0 ]; then echo "用法：install <技能...|--all> [--target DIR] [--copy] [--with-deps]" >&2; exit 1; fi
    if [ "${ITEMS[0]:-}" = "--all" ]; then
      ITEMS=()
      while IFS= read -r n; do ITEMS+=("$n"); done < <(skill_names)
    fi
    echo "[dsh-skill] 安装目标根：$TARGET（DSH 发现链：项目/.dsh/skills → ~/.dsh/skills → ~/.agents/skills）"
    for it in "${ITEMS[@]}"; do install_one "$it"; done
    echo "[dsh-skill] 完成。DSH 技能 watcher 会热加载，无需重启；可 /技能名 显式调用。"
    ;;
  uninstall)
    [ ${#ITEMS[@]} -eq 0 ] && { echo "用法：uninstall <技能...> [--target DIR]" >&2; exit 1; }
    for it in "${ITEMS[@]}"; do uninstall_one "$it"; done
    ;;
  update)
    echo "[dsh-skill] 同步上游：$REPO_DIR"
    git -C "$REPO_DIR" pull --ff-only
    echo "[dsh-skill] 符号链接模式技能已即时生效；拷贝模式请重新 install。"
    ;;
  doctor)
    echo "[dsh-skill] 体检（目标根：$TARGET）"
    [ -d "$TARGET" ] || echo "  ⚠ 目标根不存在：$TARGET"
    find "$TARGET" -maxdepth 1 -type l 2>/dev/null | while read -r l; do
      if [ -e "$l" ]; then echo "  ✓ 链接正常：$(basename "$l")"; else echo "  ✗ 断链：$(basename "$l") → $(readlink "$l")"; fi
    done
    for name in $(skill_names); do
      if [ -e "$TARGET/$name" ]; then
        [ -f "$TARGET/$name/SKILL.md" ] && echo "  ✓ $name：SKILL.md 在位" || echo "  ✗ $name：缺 SKILL.md"
      else
        echo "  · $name：未安装"
      fi
    done
    command -v python3 >/dev/null && echo "  ✓ python3：$(python3 --version 2>&1)" || echo "  ✗ python3 缺失（archmap 引擎需要）"
    ;;
  help|*)
    sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
