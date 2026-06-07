import json
import re
from openai import OpenAI
from app.config import settings

_client = OpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
)


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """调用 DeepSeek API，返回文本响应。"""
    response = _client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
    )
    return response.choices[0].message.content


def chat_structured(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict:
    """调用 DeepSeek API，使用 JSON Mode 返回结构化数据。"""
    response = _client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt + "\n你必须返回合法的 JSON 对象。"},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    # 清理可能的 markdown 代码块包裹
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)
