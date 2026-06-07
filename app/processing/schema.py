import re
import pandas as pd
import numpy as np
from collections import Counter


def extract(df: pd.DataFrame) -> dict:
    """从 DataFrame 提取 Schema 信息。"""
    schema = {
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "row_count": len(df),
        "null_counts": {col: int(df[col].isna().sum()) for col in df.columns},
    }

    # 样本扩大为 10 行，展示更多格式变体
    sample_df = df.head(10).replace({np.nan: None, pd.NaT: None})
    schema["sample"] = sample_df.to_dict(orient="records")

    schema["unique_counts"] = {
        col: int(df[col].nunique()) for col in df.columns
    }

    schema["numeric_columns"] = [
        col for col in df.columns
        if pd.to_numeric(df[col], errors='coerce').notna().sum() > len(df) * 0.8
    ]

    schema["date_candidate_columns"] = [
        col for col in df.columns
        if _looks_like_date(df[col])
    ]

    # 关键: 对每列做格式模式分析，帮助 LLM 理解数据多样性
    schema["column_patterns"] = {}
    for col in df.columns:
        patterns = _detect_patterns(df[col])
        if len(patterns) > 1:
            schema["column_patterns"][col] = patterns

    return schema


def _detect_patterns(series: pd.Series) -> list[dict]:
    """检测一列中不同值的格式模式，返回模式及示例。"""
    sample = series.dropna().head(50)
    if len(sample) == 0:
        return []

    patterns = Counter()
    examples = {}
    for val in sample:
        s = str(val)
        pat = _classify_pattern(s)
        patterns[pat] += 1
        if pat not in examples:
            examples[pat] = s

    if len(patterns) <= 1:
        return []

    total = sum(patterns.values())
    return [
        {
            "pattern": p,
            "count": c,
            "pct": round(c / total * 100, 1),
            "example": examples.get(p, ""),
        }
        for p, c in patterns.most_common()
    ]


def _classify_pattern(s: str) -> str:
    """将字符串值分类为格式模式。"""
    s = s.strip()
    if not s:
        return "EMPTY"
    # 日期格式
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return "YYYY-MM-DD"
    if re.match(r'^\d{4}/\d{2}/\d{2}$', s):
        return "YYYY/MM/DD"
    if re.match(r'^\d{4}年\d{1,2}月\d{1,2}日$', s):
        return "YYYY年M月D日"
    if re.match(r'^\d{8}$', s):
        if 1900 < int(s[:4]) < 2100:
            return "YYYYMMDD(date)"
        return "8digits"
    if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', s):
        return "YYYY-MM-DD HH:MM:SS"
    # 电话格式
    if re.match(r'^\d{3}-\d{4}-\d{4}$', s):
        return "XXX-XXXX-XXXX"
    if re.match(r'^\d{11}$', s):
        return "11digits"
    if re.match(r'^\(\d{3}\)\d{4}\d{4}$', s):
        return "(XXX)XXXXXXXX"
    if re.match(r'^\d{3}\s\d{4}\s\d{4}$', s):
        return "XXX XXXX XXXX"
    if re.match(r'^\d{3}-\d{7,8}$', s):
        return "XXX-XXXXXXX"
    # 货币格式
    if re.match(r'^¥[\d,]+$', s):
        return "¥with,comma"
    if re.match(r'^\d+\.\d{2}$', s):
        return "decimal.2"
    # 纯数字
    if re.match(r'^\d+$', s):
        return "integer"
    if re.match(r'^\d+\.\d+$', s):
        return "decimal"
    # 邮件
    if '@' in s and '.' in s.split('@')[-1]:
        return "email"
    # 混合/未知
    if any('一' <= c <= '鿿' for c in s):
        return "contains_chinese"
    return "other"


def _looks_like_date(series: pd.Series) -> bool:
    sample = series.dropna().head(20)
    if len(sample) == 0:
        return False
    success = 0
    for val in sample:
        try:
            pd.to_datetime(str(val))
            success += 1
        except (ValueError, TypeError):
            pass
    return success / len(sample) > 0.6


def _to_native(val):
    """将 NumPy 类型转为 Python 原生类型。"""
    if pd.isna(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def to_json_safe(obj):
    """递归转换对象中的所有 NumPy 类型为 Python 原生类型。"""
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if pd.isna(obj):
        return None
    return obj


def to_preview(df: pd.DataFrame, max_rows: int = 20) -> dict:
    """将 DataFrame 转为前端预览格式，所有值转为 Python 原生类型。"""
    preview_df = df.head(max_rows).replace({np.nan: None, pd.NaT: None})
    rows = [[_to_native(v) for v in row] for row in preview_df.values.tolist()]
    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
    }
