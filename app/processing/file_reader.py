import pandas as pd
from pathlib import Path
import chardet


def read(file_path: str) -> pd.DataFrame:
    """统一读取入口：自动识别格式并读取为 DataFrame。

    支持格式：.xlsx, .xls, .csv
    CSV 自动检测编码。
    """
    ext = Path(file_path).suffix.lower()

    if ext == '.csv':
        return _read_csv(file_path)
    elif ext in ('.xlsx', '.xlsm'):
        return _read_xlsx(file_path)
    elif ext == '.xls':
        return _read_xls(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def _read_csv(file_path: str) -> pd.DataFrame:
    with open(file_path, 'rb') as f:
        raw = f.read(100000)
    detected = chardet.detect(raw)
    encoding = detected['encoding'] or 'utf-8'

    encodings_to_try = [encoding]
    if encoding.lower() not in ('utf-8', 'utf8'):
        encodings_to_try.extend(['utf-8', 'gbk', 'gb2312'])
    encodings_to_try.append('latin-1')

    for enc in encodings_to_try:
        try:
            df = pd.read_csv(file_path, encoding=enc, dtype=str)
            return df
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise ValueError(f"无法解码 CSV 文件，尝试了: {encodings_to_try}")


def _read_xlsx(file_path: str) -> pd.DataFrame:
    return pd.read_excel(file_path, engine='openpyxl', dtype=str)


def _read_xls(file_path: str) -> pd.DataFrame:
    return pd.read_excel(file_path, engine='xlrd', dtype=str)
