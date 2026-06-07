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
            return {"status": "cancelled"}

        # accept_suggestion / skip_row: 移除坏行后重新执行
        bad_rows = set()
        for issue in task.get("pending_issues", []):
            bad_rows.add(issue["row"])

        source_df = task["source_df"].copy()
        result_df = task["result_df"].copy()

        if bad_rows:
            # 从结果中删除坏行（索引基于结果 DataFrame）
            keep_mask = [i not in bad_rows for i in range(len(result_df))]
            clean_result = result_df[keep_mask].reset_index(drop=True)
        else:
            clean_result = result_df

        # 现在不需要脏数据检测了，直接生成 diff
        diff_data = diff_module.compute(source_df, clean_result)
        preview = schema_module.to_preview(clean_result)
        src_preview = schema_module.to_preview(source_df)

        task.update({
            "result_df": clean_result,
            "status": "awaiting_confirmation",
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
                         max_issues: int = 10) -> list[dict]:
    """扫描结果 DataFrame 中的 NaN/NaT，返回脏数据列表。"""
    issues = []
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        for i in range(len(result_df)):
            if len(issues) >= max_issues:
                break
            res_val = result_df.iloc[i][col]
            if pd.isna(res_val) or (isinstance(res_val, str) and ('NaT' in res_val or res_val == 'nan')):
                # 尝试从源数据获取原始值（基于位置近似匹配）
                src_val = "?"
                if i < len(source_df):
                    raw = source_df.iloc[i][col]
                    src_val = str(raw) if not pd.isna(raw) else "(空)"
                issues.append({
                    "row": i,
                    "column": str(col),
                    "value": src_val,
                    "error": "第{}行 \"{}\" 原始值 \"{}\" 无法转换".format(i, str(col), src_val),
                    "suggested_action": "跳过第{}行（原始值: {}）".format(i, src_val),
                })
    return issues


orchestrator = Orchestrator()
