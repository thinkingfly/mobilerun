"""Skill registry — loads and manages skills from YAML and Python files."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import yaml

from mobilerun.skills.python_skill import SkillBase
from mobilerun.skills.skill import Skill

if TYPE_CHECKING:
    from mobilerun.agent.tool_registry import ToolRegistry
    from mobilerun.agent.action_context import ActionContext

logger = logging.getLogger("mobilerun")


class SkillRegistry:
    """Registry for skills defined in YAML or Python files.

    Skills are automatically wrapped as tool registry entries so that
    agents can call them like any other tool.
    """

    def __init__(self) -> None:
        self._yaml_skills: Dict[str, Skill] = {}
        self._python_skills: Dict[str, SkillBase] = {}

    # -- loading -------------------------------------------------------------

    def load_from_yaml(self, path: Path) -> Skill:
        """Load a skill from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        skill = Skill(
            name=data["name"],
            description=data.get("description", f"Skill: {data['name']}"),
            parameters=data.get("parameters", {}),
            steps=data.get("steps", []),
            conditions=data.get("conditions"),
        )
        self._yaml_skills[skill.name] = skill
        logger.debug(f"Loaded YAML skill: {skill.name}")
        return skill

    def load_from_python(self, path: Path) -> SkillBase:
        """Load a skill from a Python file (expects a SkillBase subclass)."""
        spec = importlib.util.spec_from_file_location("skill_module", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load skill module from {path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find the first SkillBase subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, SkillBase)
                and attr is not SkillBase
            ):
                skill_instance = attr()
                self._python_skills[skill_instance.name] = skill_instance
                logger.debug(f"Loaded Python skill: {skill_instance.name}")
                return skill_instance

        raise ValueError(f"No SkillBase subclass found in {path}")

    def load_dir(self, directory: Path) -> int:
        """Load all skills from a directory. Returns count of loaded skills."""
        if not directory.exists():
            return 0

        count = 0
        for path in sorted(directory.iterdir()):
            if path.suffix in (".yaml", ".yml"):
                try:
                    self.load_from_yaml(path)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load skill from {path}: {e}")
            elif path.suffix == ".py" and not path.name.startswith("_"):
                try:
                    self.load_from_python(path)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to load skill from {path}: {e}")
        return count

    def register(
        self, skill: Skill | SkillBase, registry: "ToolRegistry"
    ) -> None:
        """Register a skill as a tool in the given ToolRegistry."""
        if isinstance(skill, Skill):
            self._register_yaml_skill(skill, registry)
        elif isinstance(skill, SkillBase):
            self._register_python_skill(skill, registry)

    def register_all(self, registry: "ToolRegistry") -> None:
        """Register all loaded skills into a ToolRegistry."""
        from mobilerun.skills.skill import SkillExecutor

        executor = SkillExecutor(registry)

        for name, skill in self._yaml_skills.items():
            skill_instance = skill  # keep reference

            async def yaml_wrapper(
                *, _skill=skill_instance, _executor=executor, ctx: "ActionContext", **kwargs
            ):
                return await _executor.execute(_skill, kwargs, ctx)

            yaml_wrapper.__doc__ = skill.description
            registry.register(
                name=f"skill_{name}",
                fn=yaml_wrapper,
                params=skill.parameters,
                description=skill.description,
            )

        for name, skill in self._python_skills.items():
            registry.register(
                name=f"skill_{name}",
                fn=skill.execute,
                params=skill.parameters(),
                description=skill.description,
            )

    @staticmethod
    def _register_yaml_skill(skill: Skill, registry: "ToolRegistry") -> None:
        """Legacy per-skill registration (kept for backward compat)."""
        from mobilerun.skills.skill import SkillExecutor

        executor = SkillExecutor(registry)

        async def wrapper(*, _skill=skill, _executor=executor, ctx: "ActionContext", **kwargs):
            return await _executor.execute(_skill, kwargs, ctx)

        registry.register(
            name=f"skill_{skill.name}",
            fn=wrapper,
            params=skill.parameters,
            description=skill.description,
        )

    @staticmethod
    def _register_python_skill(skill: SkillBase, registry: "ToolRegistry") -> None:
        registry.register(
            name=f"skill_{skill.name}",
            fn=skill.execute,
            params=skill.parameters(),
            description=skill.description,
        )

    # -- query ---------------------------------------------------------------

    def get_skill(self, name: str) -> Skill | SkillBase | None:
        """Get a skill by name."""
        return self._yaml_skills.get(name) or self._python_skills.get(name)

    def list_skills(self) -> list[dict]:
        """List all registered skills with name, type, and description."""
        result = []
        for name, skill in self._yaml_skills.items():
            result.append({
                "name": name,
                "type": "yaml",
                "description": skill.description,
                "parameters": skill.parameters,
                "steps": len(skill.steps),
            })
        for name, skill in self._python_skills.items():
            result.append({
                "name": name,
                "type": "python",
                "description": skill.description,
                "parameters": skill.parameters(),
            })
        return result
