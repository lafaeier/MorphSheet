import os
import sys
import pytest
import pytest_asyncio
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.processing import file_reader, file_writer, schema as schema_module


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': ['28', '35', '42'],
        'salary': ['10000', '20000', '15000'],
    })


@pytest.fixture
def temp_csv(sample_df, tmp_path):
    path = tmp_path / 'test.csv'
    sample_df.to_csv(path, index=False, encoding='utf-8')
    return str(path)


@pytest.fixture
def temp_xlsx(sample_df, tmp_path):
    path = tmp_path / 'test.xlsx'
    sample_df.to_excel(path, index=False, engine='openpyxl')
    return str(path)


@pytest.fixture
def temp_xls(sample_df, tmp_path):
    import xlwt
    path = tmp_path / 'test.xls'
    wb = xlwt.Workbook()
    ws = wb.add_sheet('Sheet1')
    for c, col_name in enumerate(sample_df.columns):
        ws.write(0, c, str(col_name))
    for r, (_, row) in enumerate(sample_df.iterrows()):
        for c, val in enumerate(row):
            ws.write(r + 1, c, str(val))
    wb.save(str(path))
    return str(path)
