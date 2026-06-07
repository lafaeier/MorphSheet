import pandas as pd
from app.agent import sandbox


class TestSandboxScan:
    def test_safe_code_passes(self):
        code = '''
import pandas as pd
def transform(df):
    return df.dropna()
'''
        issues = sandbox.scan_code(code)
        assert issues == []

    def test_os_import_blocked(self):
        code = 'import os\ndef transform(df):\n    return df'
        issues = sandbox.scan_code(code)
        assert any('os' in i for i in issues)

    def test_subprocess_blocked(self):
        code = 'from subprocess import run\ndef transform(df):\n    return df'
        issues = sandbox.scan_code(code)
        assert len(issues) > 0

    def test_eval_blocked(self):
        code = 'def transform(df):\n    eval("1+1")\n    return df'
        issues = sandbox.scan_code(code)
        assert any('eval' in i for i in issues)

    def test_exec_blocked(self):
        code = 'def transform(df):\n    exec("x=1")\n    return df'
        issues = sandbox.scan_code(code)
        assert any('exec' in i for i in issues)

    def test_open_blocked(self):
        code = 'def transform(df):\n    open("/etc/passwd")\n    return df'
        issues = sandbox.scan_code(code)
        assert any('open' in i for i in issues)

    def test_sys_import_blocked(self):
        code = 'import sys\ndef transform(df):\n    return df'
        issues = sandbox.scan_code(code)
        assert any('sys' in i for i in issues)


class TestSandboxExecute:
    def test_valid_transform(self, sample_df):
        code = '''
import pandas as pd
def transform(df):
    df['age'] = pd.to_numeric(df['age'])
    return df
'''
        result = sandbox.execute(code, sample_df)
        assert result['success']
        assert len(result['dataframe']) == 3

    def test_no_transform_func(self, sample_df):
        result = sandbox.execute('x = 1', sample_df)
        assert not result['success']
        assert '未定义' in result['error']

    def test_timeout(self, sample_df):
        code = '''
def transform(df):
    while True:
        pass
    return df
'''
        result = sandbox.execute(code, sample_df, timeout=2)
        assert not result['success']
        assert '超时' in result['error']

    def test_wrong_return_type(self, sample_df):
        code = '''
def transform(df):
    return "not a dataframe"
'''
        result = sandbox.execute(code, sample_df)
        assert not result['success']
        assert 'DataFrame' in result['error']
