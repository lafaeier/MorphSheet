import os
import json
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from app.api.schemas import (
    UploadResponse, TargetSpec, TargetSpecResponse,
    ConvertRequest, ConvertResponse,
    ConfirmActionRequest, ExportRequest, ExportResponse,
    HistoryResponse, SkillsResponse, MatchSkillsResponse,
)
from app.processing import file_reader, schema as schema_module
from app.agent.orchestrator import orchestrator
from app.api.ws import send_to_task
from app.storage import database, skill_store
from app.config import settings

router = APIRouter()


def _ws_sender_for(task_id: str):
    """创建一个异步 WebSocket 发送函数，绑定到指定 task_id。"""
    async def send(msg: dict):
        await send_to_task(task_id, msg)
    return send


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('xlsx', 'xls', 'csv'):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: .{ext}")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件大小超过 {settings.max_upload_size_mb}MB 限制")

    file_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.data_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{file_id}_{file.filename}")
    with open(file_path, 'wb') as f:
        f.write(content)

    df = file_reader.read(file_path)
    schema_info = schema_module.extract(df)
    preview = schema_module.to_preview(df)

    orchestrator.register_file(file_id, file.filename, file_path, df)

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        schema_info=schema_info,
        preview=preview,
    )


@router.post("/set-target", response_model=TargetSpecResponse)
async def set_target(spec: TargetSpec):
    if not orchestrator.get_file(spec.file_id):
        raise HTTPException(status_code=404, detail="文件不存在")
    orchestrator.set_target(spec.file_id, spec.model_dump())
    return TargetSpecResponse(file_id=spec.file_id, target_spec=spec)


@router.post("/convert", response_model=ConvertResponse)
async def convert(req: ConvertRequest):
    if not orchestrator.get_file(req.file_id):
        raise HTTPException(status_code=404, detail="文件不存在")

    result = orchestrator.start_convert(
        file_id=req.file_id,
        instructions=req.instructions,
        websocket_send=None,  # Phase 3 前端 WebSocket 接入后替换
    )

    return ConvertResponse(**result)


@router.post("/confirm-action")
async def confirm_action(req: ConfirmActionRequest):
    task = orchestrator.get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if req.action == "abort":
        task["status"] = "cancelled"
        return {"status": "cancelled"}

    source_df = task["source_df"].copy()
    if req.overrides:
        for row_idx_str, col_updates in req.overrides.items():
            row_idx = int(row_idx_str)
            for col, new_val in col_updates.items():
                source_df.at[row_idx, col] = new_val

    task["source_df"] = source_df
    result = orchestrator.start_convert(
        file_id=task["file_id"],
        instructions="重新执行上次转换",
        websocket_send=None,
    )
    return result


@router.post("/export", response_model=ExportResponse)
async def export(req: ExportRequest):
    result = orchestrator.confirm_export(
        task_id=req.task_id,
        save_as_skill=req.save_as_skill,
        skill_name=req.skill_name,
    )
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result.get("error", "导出失败"))

    task = orchestrator.get_task(req.task_id)
    if task:
        file_entry = orchestrator.get_file(task.get("file_id", ""))
        src_filename = file_entry["filename"] if file_entry else ""
        # Record in history
        task_db_id = database.create_task(
            source_filename=src_filename,
            target_format=task.get("target_spec", {}).get("target_format", ""),
            instructions="export",
        )
        database.complete_task(
            task_db_id,
            status="completed",
            execution_code=task.get("code", ""),
        )

    # Save skill if requested
    skill_id = None
    if req.save_as_skill and task:
        file_entry = orchestrator.get_file(task.get("file_id", ""))
        src_schema = schema_module.extract(task["source_df"]) if task.get("source_df") is not None else {}
        skill_id = database.save_skill(
            name=req.skill_name or "未命名技能",
            description=f"自动保存: {src_filename}",
            source_schema=src_schema,
            target_spec=task.get("target_spec", {}),
            code=task.get("code", ""),
            column_mapping={},
        )
        skill_store.add_skill(skill_id, src_schema)
        result["skill_saved"] = True
        result["skill_id"] = skill_id

    return ExportResponse(**result)


@router.get("/download/{task_id}")
async def download(task_id: str):
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 尝试多种格式查找导出文件
    for ext in ('xlsx', 'xls', 'csv'):
        file_path = f"data/outputs/{task_id}_converted.{ext}"
        if os.path.exists(file_path):
            return FileResponse(file_path, filename=os.path.basename(file_path))
    raise HTTPException(status_code=404, detail="导出文件不存在")


@router.get("/history", response_model=HistoryResponse)
async def get_history(limit: int = 20, offset: int = 0):
    tasks = database.get_history(limit=limit, offset=offset)
    return HistoryResponse(
        tasks=[{
            "task_id": t["task_id"],
            "source_filename": t["source_filename"],
            "target_format": t["target_format"],
            "instructions": t["instructions"] or "",
            "created_at": t["created_at"],
            "status": t["status"],
        } for t in tasks],
        total=len(tasks),
    )


@router.get("/skills", response_model=SkillsResponse)
async def get_skills(limit: int = 20):
    skills = database.get_skills(limit=limit)
    return SkillsResponse(skills=[{
        "skill_id": s["skill_id"],
        "name": s["name"],
        "description": s["description"] or "",
        "source_schema_summary": _schema_summary(s["source_schema"]),
        "target_format": json.loads(s["target_spec"]).get("target_format", ""),
        "usage_count": s["usage_count"],
        "created_at": s["created_at"],
    } for s in skills])


@router.post("/match-skills", response_model=MatchSkillsResponse)
async def match_skills(req: dict):
    file_id = req.get("file_id", "")
    file_entry = orchestrator.get_file(file_id)
    if not file_entry:
        return MatchSkillsResponse(matches=[])
    schema_info = schema_module.extract(file_entry["df"])
    matches = skill_store.match_skills(schema_info)
    return MatchSkillsResponse(matches=matches)


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    database.delete_skill(skill_id)
    skill_store.remove_skill(skill_id)
    return {"deleted": True}


def _schema_summary(schema_json: str) -> str:
    try:
        s = json.loads(schema_json)
        cols = s.get("columns", [])[:8]
        return f"包含 {', '.join(cols)} 等 {len(s.get('columns',[]))} 列"
    except Exception:
        return ""


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
