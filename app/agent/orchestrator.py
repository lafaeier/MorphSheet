import uuid
import pandas as pd
import numpy as np
from app.processing import schema as schema_module, diff as diff_module, file_writer
from app.agent import code_generator
from app.processing.schema import to_json_safe
from app.logger import get_logger

log = get_logger(__name__)


class Orchestrator:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.file_store: dict[str, dict] = {}

    def register_file(self, file_id: str, filename: str, file_path: str, df: pd.DataFrame):
        log.info("File registered: id=%s name=%s rows=%d cols=%d",
                 file_id[:8], filename, len(df), len(df.columns))
        self.file_store[file_id] = {
            "filename": filename, "file_path": file_path,
            "df": df, "target_spec": None,
        }

    def get_file(self, file_id: str) -> dict | None:
        return self.file_store.get(file_id)

    def set_target(self, file_id: str, target_spec: dict):
        if file_id in self.file_store:
            self.file_store[file_id]["target_spec"] = target_spec
            log.info("Target set: id=%s format=%s", file_id[:8], target_spec.get("target_format"))

    def start_convert(self, file_id: str, instructions: str,
                      websocket_send=None) -> dict:
        file_entry = self.file_store.get(file_id)
        if not file_entry:
            return {"status": "failed", "error": "文件不存在"}

        source_df = file_entry["df"].copy()
        target_spec = file_entry.get("target_spec") or {"target_format": "xlsx", "target_encoding": "utf-8"}

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "file_id": file_id,
            "source_df": source_df,
            "target_spec": target_spec,
            "result_df": None,
            "code": None,
            "status": "in_progress",
            "instructions": instructions,
        }

        log.info("Convert started: task=%s file=%s instructions=%s",
                 task_id[:8], file_id[:8], instructions[:80])
        return self._run_convert(task_id, instructions, source_df, target_spec, websocket_send)

    def _run_convert(self, task_id: str, instructions: str,
                     source_df: pd.DataFrame, target_spec: dict,
                     websocket_send) -> dict:
        def send(msg):
            if websocket_send:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(websocket_send(msg), loop)

        send({"type": "phase", "phase": "analyzing_schema", "message": "正在分析源数据表结构..."})
        source_schema = schema_module.extract(source_df)
        sample = source_df.head(15).to_string()
        log.debug("Schema extracted: columns=%s rows=%d patterns=%s",
                  source_schema["columns"], source_schema["row_count"],
                  list(source_schema.get("column_patterns", {}).keys()))

        send({"type": "phase", "phase": "generating_code", "message": "正在生成 Pandas 转换代码..."})
        log.info("Calling LLM for code generation...")
        result = code_generator.generate_and_execute(
            source_schema=source_schema, target_spec=target_spec,
            instructions=instructions, sample_data=sample, source_df=source_df,
        )

        if result["success"]:
            log.info("Convert success: task=%s retries=%d rows=%d->%d",
                     task_id[:8], result["retries"],
                     len(source_df), len(result["result_df"]))
            log.debug("Generated code:\n%s", result.get("code", "")[:2000])

            # 后置脏数据检测
            dirty = _detect_coerced_data(source_df, result["result_df"])
            if dirty:
                log.info("Dirty data detected: %d issues", len(dirty))
                send({"type": "blocking", "message": "发现异常数据，需要您的决策", "issues": dirty})
                self.tasks[task_id].update({
                    "result_df": result["result_df"],
                    "code": result["code"],
                    "status": "awaiting_human_confirmation",
                    "pending_issues": dirty,
                })
                return to_json_safe({
                    "status": "awaiting_human_confirmation",
                    "task_id": task_id,
                    "detected_issues": dirty,
                })

            send({"type": "phase", "phase": "computing_diff", "message": "正在生成 Diff 对比..."})
            diff_data = diff_module.compute(source_df, result["result_df"])
            preview = schema_module.to_preview(result["result_df"])
            src_preview = schema_module.to_preview(source_df)

            self.tasks[task_id].update({
                "result_df": result["result_df"],
                "code": result["code"],
                "status": "awaiting_confirmation",
            })

            send({"type": "completed", "message": "转换完成，请查看 Diff 视图确认结果"})
            return to_json_safe({
                "status": "awaiting_confirmation",
                "task_id": task_id,
                "preview": preview,
                "source_preview": src_preview,
                "diff": diff_data,
                "code": result.get("code", ""),
                "explanation": result.get("explanation", ""),
                "retries": result.get("retries", 0),
            })

        log.error("Convert failed: task=%s error=%s", task_id[:8], result.get("error", "unknown"))
        send({"type": "error", "message": result.get("error", "未知错误")})
        self.tasks[task_id]["status"] = "failed"
        return to_json_safe({
            "status": "failed", "task_id": task_id, "error": result.get("error"),
        })

    def handle_dirty_data(self, task_id: str, action: str) -> dict:
        """处理脏数据弹窗的用户决策。"""
        task = self.tasks.get(task_id)
        if not task or task.get("status") != "awaiting_human_confirmation":
            return {"status": "failed", "error": "任务状态不正确"}

        if action == "abort":
            task["status"] = "cancelled"
            log.info("Dirty data: task=%s aborted by user", task_id[:8])
            return {"status": "cancelled"}

        # accept_suggestion / skip_row: 移除坏行
        bad_rows = set()
        for issue in task.get("pending_issues", []):
            bad_rows.add(issue["row"])

        log.info("Dirty data: task=%s action=%s removing %d rows",
                 task_id[:8], action, len(bad_rows))

        source_df = task["source_df"].copy()
        result_df = task["result_df"].copy()

        if bad_rows:
            keep_mask = [i not in bad_rows for i in range(len(result_df))]
            clean_result = result_df[keep_mask].reset_index(drop=True)
        else:
            clean_result = result_df

        diff_data = diff_module.compute(source_df, clean_result)
        preview = schema_module.to_preview(clean_result)
        src_preview = schema_module.to_preview(source_df)

        task.update({
            "result_df": clean_result,
            "status": "awaiting_confirmation",
            "pending_issues": [],
        })

        return to_json_safe({
            "status": "awaiting_confirmation",
            "task_id": task_id,
            "preview": preview,
            "source_preview": src_preview,
            "diff": diff_data,
            "code": task.get("code", ""),
            "explanation": "已跳过 " + str(len(bad_rows)) + " 个异常行",
        })

    def confirm_export(self, task_id: str, save_as_skill: bool = False,
                       skill_name: str = None) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "failed", "error": "任务不存在"}
        if task.get("status") != "awaiting_confirmation":
            return {"status": "failed", "error": "任务状态不正确: " + str(task.get("status"))}

        result_df = task["result_df"]
        target_spec = dict(task["target_spec"])
        target_spec["task_id"] = task_id

        write_result = file_writer.write_with_warnings(result_df, target_spec)
        log.info("Export: task=%s path=%s", task_id[:8], write_result["file_path"])

        task["status"] = "completed"
        return {
            "status": "completed",
            "file_path": write_result["file_path"],
            "download_url": "/api/download/" + task_id,
            "warnings": write_result["warnings"],
            "skill_saved": False,
            "source_schema": schema_module.extract(task["source_df"]),
            "code": task.get("code", ""),
            "target_spec": target_spec,
        }

    def get_task(self, task_id: str) -> dict | None:
        return self.tasks.get(task_id)


def _detect_coerced_data(source_df: pd.DataFrame, result_df: pd.DataFrame,
                         max_issues: int = 20) -> list[dict]:
    """检测脏数据：NaN + 格式不匹配 + 意外删除。"""
    issues = []

    # ---- 1. NaN/NaT 检测 ----
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        for i in range(len(result_df)):
            if len(issues) >= max_issues:
                break
            res_val = result_df.iloc[i][col]
            if pd.isna(res_val) or (isinstance(res_val, str) and 'NaT' in res_val):
                src_val = str(source_df.iloc[i][col]) if i < len(source_df) else "?"
                issues.append({
                    "row": i, "column": str(col),
                    "value": src_val[:60],
                    "error": "第{}行 \"{}\" 原始值 \"{}\" 转换后变为空".format(i, str(col), src_val[:30]),
                    "suggested_action": "跳过此行，或通过对话补充指令修正",
                })

    # ---- 2. 格式不匹配检测 (每列检查) ----
    import re
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        # 取结果中非空值分析主导格式
        valid_vals = result_df[col].dropna()
        valid_strs = [str(v) for v in valid_vals if str(v).strip()]
        if len(valid_strs) < 5:
            continue

        # 判断该列的主导格式
        patterns = {}
        for v in valid_strs[:100]:
            p = _classify_format(v)
            patterns[p] = patterns.get(p, 0) + 1
        if not patterns:
            continue
        dominant = max(patterns, key=patterns.get)
        dominant_pct = patterns[dominant] / len(valid_strs[:100])

        # 如果主导格式占比超过 60%，检查不匹配的行
        if dominant_pct > 0.6 and dominant not in ("mixed", "other"):
            for i in range(len(result_df)):
                if len(issues) >= max_issues:
                    break
                res_val = result_df.iloc[i][col]
                if pd.isna(res_val):
                    continue  # already caught above
                res_str = str(res_val).strip()
                if not res_str:
                    continue
                res_pat = _classify_format(res_str)
                if res_pat != dominant and res_pat not in ("empty",):
                    src_val = str(source_df.iloc[i][col]) if i < len(source_df) else "?"
                    issues.append({
                        "row": i, "column": str(col),
                        "value": src_val[:60],
                        "error": "第{}行 \"{}\" 的值 \"{}\" 未正确转换 (期望格式: {}, 实际: {})".format(
                            i, str(col), res_str[:30], dominant, res_pat),
                        "suggested_action": "跳过此行，或通过对话补充指令修正 \"{}\" 的值".format(str(col)),
                    })

    # ---- 3. 意外删除检测 (通过ID列对比) ----
    id_col = None
    for c in source_df.columns:
        if c in result_df.columns:
            cl = c.lower()
            if 'id' in cl or '编号' in c:
                id_col = c
                break

    if id_col and len(issues) < max_issues:
        src_ids = set(source_df[id_col].dropna().astype(str))
        res_ids = set(result_df[id_col].dropna().astype(str))
        deleted = src_ids - res_ids
        # 只报告少量删除(可能是意外的), 大量删除是用户要求的
        if 0 < len(deleted) <= 30:
            for did in list(deleted)[:max_issues - len(issues)]:
                row_match = source_df[source_df[id_col].astype(str) == did]
                if len(row_match) > 0:
                    idx = row_match.index[0]
                    issues.append({
                        "row": int(idx), "column": "(整行)",
                        "value": str(row_match.iloc[0].to_dict())[:100],
                        "error": "第{}行 ({}={}) 在转换中被删除".format(int(idx), id_col, did),
                        "suggested_action": "该行可能因数据不完整被自动删除",
                    })

    return issues


def _classify_format(val: str) -> str:
    """分类值的格式模式。"""
    import re
    v = val.strip()
    if not v:
        return "empty"
    if re.match(r'^\d{4}-\d{2}-\d{2}$', v):
        return "YYYY-MM-DD"
    if re.match(r'^\d{8}$', v):
        return "YYYYMMDD"
    if re.match(r'^\d{4}/\d{2}/\d{2}$', v):
        return "YYYY/MM/DD"
    if re.match(r'^\d{4}年\d{1,2}月\d{1,2}日$', v):
        return "YYYY年M月D日"
    if re.match(r'^\d{11}$', v):
        return "11digits"
    if re.match(r'^\d{3}-\d{4}-\d{4}$', v):
        return "XXX-XXXX-XXXX"
    if re.match(r'^\d+\.\d{2}$', v):
        return "decimal.2"
    if re.match(r'^\d+$', v):
        return "integer"
    if '@' in v and '.' in v.split('@')[-1]:
        return "email"
    return "other"


orchestrator = Orchestrator()
