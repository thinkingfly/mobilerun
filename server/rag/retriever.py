"""检索器模块 - 文档检索。"""

import logging
from typing import Optional

from server.rag.vectorstore import RagVectorStore

logger = logging.getLogger("mobilerun.server")


class RagRetriever:
    """RAG 文档检索器。"""

    @staticmethod
    async def retrieve(
        question: str,
        top_k: int = 5,
        doc_ids: list[int] = None,
        context_window: int = 1
    ) -> list[dict]:
        """检索相关文档切片。

        Args:
            question: 用户问题
            top_k: 返回结果数量
            doc_ids: 限定检索的文档 ID 列表
            context_window: 上下文窗口大小，检索到切片 N 后自动包含 N±1, N±2...

        Returns:
            检索结果 [{doc_id, filename, chunk_text, score}]
        """
        # 构建过滤条件
        filter_cond = None
        if doc_ids:
            filter_cond = {
                "$or": [{"doc_id": did} for did in doc_ids]
            }

        # 搜索
        results = await RagVectorStore.search(
            query=question,
            top_k=top_k,
            filter=filter_cond
        )

        # 如果有上下文窗口，扩展结果
        if context_window > 0 and results:
            results = await RagRetriever._expand_with_context(
                results, context_window, filter_cond
            )

        # 格式化结果
        formatted_results = []
        seen_chunks = set()  # 去重
        for r in results:
            metadata = r.get("metadata", {})
            chunk_key = (metadata.get("doc_id"), metadata.get("chunk_index"))
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)

            formatted_results.append({
                "doc_id": metadata.get("doc_id"),
                "filename": metadata.get("filename"),
                "chunk_text": r.get("document"),
                "chunk_index": metadata.get("chunk_index"),
                "score": r.get("score")
            })

        return formatted_results

    @staticmethod
    async def _expand_with_context(
        results: list[dict],
        context_window: int,
        filter_cond: dict = None
    ) -> list[dict]:
        """扩展检索结果，包含相邻切片。

        Args:
            results: 原始检索结果
            context_window: 上下文窗口大小
            filter_cond: 过滤条件

        Returns:
            扩展后的结果
        """
        # 收集需要获取的切片 ID
        needed_ids = set()
        result_map = {}  # id -> result

        for r in results:
            metadata = r.get("metadata", {})
            doc_id = metadata.get("doc_id")
            chunk_index = metadata.get("chunk_index", 0)
            result_id = f"{doc_id}_{chunk_index}"

            result_map[result_id] = r
            needed_ids.add(result_id)

            # 添加相邻切片的 ID
            for offset in range(-context_window, context_window + 1):
                if offset != 0:
                    neighbor_index = chunk_index + offset
                    if neighbor_index >= 0:
                        needed_ids.add(f"{doc_id}_{neighbor_index}")

        if not needed_ids:
            return results

        # 获取所有需要的切片
        try:
            all_chunks = await RagVectorStore.get_by_ids(list(needed_ids))
            for chunk in all_chunks:
                chunk_id = chunk.get("id")
                if chunk_id not in result_map:
                    result_map[chunk_id] = chunk
        except Exception as e:
            logger.warning(f"扩展上下文查询失败：{e}")

        # 按原始结果的顺序，插入相邻切片
        expanded_results = []
        seen_ids = set()

        for r in results:
            metadata = r.get("metadata", {})
            doc_id = metadata.get("doc_id")
            chunk_index = metadata.get("chunk_index", 0)

            # 按 chunk_index 排序，添加该文档的所有相邻切片
            neighbor_indices = []
            for offset in range(-context_window, context_window + 1):
                idx = chunk_index + offset
                if idx >= 0:
                    neighbor_id = f"{doc_id}_{idx}"
                    if neighbor_id in result_map and neighbor_id not in seen_ids:
                        neighbor_indices.append((idx, result_map[neighbor_id]))

            # 按 chunk_index 排序
            neighbor_indices.sort(key=lambda x: x[0])
            for idx, chunk in neighbor_indices:
                seen_ids.add(f"{doc_id}_{idx}")
                expanded_results.append(chunk)

        return expanded_results

    @staticmethod
    async def retrieve_by_session(
        question: str,
        session_id: str,
        source: str,
        top_k: int = 5
    ) -> list[dict]:
        """根据会话上下文检索文档。

        Args:
            question: 用户问题
            session_id: 会话 ID
            source: 来源 (wechat/whatsapp/web)
            top_k: 返回结果数量

        Returns:
            检索结果
        """
        # 获取群组配置的文档范围（如果有）
        # 这里简化处理，直接检索所有文档
        return await RagRetriever.retrieve(question, top_k)
