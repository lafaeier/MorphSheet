# 04 — Agent 核心与沙箱

## 执行流总览

```
  用户上传文件 + 自然语言指令
           │
           ▼
  ┌─────────────────────┐
  │ Step 1: Schema 提取  │  file_reader → schema.extract()
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │ Step 2: 意图理解     │  构建 Prompt（源Schema + 目标格式 + 用户指令）
  │         + 代码生成    │  → 调用 DeepSeek API → 返回 Pandas 代码
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │ Step 3: 代码安全扫描 │  AST 扫描检查危险 import/函数调用
  └────────┬────────────┘
           │ 通过
           ▼
  ┌─────────────────────┐
  │ Step 4: 沙箱执行     │  受限 namespace + 超时控制
  └────────┬────────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
  成功          失败
    │             │
    │        ┌────┴────┐
    │        ▼         ▼
    │     语法错误   数据异常
    │        │         │
    │    重试(<3次)  挂起→通知用户
    │        │         │
    │     ┌──┴──┐  用户决策→继续
    │     ▼     ▼      │
    │   成功  失败      │
    │           │       │
    │        报错终止   │
    ▼                   ▼
  ┌─────────────────────┐
  │ Step 5: 生成 Diff   │  diff.compute(原始df, 转换后df)
  └────────┬────────────┘
           │
           ▼
  ┌─────────────────────┐
  │ Step 6: 用户确认导出 │  用户确认 → file_writer → 可选保存技能
  └─────────────────────┘
```

## Prompt 模板设计

### 系统提示词（prompts.py）

```python
SYSTEM_PROMPT = """你是一个表格数据转换专家。你的任务是根据源数据的 Schema、目标格式要求、以及用户的自然语言指令，生成一段完整的 Python/Pandas 转换代码。

你需要生成的代码必须满足以下规范：

1. **函数签名**：代码中必须定义函数 `def transform(df: pd.DataFrame) -> pd.DataFrame:`
   - 输入 `df` 是源数据的 DataFrame
   - 返回值是转换后的 DataFrame

2. **数据清洗规则**：
   - 不要对源数据做没有明确要求的修改
   - 字段映射要基于语义理解（如"姓名"→"Emp_Name"）
   - 日期格式统一为 YYYY-MM-DD 字符串
   - 金额列保留 2 位小数

3. **异常处理**：
   - 如果遇到无法安全转换的数据（如将非数字字符串转为整数），使用 `pd.to_numeric(errors='coerce')`
   - 如果某列全部为 NaN 转换结果，标记该行为脏数据返回 None

4. **禁止操作**：
   - 禁止使用 `eval()`、`exec()`、`__import__()`
   - 禁止使用 `os`、`subprocess`、`pathlib`、`open()` 等文件系统模块
   - 只能使用 `pandas`、`numpy`、`datetime`、`re` 模块
   - 禁止读取或写入任何文件

5. **输出格式**：严格返回 JSON，包含以下字段：
   - `code`: 转换代码字符串
   - `explanation`: 代码逻辑的简要说明
   - `column_mapping`: 源列到目标列的映射字典
"""
```

### 主转换 Prompt

```python
CONVERT_PROMPT = """## 源数据 Schema
{source_schema}

## 目标格式要求
{target_spec}

## 用户自然语言指令
{instructions}

## 源数据前 5 行样本
{sample_data}

请生成 Pandas 转换代码，返回合法的 JSON 格式。"""
```

### 重试 Prompt

```python
RETRY_PROMPT = """## 上一次生成的代码执行失败

### 生成的代码
```python
{previous_code}
```

### 错误信息
```
{error_message}
```

### 源数据 Schema
{source_schema}

### 用户指令
{instructions}

请分析错误原因，修正代码，返回合法的 JSON 格式。
常见错误：
- KeyError: 列名不存在 → 检查实际列名是否正确
- TypeError: 类型不匹配 → 使用 pd.to_numeric(errors='coerce') 先转换
- ValueError: 数据格式问题 → 增加数据清洗步骤
"""
```

### 脏数据分析 Prompt

```python
DIRTY_DATA_PROMPT = """## 转换过程中遇到数据异常

### 异常详情
行号: {row}
列名: {column}
当前值: {value}
错误类型: {error_type}

### 上下文数据（异常行前后 3 行）
{context_data}

### 目标列要求
列名: {target_column}
期望类型: {expected_type}

请分析异常原因并给出建议：
1. 这是什么类型的数据问题？
2. 建议的修复方案是什么？
3. 修复后的值是什么？

返回 JSON 格式：
- issue_type: 问题分类
- suggested_action: 建议操作描述
- fixed_value: 建议修复后的值
"""
```

## DeepSeek API 调用封装（llm_client.py）

```python
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

def chat_structured(system_prompt: str, user_prompt: str, schema: dict) -> dict:
    """调用 DeepSeek API，使用 JSON Mode 返回结构化数据。

    注意：DeepSeek 支持 response_format={"type": "json_object"}，
    但 system prompt 中必须明确要求返回 JSON。
    """
    response = _client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt + "\n你必须返回合法的 JSON。"},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    import json
    return json.loads(response.choices[0].message.content)
```

## 代码生成器（code_generator.py）

```python
from app.agent import prompts, llm_client, sandbox
from app.config import settings
import json

def generate_and_execute(
    source_schema: dict,
    target_spec: dict,
    instructions: str,
    sample_data: str,
    source_df: "pd.DataFrame",
) -> dict:
    """
    生成代码并执行。最多重试 3 次。
    返回: {
        "success": bool,
        "result_df": pd.DataFrame | None,
        "code": str,
        "explanation": str,
        "column_mapping": dict,
        "error": str | None,
        "dirty_data": list | None,  # [{row, column, value, error, suggested_action}]
        "retries": int,
    }
    """

    user_prompt = prompts.CONVERT_PROMPT.format(
        source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
        target_spec=json.dumps(target_spec, ensure_ascii=False, indent=2),
        instructions=instructions,
        sample_data=sample_data,
    )

    for attempt in range(settings.max_retries):
        # 1. 调用 LLM
        try:
            result = llm_client.chat_structured(
                system_prompt=prompts.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema={...}  # code/explanation/column_mapping 的 JSON Schema
            )
        except Exception as e:
            return {"success": False, "error": f"LLM 调用失败: {e}", "retries": attempt}

        code = result.get("code", "")

        # 2. 安全扫描
        issues = sandbox.scan_code(code)
        if issues:
            # 不要立即失败，尝试让 LLM 重新生成
            user_prompt = prompts.RETRY_PROMPT.format(
                previous_code=code,
                error_message="安全检查未通过: " + "; ".join(issues),
                source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                instructions=instructions,
            )
            continue

        # 3. 沙箱执行
        exec_result = sandbox.execute(code, source_df)

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

        # 判断是语法错误还是数据异常
        if "KeyError" in error_msg or "TypeError" in error_msg or "SyntaxError" in error_msg:
            # 代码问题 → 重试
            user_prompt = prompts.RETRY_PROMPT.format(
                previous_code=code,
                error_message=error_msg,
                source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                instructions=instructions,
            )
            continue
        else:
            # 数据异常 → 分析脏数据
            dirty_data = _analyze_dirty_data(error_msg, code, source_df, source_schema)
            if dirty_data:
                return {
                    "success": False,
                    "dirty_data": dirty_data,
                    "code": code,
                    "error": "数据异常，需要人工决策",
                    "retries": attempt,
                }
            # 无法分类的错误 → 重试
            user_prompt = prompts.RETRY_PROMPT.format(
                previous_code=code,
                error_message=error_msg,
                source_schema=json.dumps(source_schema, ensure_ascii=False, indent=2),
                instructions=instructions,
            )
            continue

    return {"success": False, "error": f"代码生成失败，已重试 {settings.max_retries} 次", "retries": settings.max_retries}
```

## 沙箱实现（sandbox.py）

```python
import ast
import threading
from io import StringIO
from typing import Any
import pandas as pd
import numpy as np

# --- 禁止列表 ---
FORBIDDEN_IMPORTS = {
    'os', 'subprocess', 'shutil', 'sys', 'importlib', 'ctypes',
    'socket', 'http', 'urllib', 'requests', 'pathlib', 'glob',
    'pickle', 'marshal', 'code', 'codeop', 'io', 'fileinput',
    'signal', 'multiprocessing', 'threading', 'concurrent',
}

FORBIDDEN_CALLS = {
    '__import__', 'exec', 'eval', 'compile', 'open', 'input',
    'globals', 'locals', 'vars', 'dir', 'getattr', 'setattr',
    'breakpoint', '__builtins__', 'exit', 'quit',
}

FORBIDDEN_ATTRS = {
    '__class__', '__bases__', '__mro__', '__subclasses__',
    '__globals__', '__code__', '__closure__', '__dict__',
}


def scan_code(code: str) -> list[str]:
    """AST 静态扫描，返回发现的安全问题列表。"""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误: {e}"]

    for node in ast.walk(tree):
        # 检查 import
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split('.')[0]
                if root in FORBIDDEN_IMPORTS:
                    issues.append(f"禁止导入模块: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split('.')[0]
                if root in FORBIDDEN_IMPORTS:
                    issues.append(f"禁止导入模块: {node.module}")

        # 检查函数调用
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                issues.append(f"禁止调用: {node.func.id}()")

        # 检查属性访问（防止 __class__.__bases__ 等逃逸）
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                issues.append(f"禁止访问属性: .{node.attr}")

    return issues


def execute(code: str, source_df: pd.DataFrame, timeout: int = 30) -> dict:
    """
    在受限环境中执行生成的 Pandas 代码。

    参数:
        code: LLM 生成的 Python 代码（含 transform 函数定义）
        source_df: 源 DataFrame
        timeout: 超时秒数

    返回:
        {"success": bool, "dataframe": pd.DataFrame|None, "error": str|None}
    """
    imports_ok, scan_issues = scan_code(code)
    if scan_issues:
        return {"success": False, "error": "安全扫描不通过:\n" + "\n".join(scan_issues)}

    # 构建安全的全局命名空间
    safe_globals = {
        '__builtins__': {
            'True': True, 'False': False, 'None': None,
            'int': int, 'float': float, 'str': str, 'bool': bool,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'len': len, 'range': range, 'enumerate': enumerate,
            'zip': zip, 'map': map, 'filter': filter,
            'sorted': sorted, 'reversed': reversed,
            'min': min, 'max': max, 'sum': sum, 'abs': abs,
            'round': round, 'pow': pow, 'divmod': divmod,
            'print': print, 'type': type,
            'isinstance': isinstance, 'issubclass': issubclass,
            'Exception': Exception, 'ValueError': ValueError,
            'TypeError': TypeError, 'KeyError': KeyError,
            'AttributeError': AttributeError, 'IndexError': IndexError,
            'StopIteration': StopIteration,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'complex': complex, 'bytes': bytes, 'bytearray': bytearray,
            'repr': repr, 'hash': hash, 'id': id,
            'format': format, 'slice': slice,
        },
        'pd': pd,
        'np': np,
        're': __import__('re'),
        'datetime': __import__('datetime'),
    }

    local_vars = {'df': source_df.copy()}

    result = {"success": False, "dataframe": None, "error": None}

    def target():
        try:
            stdout = StringIO()
            safe_globals['__builtins__']['print'] = lambda *a, **kw: print(*a, **kw, file=stdout)
            exec(code, safe_globals, local_vars)
            if 'transform' not in local_vars:
                result["error"] = "代码中未定义 transform(df) 函数"
                return
            output = local_vars['transform'](local_vars['df'])
            if not isinstance(output, pd.DataFrame):
                result["error"] = f"transform() 返回值必须是 DataFrame，实际为 {type(output)}"
                return
            result["success"] = True
            result["dataframe"] = output
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return {"success": False, "error": f"代码执行超时 ({timeout}s)"}

    return result
```

## 脏数据检测策略

当沙箱执行报错且不是代码问题时，需要分析是否为脏数据导致的：

1. **数值转换失败**：`pd.to_numeric()` 返回 NaN → 原始数据包含非数字字符
2. **日期解析失败**：`pd.to_datetime()` 报错 → 日期格式不标准
3. **字符串截断风险**：目标列要求定长但源数据超长
4. **必需列缺失**：某行在关键列上为 NaN

检测方法：在安全环境中，逐行/逐列对源数据做预校验，将不符合目标类型约束的行标记出来。这个预校验逻辑也用 LLM 生成的代码实现——即 Agent 首先生成"数据校验代码"，校验通过后再生成"转换代码"。这是一个可选的优化，初版可以直接在执行失败后分析。

## orchestrator.py 主编排器

```python
from app.processing import file_reader, file_writer, schema, diff
from app.agent import code_generator
from app.storage import database, skill_store
import pandas as pd

class AgentOrchestrator:
    """主编排器：串联从上传到导出的完整流程。"""

    def __init__(self):
        self.tasks: dict[str, dict] = {}  # task_id → 任务状态（内存）

    def handle_upload(self, file_path: str) -> dict:
        """Step 1: 读取文件，提取 Schema"""
        df = file_reader.read(file_path)
        return schema.extract(df)

    def handle_convert(self, file_id: str, instructions: str, 
                       target_spec: dict, websocket_send) -> dict:
        """Step 2-4: 生成代码、执行、返回结果"""
        task_id = self._create_task(file_id)
        source_df = self._get_source_df(file_id)

        # 通过 WebSocket 推送阶段
        websocket_send({"type": "phase", "phase": "analyzing_schema"})
        source_schema = schema.extract(source_df)
        sample = source_df.head(5).to_string()

        websocket_send({"type": "phase", "phase": "generating_code"})
        result = code_generator.generate_and_execute(
            source_schema=source_schema,
            target_spec=target_spec,
            instructions=instructions,
            sample_data=sample,
            source_df=source_df,
        )

        if result["success"]:
            websocket_send({"type": "phase", "phase": "computing_diff"})
            diff_data = diff.compute(source_df, result["result_df"])
            self.tasks[task_id]["result_df"] = result["result_df"]
            self.tasks[task_id]["code"] = result["code"]
            return {
                "status": "awaiting_confirmation",
                "task_id": task_id,
                "preview": result["result_df"].head(20).values.tolist(),
                "diff": diff_data,
            }

        if result.get("dirty_data"):
            websocket_send({"type": "blocking", "issues": result["dirty_data"]})
            return {
                "status": "awaiting_human_confirmation",
                "task_id": task_id,
                "detected_issues": result["dirty_data"],
            }

        websocket_send({"type": "error", "message": result.get("error")})
        return {"status": "failed", "task_id": task_id, "error": result.get("error")}

    def handle_confirm(self, task_id: str, action: str, overrides: dict) -> dict:
        """Step 5: 处理人工决策"""
        # 根据 action 调整数据或继续/终止
        ...

    def handle_export(self, task_id: str, save_as_skill: bool, skill_name: str) -> dict:
        """Step 6: 写文件 + 可选保存技能"""
        task = self.tasks[task_id]
        result_df = task["result_df"]
        target_spec = task["target_spec"]
        file_path = file_writer.write(result_df, target_spec)
        if save_as_skill:
            skill_store.save(task, skill_name)
            database.record_history(task, "completed")
        return {"file_path": file_path}
```
