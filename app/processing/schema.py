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


def to_preview(df: pd.DataFrame, max_rows: int = 20) -> dict:
    """将 DataFrame 转为前端预览格式。"""
    preview_df = df.head(max_rows).replace({np.nan: None, pd.NaT: None})
    return {
        "columns": list(df.columns),
        "rows": preview_df.values.tolist(),
    }
