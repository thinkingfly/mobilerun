"""聊天 Bot 配置 — 管理支持的聊天 App 和读取模式。"""

# ── 读取模式常量 ──
READ_MODE_SCREENSHOT = "screenshot"         # 纯截图 + OCR（适用于微信等屏蔽无障碍的 App）
READ_MODE_ACCESSIBILITY = "accessibility"   # 无障碍服务读取 UI 树（更高效，适用于 WhatsApp 等）

# ── 支持的聊天 App 配置 ──
# key: App 名称（中文/英文）
# value: 配置信息
#   - source: 数据源标识（用于数据库存储）
#   - package_name: Android 包名
#   - keywords: 触发关键词列表
#   - read_mode: 聊天记录读取模式
CHAT_APP_REGISTRY: dict[str, dict] = {
    "微信": {
        "source": "wechat",
        "package_name": "com.tencent.mm",
        "keywords": ["微信", "WeChat", "wechat"],
        "read_mode": READ_MODE_SCREENSHOT,  # 微信屏蔽无障碍，必须用截图
    },
    "WhatsApp": {
        "source": "whatsapp",
        "package_name": "com.whatsapp",
        "keywords": ["WhatsApp", "whatsapp", "WA"],
        "read_mode": READ_MODE_ACCESSIBILITY,  # WhatsApp 支持无障碍，效率更高
    },
    # 后续可扩展更多聊天 App：
    # "QQ": {
    #     "source": "qq",
    #     "package_name": "com.tencent.mobileqq",
    #     "keywords": ["QQ", "qq"],
    #     "read_mode": READ_MODE_SCREENSHOT,
    # },
    # "Telegram": {
    #     "source": "telegram",
    #     "package_name": "org.telegram.messenger",
    #     "keywords": ["Telegram", "tg", "电报"],
    #     "read_mode": READ_MODE_ACCESSIBILITY,
    # },
    # "Line": {
    #     "source": "line",
    #     "package_name": "jp.naver.line.android",
    #     "keywords": ["Line", "line"],
    #     "read_mode": READ_MODE_ACCESSIBILITY,
    # },
}

# ── 聊天操作关键词 ──
# 当用户指令同时包含聊天 App 关键词和以下操作关键词时，触发 chat_bot_agent
CHAT_ACTION_KEYWORDS = [
    "回复", "自动回复", "聊天记录", "读取消息",
    "查看消息", "发消息", "聊天", "小bot",
    "自动聊天", "帮忙回复", "代回复",
]


def detect_chat_app(goal: str) -> tuple[str, dict] | None:
    """检测 goal 中是否包含聊天 App 关键词。

    Args:
        goal: 用户指令

    Returns:
        (app_name, app_config) 或 None
    """
    for app_name, config in CHAT_APP_REGISTRY.items():
        for keyword in config["keywords"]:
            if keyword in goal:
                return app_name, config
    return None


def is_chat_action(goal: str) -> bool:
    """检测 goal 是否包含聊天操作关键词。"""
    return any(kw in goal for kw in CHAT_ACTION_KEYWORDS)


def should_use_chat_bot(goal: str) -> tuple[bool, str | None, dict | None]:
    """判断是否应该使用 chat_bot_agent。

    同时满足以下条件时触发：
    1. goal 包含聊天 App 关键词（微信/WhatsApp 等）
    2. goal 包含聊天操作关键词（回复/记录/聊天 等）

    Args:
        goal: 用户指令

    Returns:
        (should_use, app_name, app_config)
    """
    app_result = detect_chat_app(goal)
    if app_result and is_chat_action(goal):
        app_name, app_config = app_result
        return True, app_name, app_config
    return False, None, None


def get_read_mode(source: str) -> str:
    """根据 source 获取读取模式。

    Args:
        source: 数据源标识（如 wechat, whatsapp）

    Returns:
        读取模式字符串
    """
    for config in CHAT_APP_REGISTRY.values():
        if config["source"] == source:
            return config.get("read_mode", READ_MODE_SCREENSHOT)
    return READ_MODE_SCREENSHOT


def get_package_name(source: str) -> str | None:
    """根据 source 获取 App 包名。

    Args:
        source: 数据源标识

    Returns:
        包名字符串或 None
    """
    for config in CHAT_APP_REGISTRY.values():
        if config["source"] == source:
            return config.get("package_name")
    return None


def get_source_by_keyword(goal: str) -> str | None:
    """根据用户指令中的关键词获取 source。

    Args:
        goal: 用户指令

    Returns:
        source 字符串或 None
    """
    result = detect_chat_app(goal)
    if result:
        _, config = result
        return config["source"]
    return None


def parse_target_chat(goal: str, app_name: str) -> str | None:
    """从用户指令中解析目标聊天对象。

    支持的格式：
    - "打开微信瞎聊群，查看聊天记录" -> "瞎聊群"
    - "打开微信，查看聊天记录" -> None
    - "在 WhatsApp 回复张三" -> "张三"
    - "帮我在微信回复李四" -> "李四"

    Args:
        goal: 用户指令
        app_name: App 名称（如 "微信"、"WhatsApp"）

    Returns:
        目标聊天对象名称，或 None
    """
    import re

    if not goal or not app_name:
        return None

    # 获取 App 的所有关键词
    app_config = None
    for name, config in CHAT_APP_REGISTRY.items():
        if name == app_name or config["source"] == app_name:
            app_config = config
            break

    if not app_config:
        return None

    # 找到 App 关键词在 goal 中的位置
    app_keyword_pos = -1
    app_keyword_len = 0
    for keyword in app_config["keywords"]:
        pos = goal.find(keyword)
        if pos >= 0:
            app_keyword_pos = pos
            app_keyword_len = len(keyword)
            break

    if app_keyword_pos < 0:
        return None

    # 提取 App 关键词之后的部分
    after_app = goal[app_keyword_pos + app_keyword_len:]

    # 移除常见的分隔符和动词
    # 例如："，"、" "、"回复"、"查看"、"打开" 等
    patterns_to_remove = [
        r'^[\s，,、]+',  # 开头的空白和分隔符
        r'^(回复|查看|打开|进入|找到|自动回复|聊天记录|查看聊天记录|查看消息)',  # 开头的动词
    ]

    cleaned = after_app
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned)

    # 再次移除开头的空白和分隔符
    cleaned = re.sub(r'^[\s，,、]+', '', cleaned)

    # 如果 cleaned 为空，说明没有指定聊天对象
    if not cleaned:
        return None

    # 提取聊天名称（到下一个动词、标点或结尾）
    # 匹配直到遇到：逗号、句号、动词、或常见的操作词
    stop_pattern = r'[\s，,。.、！!？?]+|(查看|回复|读取|发送|自动|记录|消息|聊天)'
    parts = re.split(stop_pattern, cleaned)

    if parts and parts[0]:
        target = parts[0].strip()
        # 去除末尾的助词/虚词
        target = re.sub(r'[的了呢吧吗啊哦嘛]+$', '', target)
        # 过滤掉太短或太长的结果
        if 1 <= len(target) <= 50:
            return target

    return None
