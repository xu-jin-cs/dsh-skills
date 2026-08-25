#!/bin/bash
# engine_preflight.sh — pm 流程启动前引擎体检
# 逻辑：健康检查 → 离线则自动拉起 → 复检。exit 0=引擎可用 / 1=拉起失败须人工介入。
# 纪律：禁止静默降级为软执行——本脚本失败时流程必须冻结并提示用户，不得绕过。
#
# 引擎接线：默认检查 Xj-engine（`xj-engine health`）。若你接入的是其它引擎，
# 请设置环境变量 ENGINE_HEALTH_CMD 指向你的健康检查命令、ENGINE_START_CMD
# 指向拉起命令（例如 FastAPI 服务可设 ENGINE_HEALTH_CMD='curl -fs -o /dev/null
# http://127.0.0.1:8001/api/engine/health'）。
set -u

HEALTH_CMD="${ENGINE_HEALTH_CMD:-xj-engine health}"
START_CMD="${ENGINE_START_CMD:-}"

check() { eval "$HEALTH_CMD" >/dev/null 2>&1; }

if check; then
  echo "✅ engine 在线（${HEALTH_CMD}）"
  exit 0
fi

if [ -n "$START_CMD" ]; then
  echo "⚠️ engine 离线，尝试拉起（${START_CMD}）..."
  eval "$START_CMD" >/tmp/engine_preflight_start.log 2>&1

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
fi

echo "❌ engine 离线且未配置拉起命令（ENGINE_START_CMD）。流程冻结，请启动引擎后重试。"
exit 1
