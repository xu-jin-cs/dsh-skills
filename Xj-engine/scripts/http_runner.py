#!/usr/bin/env python3
"""http_runner.py — 引擎 runner 命令桥（OpenAI 兼容 /chat/completions）。

由工作流/引擎 CLI 通过 --runner-cmd 调用：
  python3 http_runner.py --prompt-file {prompt_file}

配置（环境变量，优先 RUNNER_*，其次 LOCAL_LLM_*，再次 CS_LLM_*）：
  RUNNER_BASE_URL / RUNNER_TOKEN / RUNNER_MODEL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

SYSTEM = ("你是工作流的阶段执行器。严格按任务指令产出本阶段交付物正文；"
          "遵守全局提示词基线；不要输出过程解释，只输出交付物内容。")


def _cfg() -> tuple[str, str, str]:
    for prefix, token_key in (("RUNNER", "RUNNER_TOKEN"),
                              ("LOCAL_LLM", "LOCAL_LLM_TOKEN"),
                              ("CS_LLM", "CS_LLM_API_KEY")):
        if prefix == "RUNNER":
            base = os.environ.get("RUNNER_BASE_URL", "")
            model = os.environ.get("RUNNER_MODEL", "")
            token = os.environ.get("RUNNER_TOKEN", "")
        elif prefix == "LOCAL_LLM":
            base = os.environ.get("LOCAL_LLM_ENDPOINT", "")
            model = os.environ.get("LOCAL_LLM_MODEL", "")
            token = os.environ.get("LOCAL_LLM_TOKEN", "")
        else:
            base = os.environ.get("CS_LLM_BASE_URL", "")
            model = os.environ.get("CS_LLM_MODEL", "")
            token = os.environ.get("CS_LLM_API_KEY", "")
        if base and model:
            return base, token, model
    return "", "", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    args = ap.parse_args()
    prompt = open(args.prompt_file, encoding="utf-8").read()
    base, token, model = _cfg()
    if not (base and model):
        print("RUNNER 未配置（RUNNER_/LOCAL_LLM_/CS_LLM_ 全空）", file=sys.stderr)
        return 2
    url = base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = {
        "model": model, "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)
        print(data["choices"][0]["message"]["content"])
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"RUNNER 调用失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
