#!/bin/bash
# dsh-skills 自动发布脚本（launchd WatchPaths 触发）
# 变更落盘后防抖 60s 批量提交推送，避免每次按键都产生 commit
REPO="/Users/xujin/dsh-skills"
LOG="$HOME/Library/Logs/dsh-skills-autopublish.log"
LOCK="/tmp/dsh-skills-autopublish.lock"

# 并发去重：已有实例在跑则直接退出（launchd 会按 WatchPaths 再次触发）
if [ -f "$LOCK" ]; then
  pid=$(cat "$LOCK" 2>/dev/null)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then exit 0; fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

sleep 60  # 防抖窗口：连续编辑合并为一次提交

cd "$REPO" || exit 1
git add -A
if git diff --cached --quiet; then exit 0; fi

FILES=$(git diff --cached --name-only | head -10 | tr '\n' ' ')
TS=$(date "+%Y-%m-%d %H:%M:%S")
git commit -m "auto-publish: $FILES ($TS)" >> "$LOG" 2>&1
if git push origin HEAD >> "$LOG" 2>&1; then
  echo "[$TS] pushed: $FILES" >> "$LOG"
else
  echo "[$TS] PUSH FAILED: $FILES" >> "$LOG"
fi
