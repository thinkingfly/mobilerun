"""Embedding 模块 - 阿里云 Qwen Embedding。"""

import logging
import os

from server.langgraph.utils import LLM_BASE_URL, LLM_API_KEY

logger = logging.getLogger("mobilerun.server")

# 使用全局 LLM 配置
EMBEDDING_MODEL = "text-embedding-v3"


async def get_embedding(text: str) -> list[float]:
    """获取单个文本的 Embedding 向量。

    Args:
        text: 输入文本

    Returns:
        Embedding 向量
    """
    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL
    )

    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )

    return response.data[0].embedding


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """批量获取 Embedding 向量。

    Args:
        texts: 文本列表

    Returns:
        Embedding 向量列表
    """
    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY 环境变量未设置")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL
    )

    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )

    # 按原始顺序排序
    embeddings = sorted(response.data, key=lambda x: x.index)
    return [e.embedding for e in embeddings]
