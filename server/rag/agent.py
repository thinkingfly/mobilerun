"""RAG Agent - 政策文档智能问答 Agent。"""

import logging

from server.langgraph.agents.base import BaseAgent, AgentContext, AgentResult

logger = logging.getLogger("mobilerun.server")

# 政策相关关键词（包含带重音符号的葡萄牙语版本）
POLICY_KEYWORDS = [
    # 中文
    "政策", "规则", "薪资", "工资", "提现", "佣金", "奖励",
    "钻石", "任务", "主播", "招聘", "培训", "级别", "等级",
    # 葡萄牙语（无重音）
    "politica", "salario", "regra", "comissao", "diamante",
    "saque", "bonus", "nivel", "transmissao", "presente",
    "hora", "ao vivo", "streaming", "pix", "retirada",
    "tarefa", "ancora", "agencia",
    # 葡萄牙语（有重音）
    "política", "salário", "regras", "comissão", "diamantes",
    "saque", "bônus", "nível", "transmissão", "presente",
    "horas", "ao vivo", "streaming", "pix", "retirada",
    "tarefa", "âncora", "agência",
    # 英语
    "policy", "salary", "commission", "withdrawal", "rule",
    "diamond", "bonus", "level", "streaming", "gift",
    "hours", "live", "task", "anchor", "agency",
]


def is_policy_related(message: str) -> bool:
    """判断消息是否与政策相关。

    Args:
        message: 用户消息

    Returns:
        是否相关
    """
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in POLICY_KEYWORDS)


class RagAgent(BaseAgent):
    """RAG 政策问答 Agent。"""

    name = "rag_agent"
    description = "政策文档智能问答，回答关于薪资、规则、提现、佣金等政策相关问题"

    def can_handle(self, parsed_intent: str, message: str) -> bool:
        """判断是否能处理该消息。

        Args:
            parsed_intent: 解析的意图
            message: 用户消息

        Returns:
            是否能处理
        """
        # 意图为 chat 且包含政策相关关键词
        if parsed_intent == "chat" and is_policy_related(message):
            return True
        return False

    async def execute(self, context: AgentContext) -> AgentResult:
        """执行 RAG 问答。

        Args:
            context: Agent 上下文

        Returns:
            Agent 执行结果
        """
        from server.rag.chat_engine import RagChatEngine

        message = context.user_message

        try:
            # 调用对话引擎
            result = await RagChatEngine.chat(
                question=message,
                session_id=context.agent_id or "default",
                source="web"
            )

            # 构建回复
            answer = result["answer"]

            # 如果有翻译，附加上
            if result.get("translation"):
                answer += f"\n\n[中文翻译]\n{result['translation']}"

            # 日志打印引用来源
            source_docs = result.get("source_docs", [])
            if source_docs:
                logger.info(f"RAG 引用来源：{len(source_docs)} 个文档片段")
                for doc in source_docs[:3]:  # 只打印前 3 个
                    logger.info(f"  - {doc.get('filename')}: {doc.get('chunk_text', '')[:100]}...")

            return AgentResult(
                success=True,
                response=answer,
                data={
                    "language": result.get("language"),
                    "source_docs_count": len(source_docs)
                }
            )

        except Exception as e:
            logger.error(f"RAG Agent 执行失败：{e}")
            return AgentResult(
                success=False,
                response=f"抱歉，查询失败：{str(e)}"
            )


# 自注册：当此模块被导入时，自动注册到 Agent 注册表
def _register():
    """注册 RagAgent 到全局注册表。

    使用延迟导入避免循环导入问题。
    """
    try:
        from server.langgraph.agents.registry import registry
        # 避免重复注册
        if 'rag_agent' not in registry._agents:
            registry.register(RagAgent())
    except Exception:
        pass  # 注册表可能尚未初始化


_register()
