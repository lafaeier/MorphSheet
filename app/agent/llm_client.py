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
    try:
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
    except Exception as e:
        raise RuntimeError("DeepSeek API 调用失败: " + str(e))

    # 清理 markdown 代码块
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # 尝试解析 JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # API 可能返回了错误文本（如 "Internal Server Error"）
        if raw and len(raw) < 200:
            raise RuntimeError("API 返回错误: " + raw)
        # 尝试提取 JSON 片段
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        raise RuntimeError("API 返回了非 JSON 响应: " + raw[:200])
