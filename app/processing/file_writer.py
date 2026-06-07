import pandas as pd
import xlwt
from pathlib import Path


def write(df: pd.DataFrame, target_spec: dict, output_dir: str = "data/outputs") -> str:
    """根据目标规格写出文件，返回输出文件路径。"""
    fmt = target_spec["target_format"]
    task_id = target_spec.get("task_id", "output")
    output_path = Path(output_dir) / f"{task_id}_converted.{fmt}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if fmt == "xlsx":
        return _write_xlsx(df, str(output_path))
    elif fmt == "xls":
        return _write_xls(df, str(output_path))
    elif fmt == "csv":
        encoding = target_spec.get("target_encoding", "utf-8")
        return _write_csv(df, str(output_path), encoding)
    else:
        raise ValueError(f"不支持的目标格式: {fmt}")


def write_with_warnings(df: pd.DataFrame, target_spec: dict) -> dict:
    """写文件并返回结果，包含兼容性警告。"""
    warnings = []
    fmt = target_spec["target_format"]
    df_out = df.copy()

    if fmt == "xls" and len(df_out) > 65535:
        truncated_rows = len(df_out) - 65535
        warnings.append(f"xls 格式最多支持 65535 行数据，已截断最后 {truncated_rows} 行")
        df_out = df_out.head(65535)

    if fmt == "xls" and len(df_out.columns) > 256:
        truncated_cols = len(df_out.columns) - 256
        warnings.append(f"xls 格式最多支持 256 列，已截断最后 {truncated_cols} 列")
        df_out = df_out.iloc[:, :256]

    # 截断过长单元格内容
    if fmt == "xls":
        for col in df_out.columns:
            df_out[col] = df_out[col].apply(
                lambda x: str(x)[:32767] if pd.notna(x) and len(str(x)) > 32767 else x
            )

    file_path = write(df_out, target_spec)

    return {
        "file_path": file_path,
        "warnings": warnings,
    }


def _write_xlsx(df: pd.DataFrame, path: str) -> str:
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return path


def _write_xls(df: pd.DataFrame, path: str) -> str:
    """使用 xlwt 直接写入 .xls 格式（Pandas 2.0+ 不再内置 xlwt 引擎）。"""
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Sheet1')

    for c, col_name in enumerate(df.columns):
        ws.write(0, c, str(col_name))

    for r, (_, row) in enumerate(df.iterrows()):
        for c, val in enumerate(row):
            if pd.isna(val):
                ws.write(r + 1, c, '')
            else:
                ws.write(r + 1, c, str(val))

    wb.save(path)
    return path


def _write_csv(df: pd.DataFrame, path: str, encoding: str) -> str:
    df.to_csv(
        path,
        index=False,
        encoding=encoding,
        lineterminator='\r\n',
        errors='replace',
    )
    if encoding.lower() in ('utf-8', 'utf8'):
        _prepend_bom(path)
    return path


def _prepend_bom(path: str):
    with open(path, 'r+b') as f:
        content = f.read()
        f.seek(0)
        f.write(b'\xef\xbb\xbf' + content)
