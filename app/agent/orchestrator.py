import uuid
import pandas as pd
from app.processing import schema as schema_module, diff as diff_module, file_writer
from app.agent import code_generator


class Orchestrator:
    """Agent 主编排器：串联从上传到导出的完整流程。"""

    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.file_store: dict[str, dict] = {}

    def register_file(self, file_id: str, filename: str, file_path: str, df: pd.DataFrame):
        """注册已上传的文件。"""
        self.file_store[file_id] = {
            "filename": filename,
            "file_path": file_path,
            "df": df,
            "target_spec": None,
        }

    def get_file(self, file_id: str) -> dict | None:
        return self.file_store.get(file_id)

    def set_target(self, file_id: str, target_spec: dict):
        if file_id in self.file_store:
            self.file_store[file_id]["target_spec"] = target_spec

    def start_convert(self, file_id: str, instructions: str,
                      websocket_send=None) -> dict:
        """启动转换流程。返回任务状态给 API 层。"""
        file_entry = self.file_store.get(file_id)
        if not file_entry:
            return {"status": "failed", "error": "文件不存在"}

        source_df = file_entry["df"]
        target_spec = file_entry.get("target_spec") or {"target_format": "xlsx", "target_encoding": "utf-8"}

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "file_id": file_id,
            "source_df": source_df,
            "target_spec": target_spec,
            "result_df": None,
            "code": None,
            "status": "in_progress",
        }

        async def push(msg):
            if websocket_send:
                await websocket_send(msg)

        return self._run_convert(task_id, instructions, source_df, target_spec, websocket_send)

    def _run_convert(self, task_id: str, instructions: str,
                     source_df: pd.DataFrame, target_spec: dict,
                     websocket_send) -> dict:
        """执行转换的核心逻辑。"""

        def send(msg):
            if websocket_send:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(websocket_send(msg), loop)
                # If no event loop, just skip ws send silently

        # Phase: analyzing_schema
        send({"type": "phase", "phase": "analyzing_schema", "message": "正在分析源数据表结构..."})
        source_schema = schema_module.extract(source_df)
        sample = source_df.head(5).to_string()

        # Phase: generating_code
        send({"type": "phase", "phase": "generating_code", "message": "正在生成 Pandas 转换代码..."})
        result = code_generator.generate_and_execute(
            source_schema=source_schema,
            target_spec=target_spec,
            instructions=instructions,
            sample_data=sample,
            source_df=source_df,
        )

        if result["success"]:
            send({"type": "phase", "phase": "computing_diff", "message": "正在生成 Diff 对比..."})
            diff_data = diff_module.compute(source_df, result["result_df"])
            preview = schema_module.to_preview(result["result_df"])

            self.tasks[task_id].update({
                "result_df": result["result_df"],
                "code": result["code"],
                "status": "awaiting_confirmation",
            })

            send({"type": "completed", "message": "转换完成，请查看 Diff 视图确认结果"})
            return {
                "status": "awaiting_confirmation",
                "task_id": task_id,
                "preview": preview,
                "diff": diff_data,
            }

        # Failed
        send({"type": "error", "message": result.get("error", "未知错误")})
        self.tasks[task_id]["status"] = "failed"
        return {
            "status": "failed",
            "task_id": task_id,
            "error": result.get("error"),
        }

    def confirm_export(self, task_id: str, save_as_skill: bool = False,
                       skill_name: str = None) -> dict:
        """确认导出：将转换结果写入文件。"""
        task = self.tasks.get(task_id)
        if not task:
            return {"status": "failed", "error": "任务不存在"}
        if task.get("status") != "awaiting_confirmation":
            return {"status": "failed", "error": f"任务状态不正确: {task.get('status')}"}

        result_df = task["result_df"]
        target_spec = task["target_spec"]
        target_spec["task_id"] = task_id

        write_result = file_writer.write_with_warnings(result_df, target_spec)

        task["status"] = "completed"
        return {
            "status": "completed",
            "file_path": write_result["file_path"],
            "download_url": f"/api/download/{task_id}",
            "warnings": write_result["warnings"],
            "skill_saved": False,
        }

    def get_task(self, task_id: str) -> dict | None:
        return self.tasks.get(task_id)


# 全局单例
orchestrator = Orchestrator()
