# rag_client.py
# 知识库：把 txt / md 文档切片后存进 Chroma 向量库，做岗位分析时按语义检索相关片段。
# 向量由 sentence-transformers 本地计算，不需要联网调 embedding 接口。

import os
import re

CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join("data", "chroma"))
# 中文效果好、体积小的向量模型（首次运行会自动下载，约 100MB）
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
COLLECTION_NAME = "qiuzhao_kb"

_client = None
_collection = None


def get_collection():
    """懒加载 Chroma 集合 + 向量模型，整个进程只初始化一次。"""
    global _client, _collection
    if _collection is None:
        # 放在函数里导入，这样没装 chromadb 时其余功能（比如纯文本切分）也能正常用
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils import embedding_functions

        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False))
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL)
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"})
    return _collection


def split_text(text: str, chunk_size: int = 500, overlap: int = 60):
    """按段落尽可能完整地切块，块之间留一点重叠，避免答案被切断。"""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""

    for p in paragraphs:
        # 单段就超长，按字符硬切
        if len(p) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(p), chunk_size - overlap):
                chunks.append(p[i:i + chunk_size])
            continue

        if len(current) + len(p) + 1 <= chunk_size:
            current = f"{current}\n{p}".strip()
        else:
            chunks.append(current)
            current = p

    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def add_document(doc_id: int, doc_name: str, chunks):
    """把一份文档的所有切片写进向量库。"""
    if not chunks:
        return 0
    collection = get_collection()
    ids = [f"doc{doc_id}_{i}" for i in range(len(chunks))]
    collection.add(
        ids=ids,
        documents=chunks,
        metadatas=[{"doc_id": doc_id, "doc_name": doc_name, "chunk_index": i}
                   for i in range(len(chunks))],
    )
    return len(chunks)


def delete_document(doc_id: int, chunk_count: int):
    """删除一份文档对应的所有向量。"""
    ids = [f"doc{doc_id}_{i}" for i in range(int(chunk_count or 0))]
    if not ids:
        return
    try:
        get_collection().delete(ids=ids)
    except Exception:
        # 向量本来就不在（比如容器重启过），忽略即可
        pass


def count() -> int:
    return get_collection().count()


def search(query: str, top_k: int = 5):
    """按语义检索，返回 [{text, doc_name, chunk_index, distance}]。"""
    if not (query or "").strip():
        return []
    if count() == 0:
        return []

    result = get_collection().query(query_texts=[query], n_results=top_k)
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    items = []
    for i, text in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        items.append({
            "text": text,
            "doc_name": meta.get("doc_name", "未知"),
            "chunk_index": meta.get("chunk_index", 0),
            "distance": dists[i] if i < len(dists) else None,
        })
    return items


def rebuild_from_chunks(rows):
    """向量库为空但 SQLite 里有原文时，重建索引（容器重启后自动恢复用）。"""
    if not rows:
        return 0
    collection = get_collection()
    if collection.count() > 0:
        return collection.count()

    ids, docs, metas = [], [], []
    for r in rows:
        ids.append(f"doc{r['doc_id']}_{r['chunk_index']}")
        docs.append(r["text"])
        metas.append({"doc_id": r["doc_id"], "doc_name": r["name"],
                      "chunk_index": r["chunk_index"]})
    collection.add(ids=ids, documents=docs, metadatas=metas)
    return len(ids)
