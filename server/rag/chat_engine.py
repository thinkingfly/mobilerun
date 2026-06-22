"""对话引擎模块 - RAG 问答核心逻辑。"""

import json
import logging
from datetime import datetime
from typing import Optional

from server.rag.language_detector import detect_question_language
from server.rag.retriever import RagRetriever
from server.langgraph.utils import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

logger = logging.getLogger("mobilerun.server")

# 语言代码 → 语言名称（覆盖常用语言，LLM 可直接理解）
LANG_NAMES = {
    # 东亚
    "zh": "中文", "zh-cn": "简体中文", "zh-tw": "繁体中文",
    "ja": "日语", "ko": "韩语", "vi": "越南语", "th": "泰语",
    # 欧洲
    "en": "英语", "es": "西班牙语", "pt": "葡萄牙语", "fr": "法语",
    "de": "德语", "it": "意大利语", "nl": "荷兰语", "ru": "俄语",
    "pl": "波兰语", "sv": "瑞典语", "da": "丹麦语", "no": "挪威语",
    "fi": "芬兰语", "tr": "土耳其语", "uk": "乌克兰语", "ro": "罗马尼亚语",
    "hu": "匈牙利语", "cs": "捷克语", "el": "希腊语", "bg": "保加利亚语",
    # 南亚/东南亚
    "hi": "印地语", "bn": "孟加拉语", "ta": "泰米尔语", "te": "泰卢固语",
    "id": "印尼语", "ms": "马来语", "tl": "菲律宾语",
    # 中东/非洲
    "ar": "阿拉伯语", "he": "希伯来语", "fa": "波斯语", "ur": "乌尔都语",
    "sw": "斯瓦希里语", "am": "阿姆哈拉语",
}


def get_lang_name(lang_code: str) -> str:
    """获取语言名称，未知语言直接返回代码（LLM 能理解 ISO 639-1 代码）。

    Args:
        lang_code: 语言代码（如 zh、pt、fr）

    Returns:
        语言名称
    """
    return LANG_NAMES.get(lang_code.lower(), lang_code)


async def call_llm(prompt: str) -> str:
    """调用 LLM 生成回答。

    Args:
        prompt: 提示词

    Returns:
        LLM 回答
    """
    if not LLM_API_KEY:
        return "错误：LLM_API_KEY 未配置"

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL
    )

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM 调用失败：{e}")
        return f"错误：{str(e)}"


async def translate_text(text: str, target_language: str = "zh") -> str:
    """翻译文本。

    支持任意语言，LLM 能理解 ISO 639-1 语言代码。

    Args:
        text: 原文本
        target_language: 目标语言代码（如 zh/en/pt/fr 等）

    Returns:
        翻译后的文本
    """
    lang_name = get_lang_name(target_language)

    prompt = f"""请将以下文本翻译成{lang_name}，保持原意：

{text}

翻译："""

    return await call_llm(prompt)


class RagChatEngine:
    """RAG 对话引擎。"""

    @staticmethod
    async def chat(
        question: str,
        session_id: str,
        source: str = "web",
        language: str = None,
        include_translation: bool = True
    ) -> dict:
        """RAG 问答。

        Args:
            question: 用户问题
            session_id: 会话 ID
            source: 来源 (wechat/whatsapp/web)
            language: 指定回答语言，None=自动检测
            include_translation: 是否包含翻译

        Returns:
            {
                answer: 回答内容,
                language: 使用的语言,
                source_docs: 引用来源文档列表,
                translation: 翻译内容（如有）
            }
        """
        # 1. 检测问题语言
        detected_lang = detect_question_language(question)
        answer_language = language or detected_lang

        # 如果检测失败，默认使用葡萄牙语
        if answer_language in ["unknown", "auto"]:
            answer_language = "pt"

        # 2. 检索相关文档（启用上下文扩展，增加 top_k 提高召回率）
        docs = await RagRetriever.retrieve(question, top_k=10, context_window=1)

        if not docs:
            return {
                "answer": "抱歉，没有找到相关的政策文档。",
                "language": answer_language,
                "source_docs": [],
                "translation": ""
            }

        # 3. 构建文档上下文
        doc_contexts = []
        for i, doc in enumerate(docs, 1):
            doc_contexts.append(
                f"[{i}] {doc.get('filename', '未知文档')}:\n{doc['chunk_text']}"
            )

        context_text = "\n\n".join(doc_contexts)

        # 4. 构建 Prompt（支持任意语言）
        lang_name = get_lang_name(answer_language)

        prompt = f"""基于以下政策文档内容，用{lang_name}回答用户问题。

回答要求：
- 用简短、口语化的方式回答，像朋友聊天一样自然
- 回答控制在 1-5 句话，不要写长段落
- 不要使用 markdown 格式（不要加粗、不要列表符号）
- 给出关键数字和核心信息
- 如果问题涉及分档、等级、阶梯等表格数据，必须完整列出所有档位（例如：10人=10美元，20人=20美元，30人=30美元...），不要只说范围
- 如果文档中没有相关信息，请只回复 [NO_INFO] 这一个标记

## 文档内容
{context_text}

## 用户问题
{question}

## 回答（{lang_name}）"""

        # 5. 生成回答
        answer = await call_llm(prompt)

        # 6. 构建来源文档信息
        source_docs = [
            {
                "doc_id": doc.get("doc_id"),
                "filename": doc.get("filename"),
                "chunk_text": doc.get("chunk_text", "")[:200] + "..." if len(doc.get("chunk_text", "")) > 200 else doc.get("chunk_text", ""),
                "score": doc.get("score")
            }
            for doc in docs
        ]

        # 7. 翻译（如果需要）
        translation = ""
        if include_translation and answer_language != "zh":
            try:
                translation = await translate_text(answer, "zh")
            except Exception as e:
                logger.warning(f"翻译失败：{e}")

        return {
            "answer": answer,
            "language": answer_language,
            "source_docs": source_docs,
            "translation": translation
        }
