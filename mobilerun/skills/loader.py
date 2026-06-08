"""Skill loader utility."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from mobilerun.skills.registry import SkillRegistry

logger = logging.getLogger("mobilerun")


def load_skills_from_dirs(skill_dirs: List[str | Path]) -> SkillRegistry:
    """Load all skills from the given directories.

    Args:
        skill_dirs: List of directory paths to scan for skill files.

    Returns:
        SkillRegistry with all loaded skills.
    """
    registry = SkillRegistry()
    for dir_path in skill_dirs:
        path = Path(dir_path).expanduser()
        if path.exists():
            count = registry.load_dir(path)
            if count > 0:
                logger.info(f"Loaded {count} skills from {path}")
        else:
            logger.debug(f"Skill directory not found: {path}")
    return registry
