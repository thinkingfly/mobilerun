"""Python Skill base class.

Users can subclass ``SkillBase`` to define skills with arbitrary Python logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from mobilerun.agent.action_context import ActionContext
    from mobilerun.agent.action_result import ActionResult


class SkillBase(ABC):
    """Base class for Python-defined skills.

    Subclass this and implement ``parameters()`` and ``execute()``.
    The skill will be automatically registered with the tool registry.
    """

    name: str = "unnamed_skill"
    description: str = "A custom skill"

    def parameters(self) -> Dict[str, Any]:
        """Return parameter definitions for the tool registry.

        Returns:
            Dict mapping param name → {"type": str, "required": bool, ...}
        """
        return {}

    @abstractmethod
    async def execute(self, *, ctx: "ActionContext", **kwargs) -> "ActionResult":
        """Execute the skill logic.

        Args:
            ctx: ActionContext with driver, state, etc.
            **kwargs: Parameter values as defined by ``parameters()``.

        Returns:
            ActionResult indicating success or failure.
        """
        ...

    def to_tool_spec(self) -> dict:
        """Convert to a ToolRegistry-compatible spec."""
        return {
            "parameters": self.parameters(),
            "description": self.description,
            "function": self.execute,
        }
