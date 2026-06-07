import os
import pytest
import pandas as pd
from app.processing import file_writer, file_reader


class TestFileWriter:
    def test_write_xlsx(self, sample_df, tmp_path):
        path = str(tmp_path / 'out.xlsx')
        spec = {'target_format': 'xlsx', 'task_id': 'test'}
        result = file_writer.write(sample_df, spec)
        assert os.path.exists(result)
        df = file_reader.read(result)
        assert len(df) == len(sample_df)

    def test_write_xls(self, sample_df, tmp_path):
        path = str(tmp_path / 'out.xls')
        spec = {'target_format': 'xls', 'task_id': 'test'}
        result = file_writer.write(sample_df, spec)
        assert os.path.exists(result)
        df = file_reader.read(result)
        assert len(df) == len(sample_df)

    def test_write_csv_utf8_bom(self, sample_df, tmp_path):
        path = str(tmp_path / 'out.csv')
        spec = {'target_format': 'csv', 'task_id': 'test', 'target_encoding': 'utf-8'}
        result = file_writer.write(sample_df, spec)
        with open(result, 'rb') as f:
            assert f.read(3) == b'\xef\xbb\xbf'

    def test_write_csv_gbk(self, sample_df, tmp_path):
        path = str(tmp_path / 'out_gbk.csv')
        spec = {'target_format': 'csv', 'task_id': 'test', 'target_encoding': 'gbk'}
        result = file_writer.write(sample_df, spec)
        df = file_reader.read(result)
        assert len(df) == len(sample_df)

    def test_xls_truncation_warning(self, sample_df, tmp_path):
        big = pd.concat([sample_df] * 30000)
        path = str(tmp_path / 'big.xls')
        spec = {'target_format': 'xls', 'task_id': 'test'}
        result = file_writer.write_with_warnings(big, spec)
        assert len(result['warnings']) > 0
        assert '65535' in result['warnings'][0]

    def test_unsupported_format(self, sample_df):
        with pytest.raises(ValueError, match="不支持的目标格式"):
            file_writer.write(sample_df, {'target_format': 'pdf'})
