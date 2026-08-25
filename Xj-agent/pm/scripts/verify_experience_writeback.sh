#!/bin/bash
# verify_experience_writeback.sh — PM 工作流通用「经验固化」机械校验
# 用法: bash verify_experience_writeback.sh <本次产出物路径> <经验/索引文件路径> [关键词]
# 校验项（任一不过即退出码 1）：
#   1. 经验/索引文件存在且非空
#   2. 经验/索引文件 mtime >= 本次产出物 mtime（证明本轮有实际写入，而非口头声明）
#   3. 关键词命中（证明本次内容已入库，而非只动了别的内容）
# 适用节点：spm/dpm 复盘学习回写、retro 经验入库（registry-index.json）等一切"声称已沉淀"的场景
set -u
ARTIFACT="${1:-}"
EXP="${2:-}"
KEYWORD="${3:-}"

fail() { echo "❌ 固化校验不通过: $1"; exit 1; }

[ -n "$ARTIFACT" ] && [ -f "$ARTIFACT" ] || fail "本次产出物不存在: $ARTIFACT"
EXP_RESOLVED=$(eval echo "$EXP")
[ -s "$EXP_RESOLVED" ] || fail "经验/索引文件不存在或为空: $EXP_RESOLVED"

if [ "$(stat -f %m "$EXP_RESOLVED")" -lt "$(stat -f %m "$ARTIFACT")" ]; then
  fail "经验/索引文件修改时间早于本次产出物，说明本轮未实际固化: $EXP_RESOLVED"
fi

if [ -n "$KEYWORD" ] && ! grep -q "$KEYWORD" "$EXP_RESOLVED"; then
  fail "经验/索引文件中未命中关键词「$KEYWORD」，本次内容未入库"
fi

echo "✅ 固化校验通过: $EXP_RESOLVED 已包含本轮沉淀（mtime + 关键词双验证）"
