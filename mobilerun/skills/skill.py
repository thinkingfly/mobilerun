"""Skill definition and executor.

YAML-defined skills are loaded as ``Skill`` dataclasses and executed
by ``SkillExecutor``, which expands the step sequence into tool calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from jinja2 import Template

from mobilerun.agent.action_result import ActionResult

if TYPE_CHECKING:
    from mobilerun.agent.action_context import ActionContext
    from mobilerun.agent.tool_registry import ToolRegistry

logger = logging.getLogger("mobilerun")


@dataclass
class Skill:
    """A declarative skill defined in YAML."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    # Optional: only run when conditions are met (simple key-value match on shared state)
    conditions: Optional[Dict[str, str]] = None


class SkillExecutor:
    """Executes a Skill by expanding its steps into tool registry calls."""

    def __init__(self, registry: "ToolRegistry"):
        self._registry = registry

    async def execute(
        self,
        skill: Skill,
        params: Dict[str, Any],
        ctx: "ActionContext",
    ) -> ActionResult:
        """Run all steps of a skill in order, rendering Jinja2 templates in args."""
        results = []
        for i, step in enumerate(skill.steps):
            action_name = step.get("action")
            if not action_name:
                logger.warning(f"Skill {skill.name}: step {i} has no 'action', skipping")
                continue

            # Render Jinja2 templates in args
            raw_args = step.get("args", {})
            rendered_args = self._render_args(raw_args, params)

            logger.debug(
                f"Skill {skill.name}: step {i} → {action_name}({rendered_args})"
            )

            result = await self._registry.execute(
                name=action_name,
                args=rendered_args,
                ctx=ctx,
            )

            if not result.success:
                return ActionResult(
                    success=False,
                    summary=f"Skill '{skill.name}' failed at step {i} ({action_name}): {result.summary}",
                )
            results.append(result.summary)

        return ActionResult(
            success=True,
            summary=f"Skill '{skill.name}' completed: {'; '.join(results)}",
        )

    @staticmethod
    def _render_args(
        raw_args: Dict[str, Any], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Render Jinja2 template strings in arg values."""
        rendered = {}
        for key, value in raw_args.items():
            if isinstance(value, str) and "{{" in value:
                tmpl = Template(value)
                rendered[key] = tmpl.render(**params)
            elif isinstance(value, dict):
                rendered[key] = {
                    k: (
                        Template(v).render(**params)
                        if isinstance(v, str) and "{{" in v
                        else v
                    )
                    for k, v in value.items()
                }
            else:
                rendered[key] = value
        return rendered
