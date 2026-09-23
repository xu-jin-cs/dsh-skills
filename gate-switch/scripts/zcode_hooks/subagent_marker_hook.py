"""subagent_marker_hook.py — 子代理运行窗口标记钩子

2026-09-06 用户裁定（子代理不扛纪律闸，删除命令母体专属），
problem_gate / reform_gate / council 三关判 A。

契约：
  标记文件：~/.agents/logs/zcode_subagent_marker.json
  JSON 模式：{"count": <int>=0, "expires_at": "<UTC ISO8601>",
             "parent_session": "<母体 session_id>", "note": "<可空>"}
  窗口判定（读侧参考，本钩子不写读侧）：
    count>0 且 expires_at>now 为开启；文件缺失/解析失败/过期=关闭。

  CLI：python3 subagent_marker_hook.py set|clear
    set   ：读 stdin 钩子载荷（JSON，取 session_id/sessionId 作 parent_session，
            tool_input.description 作 note），count+1，expires_at=now+30min，
            原子写（写 .tmp 后 os.replace），stdout 打印一行 JSON 状态，exit 0。
    clear ：count-1（下限 0），count 到 0 则删除标记文件，否则原子写回，exit 0。
    任何异常静默 exit 0（只往 ~/.agents/logs/zcode_hooks.log 追加一行错误日志，
    绝不阻塞钩子链）。

已知取舍（裁定声明）：
  1. 窗口期母体调用同样豁免——钩子载荷无身份字段，读侧无法区分母体/子代理
     发起的工具调用，属结构性上限。
  2. run_in_background 子代理的 PostToolUse 时机未实证，降级路径为
     declare_stamp 兜底。
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

MARKER_PATH = os.path.expanduser("~/.agents/logs/zcode_subagent_marker.json")
LOG_PATH = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
WINDOW_MINUTES = 30


def _log_error(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s [subagent_marker_hook] %s\n" % (now, msg))
    except Exception:
        pass


def _read_marker():
    try:
        with open(MARKER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def _atomic_write(data):
    os.makedirs(os.path.dirname(MARKER_PATH), exist_ok=True)
    tmp_path = MARKER_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, MARKER_PATH)


def _now_utc():
    return datetime.now(timezone.utc)


def _do_set():
    payload = {}
    try:
        raw = sys.stdin.read()
        if raw:
            payload = json.loads(raw)
    except Exception:
        payload = {}

    parent_session = payload.get("session_id") or payload.get("sessionId") or ""
    note = ""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        desc = tool_input.get("description")
        if isinstance(desc, str):
            note = desc

    marker = _read_marker() or {}
    count = marker.get("count", 0)
    try:
        count = int(count)
    except Exception:
        count = 0
    if count < 0:
        count = 0
    count += 1

    expires_at = (_now_utc() + timedelta(minutes=WINDOW_MINUTES)).isoformat()
    data = {
        "count": count,
        "expires_at": expires_at,
        "parent_session": parent_session,
        "note": note or None,
    }
    _atomic_write(data)
    sys.stdout.write(json.dumps({"status": "set", "count": count,
                                 "expires_at": expires_at},
                                ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _do_clear():
    marker = _read_marker()
    if marker is None:
        # 文件缺失或解析失败：视为已关闭，无需处理
        sys.stdout.write(json.dumps({"status": "clear", "count": 0,
                                     "removed": False, "reason": "no_marker"},
                                    ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return

    count = marker.get("count", 0)
    try:
        count = int(count)
    except Exception:
        count = 0
    count -= 1
    if count <= 0:
        count = 0
        try:
            if os.path.exists(MARKER_PATH):
                os.remove(MARKER_PATH)
            removed = True
        except Exception:
            removed = False
        sys.stdout.write(json.dumps({"status": "clear", "count": 0,
                                     "removed": removed},
                                    ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return

    marker["count"] = count
    _atomic_write(marker)
    sys.stdout.write(json.dumps({"status": "clear", "count": count,
                                 "removed": False},
                                ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else ""
        if action == "set":
            _do_set()
        elif action == "clear":
            _do_clear()
        else:
            _log_error("unknown action: %r" % action)
    except Exception as e:
        _log_error("exception: %r" % e)
    sys.exit(0)


if __name__ == "__main__":
    main()
