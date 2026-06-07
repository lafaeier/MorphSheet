from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class SchemaInfo(BaseModel):
    columns: list[str]
    dtypes: dict[str, str]
    row_count: int
    null_counts: dict[str, int]
    sample: list[dict[str, Any]]
    unique_counts: dict[str, int]
    numeric_columns: list[str]
    date_candidate_columns: list[str]


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    schema_info: SchemaInfo
    preview: dict  # {columns: [...], rows: [[...], ...]}


class TargetSpec(BaseModel):
    file_id: str
    target_format: str = Field(..., description="xlsx | xls | csv")
    target_encoding: str = "utf-8"
    target_columns: Optional[list[str]] = None
    column_types: Optional[dict[str, str]] = None


class TargetSpecResponse(BaseModel):
    file_id: str
    target_spec: TargetSpec


class ConvertRequest(BaseModel):
    file_id: str
    instructions: str
    use_skill_id: Optional[str] = None


class CellModification(BaseModel):
    row: int
    col: str
    old: Any
    new: Any


class DataIssue(BaseModel):
    row: int
    column: str
    value: Any
    error: str
    suggested_action: str


class ConvertResponse(BaseModel):
    status: str
    task_id: str
    preview: Optional[dict] = None
    diff: Optional[dict] = None
    detected_issues: Optional[list[DataIssue]] = None
    error: Optional[str] = None


class ConfirmActionRequest(BaseModel):
    task_id: str
    action: str = Field(..., description="accept_suggestion | skip_row | abort")
    overrides: Optional[dict[str, dict[str, Any]]] = None


class ExportRequest(BaseModel):
    task_id: str
    save_as_skill: bool = False
    skill_name: Optional[str] = None


class ExportResponse(BaseModel):
    file_path: str
    download_url: str
    warnings: list[str] = []
    skill_saved: bool = False
    skill_id: Optional[str] = None


class SkillInfo(BaseModel):
    skill_id: str
    name: str
    description: str
    source_schema_summary: str
    target_format: str
    usage_count: int
    created_at: datetime


class HistoryTask(BaseModel):
    task_id: str
    source_filename: str
    target_format: str
    instructions: str
    created_at: datetime
    status: str


class HistoryResponse(BaseModel):
    tasks: list[HistoryTask]
    total: int


class SkillsResponse(BaseModel):
    skills: list[SkillInfo]


class MatchSkillsResponse(BaseModel):
    matches: list[dict]


class ErrorResponse(BaseModel):
    error: bool = True
    code: str
    message: str
    detail: Optional[str] = None
