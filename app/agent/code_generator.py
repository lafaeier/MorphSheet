import json
import pandas as pd
from app.agent import prompts, llm_client, sandbox
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


def generate_and_execute(
    source_schema: dict,
    target_spec: dict,
    instructions: str,
    sample_data: str,
    source_df: pd.DataFrame,
) -> dict:
    """生成代码并执行。最多重试 max_retries 次。

    返回: {
        "success": bool,
        "result_df": pd.DataFrame | None,
        "code": str,
        "explanation": str,
        "column_mapping": dict,
        "error": str | None,
        "dirty_data": list | None,
        "retries": int,
    }
    """
    user_prompt = prompts.CONVERT_PROMPT.format(
        source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
        target_spec=json.dumps(target_spec, ensure_ascii=False, indent=2),
        instructions=instructions,
        sample_data=sample_data,
    )

    max_attempts = settings.max_retries

    for attempt in range(max_attempts):
        # 1. 调用 LLM 生成代码
        try:
            log.info("LLM call attempt %d/%d", attempt + 1, max_attempts)
            result = llm_client.chat_structured(
                system_prompt=prompts.SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as e:
            log.error("LLM call failed: %s", e)
            return {"success": False, "error": "LLM 调用失败: " + str(e), "retries": attempt}

        code = result.get("code", "")
        if not code:
            # 没有 code 字段，重试
            user_prompt = prompts.RETRY_PROMPT.format(
                previous_code="(无代码)",
                error_message="LLM 返回的 JSON 中缺少 code 字段",
                source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                instructions=instructions,
            )
            continue

        # 2. 安全扫描
        issues = sandbox.scan_code(code)
        log.debug("Code scan: %d issues found", len(issues))
        if issues:
            user_prompt = prompts.RETRY_PROMPT.format(
                previous_code=code,
                error_message="安全检查未通过: " + "; ".join(issues),
                source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                instructions=instructions,
            )
            continue

        # 3. 沙箱执行
        log.info("Executing generated code (attempt %d)...", attempt + 1)
        exec_result = sandbox.execute(code, source_df)
        log.debug("Sandbox result: success=%s", exec_result["success"])

        if exec_result["success"]:
            return {
                "success": True,
                "result_df": exec_result["dataframe"],
                "code": code,
                "explanation": result.get("explanation", ""),
                "column_mapping": result.get("column_mapping", {}),
                "retries": attempt,
            }

        # 4. 失败处理
        error_msg = exec_result["error"]

        # 判断是否是代码问题（可重试）
        code_errors = ("KeyError", "TypeError", "NameError", "SyntaxError",
                       "AttributeError", "IndexError", "ValueError")
        if any(e in error_msg for e in code_errors):
            if attempt < max_attempts - 1:
                user_prompt = prompts.RETRY_PROMPT.format(
                    previous_code=code,
                    error_message=error_msg,
                    source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                    instructions=instructions,
                )
                continue
            else:
                return {
                    "success": False,
                    "code": code,
                    "error": f"代码生成失败，已重试 {max_attempts} 次: {error_msg}",
                    "retries": attempt,
                }

        # 非代码错误 → 返回失败（可能是数据问题或系统问题）
        return {
            "success": False,
            "code": code,
            "error": error_msg,
            "retries": attempt,
        }

    return {"success": False, "error": f"代码生成失败，已重试 {max_attempts} 次", "retries": max_attempts}
