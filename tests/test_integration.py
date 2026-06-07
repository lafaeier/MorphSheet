import pytest
import pytest_asyncio
import pandas as pd
import io
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.processing import diff, schema as schema_module


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def csv_bytes():
    df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'Diana'],
        'age': ['28', '35', '42', '31'],
        'salary': ['12000', '8500', '15000', '9200'],
    })
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding='utf-8')
    buf.seek(0)
    return buf


@pytest.mark.asyncio
async def test_upload_csv(client, csv_bytes):
    resp = await client.post('/api/upload', files={'file': ('test.csv', csv_bytes, 'text/csv')})
    assert resp.status_code == 200
    data = resp.json()
    assert data['filename'] == 'test.csv'
    assert data['schema_info']['row_count'] == 4


@pytest.mark.asyncio
async def test_upload_bad_format(client):
    resp = await client.post('/api/upload', files={'file': ('test.pdf', b'fake', 'application/pdf')})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get('/api/health')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'ok'


@pytest.mark.asyncio
async def test_root_html(client):
    resp = await client.get('/')
    assert resp.status_code == 200
    assert 'MorphSheet' in resp.text


@pytest.mark.asyncio
async def test_history_empty(client):
    resp = await client.get('/api/history')
    assert resp.status_code == 200
    assert 'tasks' in resp.json()


@pytest.mark.asyncio
async def test_skills_empty(client):
    resp = await client.get('/api/skills')
    assert resp.status_code == 200
    assert 'skills' in resp.json()


class TestDiffModule:
    def test_diff_basic(self):
        df1 = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'z']})
        df2 = pd.DataFrame({'a': [1, 3], 'b': ['x', 'z']})
        result = diff.compute(df1, df2)
        assert result['row_counts']['original'] == 3
        assert result['row_counts']['transformed'] == 2

    def test_diff_added_column(self):
        df1 = pd.DataFrame({'a': [1, 2]})
        df2 = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
        result = diff.compute(df1, df2)
        assert 'b' in result['added_columns']


class TestSchemaModule:
    def test_extract(self, sample_df):
        s = schema_module.extract(sample_df)
        assert s['row_count'] == 3
        assert 'name' in s['columns']

    def test_to_preview(self, sample_df):
        p = schema_module.to_preview(sample_df)
        assert len(p['rows']) == 3

    def test_to_json_safe_numpy(self):
        import numpy as np
        from app.processing.schema import to_json_safe
        data = {'val': np.int64(42), 'list': [np.float64(3.14)]}
        clean = to_json_safe(data)
        assert isinstance(clean['val'], int)
        assert isinstance(clean['list'][0], float)
