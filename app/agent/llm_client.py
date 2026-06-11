import json
import re
import time
from openai import OpenAI
from app.config import settings

_client = OpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
)


def _call_with_retry(messages, temperature, max_retries=3, is_json=False):
    """调用 DeepSeek API，带重试。处理 5xx / 速率限制 / 错误响应体。"""
    last_error = None
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": settings.deepseek_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096,
            }
            if is_json:
                kwargs["response_format"] = {"type": "json_object"}
            response = _client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            # 检测 API 返回的错误文本 (某些代理返回 200 + 错误文本)
            if is_json and not content.startswith('{') and not content.startswith('['):
                raise RuntimeError("API returned non-JSON: " + content[:200])
            if is_json:
                lower = content.lower()
                if any(e in lower for e in ("internal server error", "service unavailable",
                                              "rate limit", "too many requests", "timeout",
                                              "bad gateway", "gateway timeout")):
                    raise RuntimeError("API error response: " + content[:150])

            return content
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                time.sleep(wait)
    raise RuntimeError("DeepSeek API 调用失败 (重试{}次): {}".format(max_retries, last_error))


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    return _call_with_retry([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature)


def chat_structured(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
    raw = _call_with_retry([
        {"role": "system", "content": system_prompt + "\n你必须返回合法的 JSON 对象。"},
        {"role": "user", "content": user_prompt},
    ], temperature, is_json=True)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # 检查是否是 API 错误文本
    if "Internal Server Error" in raw or "Service Unavailable" in raw or "Rate limit" in raw:
        raise RuntimeError("API 服务端错误: " + raw[:200])

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if raw and len(raw) < 200 and not raw.startswith("{"):
            raise RuntimeError("API 返回错误: " + raw)
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        raise RuntimeError("API 返回了非 JSON 响应: " + raw[:200])
