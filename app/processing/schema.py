import pandas as pd
import numpy as np


def extract(df: pd.DataFrame) -> dict:
    """从 DataFrame 提取 Schema 信息。"""
    schema = {
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "row_count": len(df),
        "null_counts": {col: int(df[col].isna().sum()) for col in df.columns},
    }

    sample_df = df.head(5).replace({np.nan: None, pd.NaT: None})
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

    return schema


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
