"""skills/registry.py — Skill 注册表框架.

Skill = SKILL.md 文件（frontmatter + markdown 正文），是注入 system prompt 的
"知识包"，告诉 LLM 何时用哪些 tool、怎么用。

设计借鉴 Code_Agent 的 skills/registry.py：
  - SkillDef：name / description / body(markdown 正文) / triggers(触发关键词)
  - 全局缓存：register / get_active_skill_contents
  - loader 扫描 skills_data/ 目录解析 SKILL.md

跟 tool 的区别：tool 是可执行函数（LLM 调用），skill 是知识说明（注入 prompt）。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SkillDef:
    """Skill 定义 — 一个 SKILL.md 文件解析结果.

    Attributes:
        name: 短名称，如 "weather".
        description: 一句话描述.
        body: frontmatter 之后的 markdown 正文（注入 system prompt 的内容）.
        triggers: 触发关键词列表（frontmatter 解析，预留：可用于自动激活）.
        path: SKILL.md 文件路径.
    """

    name: str
    description: str = ""
    body: str = ""
    triggers: list[str] = field(default_factory=list)
    path: Path = field(default_factory=Path)


# ===== 全局缓存 =====

_skills_cache: dict[str, SkillDef] = {}


def register(skill: SkillDef) -> None:
    """注册一个 skill（同名覆盖）."""
    _skills_cache[skill.name] = skill


def get_skill(name: str) -> Optional[SkillDef]:
    """按名查 skill."""
    return _skills_cache.get(name)


def list_skills() -> list[dict]:
    """列出所有 skill 摘要（调试/UI 用）."""
    return [
        {
            "name": s.name,
            "description": s.description,
            "triggers": s.triggers,
        }
        for s in _skills_cache.values()
    ]


def get_active_skill_contents(active: Optional[list[str]] = None) -> str:
    """返回激活 skill 的 body，拼成 markdown，注入 system prompt.

    Args:
        active: 激活的 skill name 列表。None 表示所有已注册 skill 都激活
            （演示场景：让 LLM 看到全部 tool 使用说明）.

    Returns:
        拼接后的 markdown 字符串，前缀说明"以下是可用能力"，每个 skill 用注释标记。
    """
    targets = (
        list(_skills_cache.values())
        if active is None
        else [_skills_cache[n] for n in active if n in _skills_cache]
    )
    if not targets:
        return ""
    parts = ["\n\n## 可用能力（skill 说明）\n以下是你可用的工具能力说明，按需调用对应工具。"]
    for s in targets:
        parts.append(f"\n<!-- SKILL: {s.name} -->\n{s.body}")
    return "\n".join(parts)


def clear_cache() -> None:
    """清空缓存（测试/重载用）."""
    _skills_cache.clear()
