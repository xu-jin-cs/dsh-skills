#!/bin/bash
# engine_preflight.sh — pm 流程启动前引擎体检（P2 · 2026-08-15 REFORM-GATE 判A）
# 逻辑：健康检查 → 离线则自动 start.sh 拉起 → 复检。exit 0=引擎可用 / 1=拉起失败须人工介入。
# 纪律：禁止静默降级为软执行——本脚本失败时流程必须冻结并提示用户，不得绕过。
set -u
API="http://127.0.0.1:8001/api"

# 2026-08-17 引擎替换：体检改打新引擎自检端点 GET /api/engine/health（旧 /docs 探活作废）
check() { curl -s -m 3 -o /dev/null -w "%{http_code}" "$API/engine/health" 2>/dev/null | grep -q "200"; }

if check; then
  echo "✅ engine 在线（${API}）"
  exit 0
fi

echo "⚠️ engine 离线，按裁定自动拉起（bash ~/agent-harness/start.sh）..."
bash ~/agent-harness/start.sh >/tmp/engine_preflight_start.log 2>&1

# 等待就绪，最多 60 秒
for i in $(seq 1 12); do
  sleep 5
  if check; then
    echo "✅ engine 拉起成功并复检通过（耗时 ~$((i*5))s）"
    exit 0
  fi
done

echo "❌ engine 拉起失败，日志见 /tmp/engine_preflight_start.log。流程冻结，请人工检查后重试。"
exit 1
