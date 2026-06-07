import chromadb
from chromadb.utils import embedding_functions
from app.config import settings
from app.storage import database

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        _client = chromadb.PersistentClient(path=settings.chroma_db_dir)
        _collection = _client.get_or_create_collection(
            name="skill_schemas",
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        # Fallback: if ChromaDB fails (e.g., missing embedding model),
        # create a simple in-memory client
        _client = chromadb.Client()
        _collection = _client.get_or_create_collection(name="skill_schemas")
    return _collection


def schema_to_text(schema: dict) -> str:
    """将 Schema 转换为可 Embedding 的自然语言文本。"""
    cols = ", ".join(schema.get("columns", []))
    dtypes = ", ".join(f"{k}:{v}" for k, v in schema.get("dtypes", {}).items())
    return f"columns: {cols}. types: {dtypes}. rows: {schema.get('row_count', 0)}"


def add_skill(skill_id: str, source_schema: dict):
    """将技能的源 Schema 存入向量库。"""
    try:
        collection = _get_collection()
        text = schema_to_text(source_schema)
        collection.add(
            ids=[skill_id],
            documents=[text],
            metadatas=[{"skill_id": skill_id}],
        )
    except Exception:
        pass  # 向量存储失败不影响核心功能


def match_skills(source_schema: dict, top_k: int = 3, threshold: float = 0.5) -> list[dict]:
    """根据源 Schema 匹配最相似的技能模板。"""
    try:
        collection = _get_collection()
        if collection.count() == 0:
            return []

        query_text = schema_to_text(source_schema)
        results = collection.query(query_texts=[query_text], n_results=min(top_k, collection.count()))

        matches = []
        ids_list = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, skill_id in enumerate(ids_list):
            distance = distances[i] if i < len(distances) else 1.0
            similarity = round(1.0 - distance, 4)
            if similarity >= threshold:
                skill = database.get_skill(skill_id)
                if skill:
                    matches.append({
                        "skill_id": skill_id,
                        "skill_name": skill["name"],
                        "similarity": similarity,
                        "suggested_use": similarity >= 0.75,
                    })

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches
    except Exception:
        return []


def remove_skill(skill_id: str):
    """从向量库中删除技能。"""
    try:
        collection = _get_collection()
        collection.delete(ids=[skill_id])
    except Exception:
        pass
