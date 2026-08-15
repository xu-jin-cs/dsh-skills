#!/bin/bash
# dsh-skills 本地安装入口（已 clone 仓库的场景，无需任何命令知识）
#
# 用法：
#   ./install.sh                      交互式选择要安装的技能
#   ./install.sh archmap              安装指定技能（agent/引擎类）
#   ./install.sh parallel-dispatch    安装指定技能（规则类）
#   ./install.sh archmap parallel-dispatch   一次装多个
#   ./install.sh --all                全部安装
#   ./install.sh --copy archmap       拷贝模式（脱离本仓库独立存在）
#   ./install.sh --target DIR archmap 装到指定发现根（默认 ~/.dsh/skills）
#
# 本脚本是 scripts/dsh-skill.sh 的友好外壳，装完 DSH watcher 热加载即生效。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CLI="${HERE}/scripts/dsh-skill.sh"

if [ ! -f "${CLI}" ]; then
  echo "[install] ✗ 缺少 ${CLI}，仓库不完整，请重新 clone" >&2
  exit 1
fi

# 无参数 → 交互式选择
if [ $# -eq 0 ]; then
  echo "dsh-skills 可用技能："
  NAMES=()
  i=1
  while IFS= read -r line; do
    name="${line%% *}"
    NAMES+=("${name}")
    printf "  %d) %s\n" "${i}" "${line}"
    i=$((i + 1))
  done < <(python3 -c "
import json
d=json.load(open('${HERE}/skills.json'))['skills']
for n,m in d.items():
    print('%-20s %s' % (n, m['summary']))
")
  echo "  a) 全部安装"
  printf "请选择（序号或名字，空格分隔）："; read -r pick
  SEL=()
  for p in ${pick}; do
    if [ "${p}" = "a" ] || [ "${p}" = "all" ]; then
      SEL=("--all"); break
    elif [[ "${p}" =~ ^[0-9]+$ ]] && [ "${p}" -ge 1 ] && [ "${p}" -le ${#NAMES[@]} ]; then
      SEL+=("${NAMES[$((p - 1))]}")
    else
      SEL+=("${p}")
    fi
  done
  [ ${#SEL[@]} -eq 0 ] && { echo "[install] 未选择，退出"; exit 0; }
  exec "${CLI}" install ${SEL[@]+"${SEL[@]}"} --with-deps
fi

# 有参数 → 直接透传给 CLI（install 语义）
exec "${CLI}" install "$@"
