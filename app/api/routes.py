import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.api.schemas import (
    UploadResponse, TargetSpec, TargetSpecResponse,
    ConvertRequest, ConvertResponse,
    ConfirmActionRequest, ExportRequest, ExportResponse,
    HistoryResponse, SkillsResponse, MatchSkillsResponse,
)
from app.processing import file_reader, schema as schema_module, diff as diff_module
from app.config import settings

router = APIRouter()

# 内存临时存储：file_id → {filename, file_path, df, target_spec, ...}
_file_store: dict[str, dict] = {}
# 任务存储：task_id → {file_id, status, result_df, code, ...}
_task_store: dict[str, dict] = {}


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

    _file_store[file_id] = {
        "filename": file.filename,
        "file_path": file_path,
        "df": df,
        "target_spec": None,
    }

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        schema_info=schema_info,
        preview=preview,
    )


@router.post("/set-target", response_model=TargetSpecResponse)
async def set_target(spec: TargetSpec):
    if spec.file_id not in _file_store:
        raise HTTPException(status_code=404, detail="文件不存在")
    _file_store[spec.file_id]["target_spec"] = spec
    return TargetSpecResponse(file_id=spec.file_id, target_spec=spec)


@router.post("/convert", response_model=ConvertResponse)
async def convert(req: ConvertRequest):
    # Phase 2 实现
    return ConvertResponse(
        status="not_implemented",
        task_id=str(uuid.uuid4()),
        error="Agent 核心将在 Phase 2 实现",
    )


@router.post("/confirm-action")
async def confirm_action(req: ConfirmActionRequest):
    # Phase 2 实现
    return {"status": "not_implemented"}


@router.post("/export", response_model=ExportResponse)
async def export(req: ExportRequest):
    # Phase 2 实现
    return ExportResponse(
        file_path="",
        download_url="",
        skill_saved=False,
    )


@router.get("/download/{file_id}")
async def download(file_id: str):
    # Phase 2 实现
    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/history", response_model=HistoryResponse)
async def get_history(limit: int = 20, offset: int = 0):
    return HistoryResponse(tasks=[], total=0)


@router.get("/skills", response_model=SkillsResponse)
async def get_skills(limit: int = 20):
    return SkillsResponse(skills=[])


@router.post("/match-skills", response_model=MatchSkillsResponse)
async def match_skills(req: dict):
    return MatchSkillsResponse(matches=[])


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    return {"deleted": True}


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
