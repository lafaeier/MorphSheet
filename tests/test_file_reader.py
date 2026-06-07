import pytest
from app.processing import file_reader


class TestFileReader:
    def test_read_csv(self, temp_csv):
        df = file_reader.read(temp_csv)
        assert len(df) == 3
        assert list(df.columns) == ['name', 'age', 'salary']

    def test_read_xlsx(self, temp_xlsx):
        df = file_reader.read(temp_xlsx)
        assert len(df) == 3

    def test_read_xls(self, temp_xls):
        df = file_reader.read(temp_xls)
        assert len(df) == 3

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="不支持的文件格式"):
            file_reader.read("test.pdf")

    def test_csv_encoding_gbk(self, tmp_path):
        import pandas as pd
        path = tmp_path / 'gbk.csv'
        df = pd.DataFrame({'col1': ['中文', '测试']})
        df.to_csv(path, index=False, encoding='gbk')
        result = file_reader.read(str(path))
        assert len(result) == 2

    def test_dtype_str_preserved(self, temp_csv):
        """读取后数据类型应为 str，防止自动类型转换丢失前导零。"""
        df = file_reader.read(temp_csv)
        assert str(df['age'].dtype) == 'object'
