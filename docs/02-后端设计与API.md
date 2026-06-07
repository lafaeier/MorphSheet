# 02 — 后端设计与 API

## FastAPI 应用结构（app/main.py）

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from app.api.ws import router as ws_router

app = FastAPI(title="MorphSheet", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

FastAPI 负责：挂载静态前端文件、提供 REST API、WebSocket 端点。不做模板渲染，纯 JSON 通信。

## API 端点清单

### 1. 文件上传

```
POST /api/upload
  Content-Type: multipart/form-data
  Body: file (binary)
  Response 200:
  {
    "file_id": "uuid",
    "filename": "原始文件名.xlsx",
    "schema": {
      "columns": ["姓名", "年龄", "部门"],
      "dtypes": {"姓名": "object", "年龄": "int64", "部门": "object"},
      "row_count": 500,
      "sample": [{"姓名": "张三", "年龄": 28, "部门": "研发部"}, ...]
    },
    "preview": [[...], [...], ...]  // 前20行数据，用于前端预览
  }
```

后端动作：
1. 保存文件到 `data/uploads/{file_id}_{filename}`
2. 调用 `file_reader.read()` 读取为 DataFrame
3. 调用 `schema.extract()` 提取 Schema
4. 返回 file_id（后续所有操作使用 file_id 引用）

### 2. 设置目标格式

```
POST /api/set-target
  Body:
  {
    "file_id": "uuid",
    "target_format": "xlsx" | "xls" | "csv",
    "target_encoding": "utf-8" | "gbk" | "gb2312",  // csv 时必填
    "target_columns": ["Emp_Name", "Age", "Dept"],    // 可选，指定目标表头
    "column_types": {"Age": "int", "Emp_Name": "str"}  // 可选，指定目标列类型
  }
  Response 200:
  {
    "file_id": "uuid",
    "target_spec": {...}  // 完整的目标规格
  }
```

### 3. 执行转换（核心端点）

```
POST /api/convert
  Body:
  {
    "file_id": "uuid",
    "instructions": "删除所有金额小于0的行，将地址列拆分为省市区三列",
    "use_skill_id": null | "uuid"  // 可选：直接使用已有技能模板
  }
  Response 200 (成功，等待用户确认):
  {
    "status": "awaiting_confirmation",
    "task_id": "uuid",
    "preview": [[...], [...]],      // 转换后数据预览（前20行）
    "diff": {                        // Diff 数据
      "added_columns": ["省", "市", "区"],
      "removed_columns": ["地址"],
      "added_rows": [],
      "removed_rows": [12, 45, 78], // 被删除的行索引
      "modified_cells": [           // 被修改的单元格
        {"row": 3, "col": "电话", "old": "010-1234-5678", "new": "01012345678"}
      ]
    }
  }

  Response 200 (遇到脏数据，需要人工决策):
  {
    "status": "awaiting_human_confirmation",
    "task_id": "uuid",
    "detected_issues": [
      {
        "row": 45,
        "column": "员工电话",
        "value": "abc-def-ghij",
        "error": "包含非数字字符及格式异常",
        "suggested_action": "清除所有非数字字符后保留为 01012345678"
      }
    ],
    "partial_preview": [[...], [...]]
  }
```

### 4. 人工决策响应

```
POST /api/confirm-action
  Body:
  {
    "task_id": "uuid",
    "action": "accept_suggestion" | "skip_row" | "abort",
    "overrides": {                   // 可选：用户手动修改的值
      "45": {"员工电话": "01012345678"}
    }
  }
  Response 200:
  {
    "status": "continuing" | "completed",
    "next_state": {...}  // 同 convert 返回格式，继续等待或完成
  }
```

### 5. 确认导出

```
POST /api/export
  Body:
  {
    "task_id": "uuid",
    "save_as_skill": true | false,
    "skill_name": "我的技能名称"  // save_as_skill=true 时必填
  }
  Response 200:
  {
    "file_path": "data/outputs/uuid_converted.xls",
    "download_url": "/api/download/uuid",
    "skill_saved": true,
    "skill_id": "uuid"
  }
```

### 6. 文件下载

```
GET /api/download/{file_id}
  Response: binary file stream (Content-Disposition: attachment)
```

### 7. 历史记录

```
GET /api/history?limit=20&offset=0
  Response 200:
  {
    "tasks": [
      {
        "task_id": "uuid",
        "source_filename": "...",
        "target_format": "xls",
        "instructions": "...",
        "created_at": "ISO8601",
        "status": "completed" | "failed" | "cancelled"
      }
    ],
    "total": 50
  }
```

### 8. 技能库

```
GET /api/skills?limit=20
  Response 200:
  {
    "skills": [
      {
        "skill_id": "uuid",
        "name": "ERP → Legacy 系统",
        "description": "自动生成的描述",
        "source_schema_summary": "包含 姓名,年龄,部门 等 12 列",
        "target_format": "xls",
        "usage_count": 5,
        "created_at": "ISO8601"
      }
    ]
  }

DELETE /api/skills/{skill_id}
  Response 200: {"deleted": true}
```

### 9. 匹配技能（上传文件后自动调用）

```
POST /api/match-skills
  Body:
  {
    "file_id": "uuid"
  }
  Response 200:
  {
    "matches": [
      {
        "skill_id": "uuid",
        "skill_name": "ERP → Legacy 系统",
        "similarity": 0.92,
        "suggested_use": true
      }
    ]
  }
```

## WebSocket 端点

```
WS /ws/agent-status/{task_id}
```

服务端推送消息格式：

```json
// 思维链阶段更新
{"type": "phase", "phase": "analyzing_schema", "message": "正在分析源数据表结构..."}

// LLM 推理中
{"type": "phase", "phase": "generating_code", "message": "正在生成 Pandas 转换代码..."}

// 沙箱执行中
{"type": "phase", "phase": "executing", "message": "沙箱执行中...已处理 320/500 行"}

// 脏数据拦截
{"type": "blocking", "message": "在第 45 行发现异常数据，需要您的决策",
 "issues": [...]}

// 执行完成
{"type": "completed", "message": "转换完成，请查看 Diff 视图确认结果"}

// 错误
{"type": "error", "message": "代码生成失败，已重试 3 次", "detail": "..."}
```

## Pydantic 模型（app/api/schemas.py）

```python
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

class SchemaInfo(BaseModel):
    columns: list[str]
    dtypes: dict[str, str]
    row_count: int
    sample: list[dict[str, Any]]

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    schema: SchemaInfo
    preview: list[list[Any]]

class TargetSpec(BaseModel):
    file_id: str
    target_format: str          # "xlsx" | "xls" | "csv"
    target_encoding: str = "utf-8"
    target_columns: Optional[list[str]] = None
    column_types: Optional[dict[str, str]] = None

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
    status: str  # "awaiting_confirmation" | "awaiting_human_confirmation"
    task_id: str
    preview: Optional[list[list[Any]]] = None
    diff: Optional[dict] = None
    detected_issues: Optional[list[DataIssue]] = None

class ConfirmActionRequest(BaseModel):
    task_id: str
    action: str  # "accept_suggestion" | "skip_row" | "abort"
    overrides: Optional[dict[str, dict[str, Any]]] = None

class ExportRequest(BaseModel):
    task_id: str
    save_as_skill: bool = False
    skill_name: Optional[str] = None

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
```

## 错误处理模式

所有错误返回统一格式：

```json
{
  "error": true,
  "code": "FILE_TOO_LARGE",
  "message": "文件大小超过 50MB 限制",
  "detail": null
}
```

预定义错误码：
- `FILE_TOO_LARGE` — 文件超限
- `UNSUPPORTED_FORMAT` — 不支持的格式
- `FILE_NOT_FOUND` — file_id 无效
- `LLM_API_ERROR` — DeepSeek 调用失败
- `SANDBOX_TIMEOUT` — 代码执行超时
- `CODE_GENERATION_FAILED` — 3次重试后仍失败
- `TASK_NOT_FOUND` — task_id 无效

## 中间件

1. **请求大小限制**：FastAPI 默认限制 multipart 大小，在 `config.py` 中配置
2. **日志中间件**：记录每个请求的方法、路径、耗时、状态码
3. **任务状态管理**：内存字典 `tasks: dict[str, TaskState]` 跟踪所有进行中的任务（不做持久化，重启丢失无影响）
