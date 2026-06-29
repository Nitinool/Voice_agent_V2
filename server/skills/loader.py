"""skills/loader.py — 扫描 skills_data/ 目录，解析 SKILL.md 注册到 registry.

每个 skill 是 skills_data/<name>/SKILL.md，frontmatter 用 YAML 解析（依赖 pyyaml）。
frontmatter 字段：name / description / triggers(列表)。
frontmatter 之后的正文是 body（注入 system prompt）。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from skills.registry import SkillDef, clear_cache, register

# skill 数据目录：server/skills_data/
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills_data"

_cache_loaded = False


def parse_skill_file(path: Path) -> SkillDef | None:
    """解析单个 SKILL.md 文件 → SkillDef. 解析失败返回 None."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"Failed to read skill {path}: {e}")
        return None

    # 拆 frontmatter（--- ... ---）和正文
    if not raw.startswith("---"):
        logger.warning(f"Skill {path} has no frontmatter, skipping")
        return None

    parts = raw.split("---", 2)
    if len(parts) < 3:
        logger.warning(f"Skill {path} malformed frontmatter, skipping")
        return None

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    try:
        fm = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Skill {path} frontmatter YAML parse failed: {e}")
        return None

    name = str(fm.get("name", "")).strip()
    if not name:
        logger.warning(f"Skill {path} has no name in frontmatter, skipping")
        return None

    description = str(fm.get("description", "")).strip()
    triggers = fm.get("triggers", [])
    if not isinstance(triggers, list):
        triggers = [str(triggers)]
    triggers = [str(t).strip() for t in triggers if str(t).strip()]

    return SkillDef(
        name=name,
        description=description,
        body=body,
        triggers=triggers,
        path=path.parent,
    )


def load_skills(force: bool = False) -> None:
    """扫描 skills_data/ 目录，加载所有 SKILL.md 到 registry.

    Args:
        force: True 强制重新扫描（否则只扫一次）.
    """
    global _cache_loaded
    if _cache_loaded and not force:
        return
    clear_cache()

    if not _SKILLS_DIR.is_dir():
        logger.info(f"Skills dir not found: {_SKILLS_DIR}, no skills loaded")
        _cache_loaded = True
        return

    for entry in sorted(_SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.exists():
            continue
        skill = parse_skill_file(skill_file)
        if skill:
            register(skill)
            logger.info(f"Loaded skill '{skill.name}' from {skill_file}")

    _cache_loaded = True
