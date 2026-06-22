"""语言检测模块。"""

import logging
import re

logger = logging.getLogger("mobilerun.server")

# 语言代码映射（langdetect 返回标准化）
# langdetect 基于 ISO 639-1，理论上支持 100+ 语言
# 这里只列出常用映射，其他语言代码直接透传给下游（LLM 能理解）
LANGUAGE_MAP = {
    # 东亚
    "zh-cn": "zh", "zh-tw": "zh",  # 统一为 zh
    # 欧洲常见
    # langdetect 返回的已经是标准代码，直接透传即可
}


def _detect_by_charset(text: str) -> str | None:
    """通过字符集快速判断语言（适用于短文本）。

    Args:
        text: 输入文本

    Returns:
        语言代码，或 None（无法判断）
    """
    # 统计各类字符数量
    cjk_count = len(re.findall(r'[\u4e00-\u9fff]', text))  # CJK 统一汉字
    hiragana_count = len(re.findall(r'[\u3040-\u309f]', text))  # 日语平假名
    katakana_count = len(re.findall(r'[\u30a0-\u30ff]', text))  # 日语片假名
    korean_count = len(re.findall(r'[\uac00-\ud7af]', text))  # 韩文
    latin_count = len(re.findall(r'[a-zA-Z]', text))  # 拉丁字母

    total = cjk_count + hiragana_count + katakana_count + korean_count + latin_count
    if total == 0:
        return None

    # 日语：有假名字符
    if hiragana_count + katakana_count > 0:
        return "ja"
    # 韩语
    if korean_count > 0 and korean_count >= cjk_count:
        return "ko"
    # 中文：CJK 字符占主体（或全是 CJK）
    if cjk_count > 0 and cjk_count >= latin_count:
        return "zh"
    # 纯拉丁字母 → 需要 langdetect 进一步区分（pt/es/en）
    if latin_count > 0 and cjk_count == 0:
        return None  # 交给 langdetect

    return None


def detect_language(text: str) -> str:
    """检测文本语言。

    优先通过字符集判断（适合短文本），再用 langdetect 辅助。

    Args:
        text: 要检测的文本

    Returns:
        语言代码 (pt/zh/en 等)，检测失败返回 'unknown'
    """
    if not text or len(text.strip()) < 2:
        return "unknown"

    # 1. 字符集快速判断（对短文本特别有效）
    charset_lang = _detect_by_charset(text)
    if charset_lang:
        return charset_lang

    # 2. langdetect（适合拉丁字母语系区分：pt/es/en）
    try:
        from langdetect import detect

        result = detect(text)
        return LANGUAGE_MAP.get(result, result)
    except Exception as e:
        logger.warning(f"语言检测失败：{e}")
        return "unknown"


def detect_question_language(question: str) -> str:
    """检测用户提问的语言。

    Args:
        question: 用户问题

    Returns:
        语言代码
    """
    return detect_language(question)
