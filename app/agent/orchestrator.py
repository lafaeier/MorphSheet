import uuid
import pandas as pd
import numpy as np
from app.processing import schema as schema_module, diff as diff_module, file_writer
from app.agent import code_generator, sandbox
from app.processing.schema import to_json_safe
from app.storage import database
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
                      websocket_send=None, use_skill_id: str = None) -> dict:
        file_entry = self.file_store.get(file_id)
        if not file_entry:
            return {"status": "failed", "error": "文件不存在"}

        source_df = file_entry["df"].copy()
        target_spec = file_entry.get("target_spec") or {"target_format": "xlsx", "target_encoding": "utf-8"}

        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "file_id": file_id, "source_df": source_df,
            "target_spec": target_spec, "result_df": None,
            "code": None, "status": "in_progress",
            "instructions": instructions,
        }

        # 如果指定了技能，使用保存的代码直接执行
        if use_skill_id:
            skill = database.get_skill(use_skill_id)
            if skill:
                log.info("Using skill: id=%s name=%s", use_skill_id[:8], skill["name"])
                database.increment_skill_usage(use_skill_id)
                return self._run_skill(task_id, source_df, target_spec, skill, websocket_send)
            else:
                log.warning("Skill not found: %s", use_skill_id)

        log.info("Convert started: task=%s file=%s instructions=%s",
                 task_id[:8], file_id[:8], instructions[:80])
        return self._run_convert(task_id, instructions, source_df, target_spec, websocket_send)

    def _run_skill(self, task_id: str, source_df: pd.DataFrame,
                   target_spec: dict, skill: dict, websocket_send) -> dict:
        """使用已保存的技能代码直接执行转换。"""
        code = skill.get("code", "")
        if not code:
            return {"status": "failed", "task_id": task_id, "error": "技能中没有保存代码"}

        log.info("Running skill code: task=%s", task_id[:8])

        # 安全扫描
        issues = sandbox.scan_code(code)
        if issues:
            return {"status": "failed", "task_id": task_id,
                    "error": "技能代码安全检查未通过: " + "; ".join(issues)}

        # 沙箱执行
        exec_result = sandbox.execute(code, source_df)
        if not exec_result["success"]:
            log.error("Skill execution failed: %s", exec_result.get("error"))
            return {"status": "failed", "task_id": task_id,
                    "error": "技能执行失败: " + str(exec_result.get("error"))}

        result_df = exec_result["dataframe"]
        log.info("Skill success: task=%s rows=%d->%d", task_id[:8], len(source_df), len(result_df))

        # 预扫描 + 后置脏数据检测
        pre_issues = _pre_scan_source(source_df, "date amount")  # generic scan for skills
        dirty = _detect_coerced_data(source_df, result_df)
        seen = set()
        for d in dirty:
            seen.add((d["row"], d["column"]))
        for p in pre_issues:
            if (p["row"], p["column"]) not in seen:
                seen.add((p["row"], p["column"]))
                dirty.append(p)
        dirty.sort(key=lambda x: (x.get("row", 0), x.get("column", "")))
        if dirty:
            log.info("Skill: dirty data detected: %d issues", len(dirty))
            self.tasks[task_id].update({
                "result_df": result_df, "code": code,
                "status": "awaiting_human_confirmation",
                "pending_issues": dirty,
            })
            return to_json_safe({
                "status": "awaiting_human_confirmation",
                "task_id": task_id,
                "detected_issues": dirty,
            })

        diff_data = diff_module.compute(source_df, result_df)
        preview = schema_module.to_preview(result_df)
        src_preview = schema_module.to_preview(source_df)

        self.tasks[task_id].update({
            "result_df": result_df, "code": code,
            "status": "awaiting_confirmation",
        })

        return to_json_safe({
            "status": "awaiting_confirmation", "task_id": task_id,
            "preview": preview, "source_preview": src_preview,
            "diff": diff_data, "code": code,
            "explanation": "使用技能: " + skill.get("name", ""),
            "retries": 0,
        })

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

        # 预扫描: 在 LLM 代码执行前, 检查源数据中明显的问题值
        pre_scan_issues = _pre_scan_source(source_df, instructions)

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

            # 后置脏数据检测 + 合并预扫描结果
            dirty = _detect_coerced_data(source_df, result["result_df"])
            # 合并预扫描问题 (去重: 同一行+列只保留一个)
            seen = set()
            for d in dirty:
                seen.add((d["row"], d["column"]))
            for p in pre_scan_issues:
                key = (p["row"], p["column"])
                if key not in seen:
                    seen.add(key)
                    dirty.append(p)
                    if len(dirty) >= 30:
                        break
            dirty.sort(key=lambda x: (x.get("row", 0), x.get("column", "")))
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

        # 通过ID列匹配来移除坏行, 避免原始行号与结果行号错位
        source_df = task["source_df"].copy()
        result_df = task["result_df"].copy()

        # 查找ID列用于精确匹配
        id_col = _find_id_col(source_df, result_df)
        bad_ids = set()
        for issue in task.get("pending_issues", []):
            row_idx = issue["row"]
            col = issue.get("column", "")
            if col == "(整行)":
                continue
            if not issue.get("actionable", True):
                continue

            if id_col:
                # 优先从结果DataFrame查找 (后置扫描用结果行号)
                if row_idx < len(result_df):
                    id_val = str(result_df.iloc[row_idx][id_col])
                    bad_ids.add(id_val)
                # 回退到源DataFrame (预扫描用原始行号)
                elif row_idx < len(source_df):
                    id_val = str(source_df.iloc[row_idx][id_col])
                    bad_ids.add(id_val)
            else:
                bad_ids.add(str(row_idx))

        removed_count = 0
        if bad_ids and id_col:
            keep_mask = [str(result_df.iloc[i][id_col]) not in bad_ids for i in range(len(result_df))]
            removed_count = len(result_df) - sum(keep_mask)
            clean_result = result_df[keep_mask].reset_index(drop=True)
        else:
            clean_result = result_df

        log.info("Dirty data: task=%s action=%s removing %d rows (by %s)",
                 task_id[:8], action, removed_count, id_col or "index")

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
            "explanation": "已移除 " + str(removed_count) + " 个异常行",
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
                         max_issues: int = 30) -> list[dict]:
    """检测脏数据：NaN + 格式不匹配 + 空值 + 异常值 + 意外删除。
    所有 issue 都带 actionable=True，表示存在于结果中可操作。"""
    issues = []

    # 建立结果列 → 源列的映射 (处理 LLM 重命名列名的情况)
    col_map = {}  # {result_col: source_col or None}
    for rc in result_df.columns:
        if rc in source_df.columns:
            col_map[rc] = rc
        else:
            # 尝试按位置匹配 (列数相同时)
            rpos = list(result_df.columns).index(rc)
            if rpos < len(source_df.columns):
                col_map[rc] = source_df.columns[rpos]

    def _src_val(i, res_col):
        """安全获取源 DataFrame 中与结果列对应的值。"""
        sc = col_map.get(res_col)
        if sc and i < len(source_df):
            return source_df.iloc[i][sc]
        return None

    # ---- 0. 空值/空白检测 ----
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        for i in range(len(result_df)):
            if len(issues) >= max_issues:
                break
            res_val = result_df.iloc[i][col]
            if isinstance(res_val, str) and res_val.strip() == '':
                sv = _src_val(i, col)
                if sv is not None and str(sv).strip() != '':
                    issues.append({
                        "row": i, "column": str(col),
                        "value": str(sv)[:60],
                        "error": "第{}行 \"{}\" 原值 \"{}\" 转换后变为空字符串".format(i, str(col), str(sv)[:30]),
                        "suggested_action": "检查该行数据是否有效",
                    })

    # ---- 1. NaN/NaT 检测 ----
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        for i in range(len(result_df)):
            if len(issues) >= max_issues:
                break
            res_val = result_df.iloc[i][col]
            if pd.isna(res_val) or (isinstance(res_val, str) and 'NaT' in res_val):
                issues.append({
                    "row": i, "column": str(col),
                    "value": "NaN (转换失败)",
                    "error": "结果第{}行 \"{}\" 的值在转换后变为空".format(i, str(col)),
                    "suggested_action": "跳过此行，或通过对话补充指令修正",
                    "actionable": True,
                })

    # ---- 2. 格式不匹配检测 (每列检查) ----
    import re
    for col in result_df.columns:
        if len(issues) >= max_issues:
            break
        valid_vals = result_df[col].dropna()
        valid_strs = [str(v) for v in valid_vals if str(v).strip()]
        if len(valid_strs) < 5:
            continue

        patterns = {}
        for v in valid_strs[:100]:
            p = _classify_format(v)
            patterns[p] = patterns.get(p, 0) + 1
        if not patterns:
            continue
        dominant = max(patterns, key=patterns.get)
        dominant_pct = patterns[dominant] / len(valid_strs[:100])

        if dominant_pct > 0.6 and dominant not in ("mixed", "other"):
            for i in range(len(result_df)):
                if len(issues) >= max_issues:
                    break
                res_val = result_df.iloc[i][col]
                if pd.isna(res_val):
                    continue
                res_str = str(res_val).strip()
                if not res_str:
                    continue
                res_pat = _classify_format(res_str)
                if res_pat != dominant and res_pat not in ("empty",):
                    sv = _src_val(i, col)
                    src_str = str(sv)[:60] if sv is not None else "?"
                    issues.append({
                        "row": i, "column": str(col),
                        "value": src_str,
                        "error": "第{}行 \"{}\" 的值 \"{}\" 未正确转换 (期望格式: {}, 实际: {})".format(
                            i, str(col), res_str[:30], dominant, res_pat),
                        "suggested_action": "跳过此行，或通过对话补充指令修正 \"{}\" 的值".format(str(col)),
                        "actionable": True,
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
                        "actionable": False,  # 已从结果中删除, 仅展示信息
                    })

    issues.sort(key=lambda x: (x["row"], x["column"]))
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


def _pre_scan_source(df: pd.DataFrame, instructions: str) -> list[dict]:
    """在 LLM 执行前预扫描源数据，找出明显的问题值。
    即使这些行后续被其他操作(如删除空行)移除,
    也能在脏数据报告中体现出来。"""
    issues = []
    instr_lower = instructions.lower()

    # 检测日期列的明显非法值
    date_cols = _find_date_columns(df)
    for col in date_cols:
        for i in range(len(df)):
            if len(issues) >= 20:
                break
            val = str(df.iloc[i][col]).strip()
            if not val or val == 'nan':
                continue
            # 检测明显非法的日期值 (如 99999999, 00000000)
            import re
            if re.match(r'^\d{8}$', val):
                try:
                    y, m, d = int(val[:4]), int(val[4:6]), int(val[6:8])
                    if y < 1900 or y > 2100 or m < 1 or m > 12 or d < 1 or d > 31:
                        issues.append({
                            "row": i, "column": col,
                            "value": val,
                            "error": "源数据第{}行 \"{}\" = \"{}\" 为非法日期(超出合理范围)".format(i, col, val),
                            "suggested_action": "跳过此行或手动修正日期值",
                            "actionable": False,  # 预扫描问题，可能已被LLM代码处理
                        })
                except ValueError:
                    issues.append({
                        "row": i, "column": col,
                        "value": val,
                        "error": "源数据第{}行 \"{}\" = \"{}\" 为非法日期格式".format(i, col, val),
                        "suggested_action": "跳过此行或手动修正日期值",
                        "actionable": False,
                    })

    # 检测明显非法数值
    if 'amount' in instr_lower or '金额' in instructions or 'salary' in instr_lower or '工资' in instructions:
        num_cols = _find_numeric_columns(df)
        for col in num_cols:
            for i in range(len(df)):
                if len(issues) >= 20:
                    break
                val = str(df.iloc[i][col]).strip()
                if not val or val == 'nan':
                    continue
                # 检查是否包含非数字字符(排除常见分隔符)
                cleaned = val.replace(',', '').replace('¥', '').replace('$', '').replace(' ', '').replace('%', '')
                try:
                    float(cleaned)
                except ValueError:
                    issues.append({
                        "row": i, "column": col,
                        "value": val,
                        "error": "源数据第{}行 \"{}\" = \"{}\" 包含非数字字符".format(i, col, val),
                        "suggested_action": "跳过此行或手动修正数值",
                        "actionable": False,
                    })

    return issues


def _find_date_columns(df: pd.DataFrame) -> list[str]:
    """识别 DataFrame 中可能是日期列的列名。"""
    date_keywords = ['date', '日期', '时间', 'time', 'dt', '年月', '签约', '入职', 'birth', '生日']
    cols = []
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in date_keywords):
            cols.append(col)
    return cols


def _find_numeric_columns(df: pd.DataFrame) -> list[str]:
    """识别可能是数值列的列名。"""
    num_keywords = ['amount', '金额', 'salary', '工资', 'price', '价格', '数量', 'qty',
                    'money', '收入', '支出', '费用', 'cost', 'fee', '基本工资', '签约金额']
    cols = []
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in num_keywords):
            cols.append(col)
    return cols


def _find_id_col(source_df: pd.DataFrame, result_df: pd.DataFrame) -> str | None:
    """在两个DataFrame中找到ID列（可处理列名被重命名的情况）。"""
    common = set(source_df.columns) & set(result_df.columns)
    id_patterns = ['id', 'ID', '编号', '序号', 'code', 'Code', 'CUST', 'EMP',
                   '员工', '客户', '学号', '工号', 'no', 'NO', 'No', 'key', 'Key']
    # 1. 公共列中按模式匹配
    for col in common:
        col_lower = col.lower()
        for pat in id_patterns:
            if pat.lower() in col_lower:
                if source_df[col].nunique() == len(source_df):
                    return col
    # 2. 公共列中第一列为全唯一值
    common_list = [c for c in source_df.columns if c in common]
    if common_list:
        first_col = common_list[0]
        if source_df[first_col].nunique() == len(source_df):
            return first_col
    # 3. 列名被重命名 — 值重叠但列名不同，无法用单一列名索引两个DataFrame
    return None


orchestrator = Orchestrator()
