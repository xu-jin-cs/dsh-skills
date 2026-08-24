"""Claude 执行引擎 — 调用 Anthropic API，仅转发 LLM 请求

注意：Prompt 不再硬编码，由调用方通过 prompt_store/core_loader 渲染后传入 system_prompt 参数。
"""

import anthropic
import re


class ClaudeEngine:
    """封装 Claude API 调用，仅负责请求转发与输出清洗"""

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-6",
                 max_tokens: int = 8000, temperature: float = 0.1,
                 max_retries: int = 2, base_url: str = ""):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.base_url = base_url
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        if not self._client:
            self._client = anthropic.Anthropic(api_key=self.api_key or None, **({"base_url": self.base_url} if self.base_url else {}))
        return self._client

    def execute(self, vl_text: str, system_prompt: str = "") -> dict:
        """输入文本 + 外部渲染的 system_prompt，返回 Claude 执行文本。

        用户消息原样转发 vl_text——业务包装（来源标注/场景前缀等）属业务规则，
        按引擎零业务常量裁定由调用方在 prompt 层完成，禁止下沉引擎层。
        """
        system = system_prompt or "你是一个纯执行工具。"
        last_err = ""
        for attempt in range(1 + self.max_retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system,
                    messages=[{
                        "role": "user",
                        "content": vl_text,
                    }],
                )
                raw = self._extract_text(resp.content)
                return {"text": self._clean(raw), "error": ""}
            except Exception as e:
                last_err = f"Claude 请求失败 (attempt {attempt + 1}): {e}"

        return {"text": "", "error": last_err}

    def send_raw(self, user_text: str, system_prompt: str = "") -> dict:
        """直接发送自定义文本给 Claude，system_prompt 由调用方提供"""
        system = system_prompt or "你是一个纯执行工具。"
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user_text}],
            )
            raw = self._extract_text(resp.content)
            return {"text": self._clean(raw), "error": ""}
        except Exception as e:
            return {"text": "", "error": f"Claude 请求失败: {e}"}

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        """从 content blocks 中提取纯文本，跳过 ThinkingBlock 等非文本块"""
        parts = []
        for block in content_blocks:
            if hasattr(block, 'text') and block.text:
                parts.append(block.text)
        return "".join(parts)

    def _clean(self, text: str) -> str:
        """清洗 Claude 输出：移除 markdown 代码块标记、合并多余空行。

        仅保留通用格式清洗；引导话术等业务清洗规则已按「引擎零业务常量」
        裁定移出引擎层（2026-08-22），由调用方/技能层按需自行处理。
        """
        # 移除代码块标记
        text = re.sub(r'```[\w]*\n?', '', text)
        # 合并连续空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
