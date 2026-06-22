"""文本切片模块 - 语义切片。"""

import logging
import re

logger = logging.getLogger("mobilerun.server")


def semantic_split(
    text: str,
    chunk_size: int = 400,
    overlap: int = 50
) -> list[str]:
    """语义切片 - 按段落分割，保持语义完整性。

    Args:
        text: 原始文本
        chunk_size: 每个切片的目标字符数
        overlap: 切片之间的重叠字符数

    Returns:
        切片列表
    """
    if not text or not text.strip():
        return []

    # 按段落分割
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks = []
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        para_length = len(para)

        # 如果单个段落超过 chunk_size，强制分割
        if para_length > chunk_size:
            # 先保存当前 chunk
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_length = 0

            # 按句子分割长段落
            sentences = re.split(r'(?<=[.!?。！？])\s+', para)
            sentence_buffer = []
            sentence_length = 0

            for sentence in sentences:
                sentence_length += len(sentence)
                sentence_buffer.append(sentence)

                if sentence_length >= chunk_size:
                    chunks.append(" ".join(sentence_buffer))
                    # 保留重叠
                    if overlap > 0 and len(sentence_buffer) > 1:
                        sentence_buffer = sentence_buffer[-2:]
                    else:
                        sentence_buffer = []
                    sentence_length = 0

            if sentence_buffer:
                current_chunk.append(" ".join(sentence_buffer))
                current_length = len(" ".join(sentence_buffer))
            continue

        # 正常段落累加
        if current_length + para_length > chunk_size and current_chunk:
            # 保存当前 chunk
            chunks.append("\n\n".join(current_chunk))

            # 保留重叠部分
            if overlap > 0:
                # 从后往前累加，直到达到 overlap 大小
                overlap_chunks = []
                overlap_length = 0
                for p in reversed(current_chunk):
                    if overlap_length + len(p) <= overlap:
                        overlap_chunks.insert(0, p)
                        overlap_length += len(p)
                    else:
                        break
                current_chunk = overlap_chunks
                current_length = overlap_length
            else:
                current_chunk = []
                current_length = 0

        current_chunk.append(para)
        current_length += para_length

    # 保存最后一个 chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]
