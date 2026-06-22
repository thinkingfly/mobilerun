"""向量存储模块 - ChromaDB。"""

import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("mobilerun.server")

# ChromaDB 持久化目录
CHROMA_DB_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_db"
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

# 全局客户端
_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def get_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端（单例）。"""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=Settings(anonymized_telemetry=False)
        )
    return _client


def get_collection() -> chromadb.Collection:
    """获取 ChromaDB Collection（单例）。"""
    global _collection
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name="rag_documents",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


class RagVectorStore:
    """RAG 向量存储操作类。"""

    @staticmethod
    async def add_documents(
        doc_id: int,
        chunks: list[str],
        metadata_list: list[dict]
    ) -> int:
        """添加文档切片到向量库。

        Args:
            doc_id: 文档 ID
            chunks: 切片文本列表
            metadata_list: 每个切片的元数据列表

        Returns:
            添加的切片数量
        """
        if not chunks:
            return 0

        collection = get_collection()

        # 生成 ID
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        # 添加文档
        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadata_list
        )

        logger.info(f"向量库添加文档 {doc_id}，共 {len(chunks)} 个切片")
        return len(chunks)

    @staticmethod
    async def search(
        query: str,
        top_k: int = 5,
        filter: dict = None
    ) -> list[dict]:
        """搜索相似文档。

        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter: 过滤条件

        Returns:
            搜索结果列表 [{id, document, metadata, score}]
        """
        collection = get_collection()

        # 查询
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=filter
        )

        # 格式化结果
        search_results = []
        if results and results["ids"]:
            for i in range(len(results["ids"][0])):
                search_results.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": results["distances"][0][i] if results.get("distances") else 0
                })

        return search_results

    @staticmethod
    async def get_by_ids(ids: list[str]) -> list[dict]:
        """按 ID 直接获取切片。

        Args:
            ids: 切片 ID 列表（格式：{doc_id}_{chunk_index}）

        Returns:
            切片列表 [{id, document, metadata}]
        """
        if not ids:
            return []

        collection = get_collection()

        results = collection.get(ids=ids, include=["documents", "metadatas"])

        chunks = []
        if results and results["ids"]:
            for i in range(len(results["ids"])):
                chunks.append({
                    "id": results["ids"][i],
                    "document": results["documents"][i],
                    "metadata": results["metadatas"][i]
                })

        return chunks

    @staticmethod
    async def delete_documents(doc_id: int) -> bool:
        """删除文档的所有切片。

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        collection = get_collection()

        # 查询该文档的所有 ID
        results = collection.get(
            where={"doc_id": doc_id}
        )

        if results and results["ids"]:
            collection.delete(ids=results["ids"])
            logger.info(f"向量库删除文档 {doc_id}，共 {len(results['ids'])} 个切片")
            return True

        return False

    @staticmethod
    async def delete_all() -> bool:
        """清空所有数据。"""
        global _collection
        client = get_client()
        try:
            client.delete_collection("rag_documents")
            _collection = None
            logger.info("向量库已清空")
            return True
        except Exception as e:
            logger.error(f"清空向量库失败：{e}")
            return False
