#!/usr/bin/env python3
"""RAG 系统测试脚本。"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_document_parser():
    """测试文档解析。"""
    from server.rag.document_parser import parse_document
    print("=== 测试文档解析 ===")
    print("✓ 模块导入成功")


async def test_language_detector():
    """测试语言检测。"""
    from server.rag.language_detector import detect_language
    print("\n=== 测试语言检测 ===")
    print("✓ 模块导入成功")

    test_texts = [
        ("Olá, como vai?", "pt"),
        ("Hello, how are you?", "en"),
        ("你好，世界", "zh"),
    ]
    for text, expected in test_texts:
        result = detect_language(text)
        print(f"  {text[:20]}... → {result} (expected: {expected})")


async def test_text_splitter():
    """测试文本切片。"""
    from server.rag.text_splitter import semantic_split
    print("\n=== 测试文本切片 ===")
    print("✓ 模块导入成功")

    text = """
    第一段内容。这是测试文本的第一部分。

    第二段内容。继续测试切片功能。

    第三段内容。这是最后一段。
    """
    chunks = semantic_split(text, chunk_size=50, overlap=10)
    print(f"  切片数：{len(chunks)}")


async def test_embedding():
    """测试 Embedding（需要 API Key）。"""
    from server.rag.embedding import get_embedding
    print("\n=== 测试 Embedding ===")

    import os
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("⚠ DASHSCOPE_API_KEY 未设置，跳过测试")
        return

    try:
        result = await get_embedding("测试文本")
        print(f"✓ Embedding 向量维度：{len(result)}")
    except Exception as e:
        print(f"✗ 测试失败：{e}")


async def test_vectorstore():
    """测试向量存储。"""
    from server.rag.vectorstore import RagVectorStore
    print("\n=== 测试向量存储 ===")
    print("✓ 模块导入成功")


async def main():
    """运行所有测试。"""
    print("RAG 系统测试\n")

    await test_document_parser()
    await test_language_detector()
    await test_text_splitter()
    await test_embedding()
    await test_vectorstore()

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())
