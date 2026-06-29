"""tools/registry.py — 全局工具注册表.

职责：ToolDef 注册、查找、导出所有 schema 给 LLMContext.
设计借鉴 Code_Agent 的 tools/registry.py，但导出 pipecat FunctionSchema 而非 OpenAI dict。

用法：
    from tools.registry import register, ToolDef
    register(ToolDef(name=..., ...))

    # bot.py 启动时：
    from tools.registry import register_all, get_all_schemas
    register_all()
    context = LLMContext(tools=get_all_schemas())
"""

from __future__ import annotations

from pipecat.adapters.schemas.function_schema import FunctionSchema

from tools.base import ToolDef

# ===== 全局注册表 =====

_registry: dict[str, ToolDef] = {}


def register(tool_def: ToolDef) -> None:
    """注册一个工具。同名覆盖（后注册的生效）."""
    _registry[tool_def.name] = tool_def


def get_tool(name: str) -> ToolDef | None:
    """按名查工具."""
    return _registry.get(name)


def get_all_schemas() -> list[FunctionSchema]:
    """返回所有已注册工具的 FunctionSchema，给 LLMContext(tools=...) 用."""
    return [t.to_function_schema() for t in _registry.values()]


def get_all_defs() -> list[ToolDef]:
    """返回所有 ToolDef（调试/权限检查用）."""
    return list(_registry.values())


def clear_registry() -> None:
    """清空注册表（测试用）."""
    _registry.clear()


def register_all() -> None:
    """启动时调用：导入所有 builtin 模块，触发它们的 register().

    每个 builtin 模块在顶层调用 register(ToolDef(...))。这里只需 import 它们
    即可触发注册。新增 tool 时在 builtin/__init__.py 加一行 import。
    """
    # 延迟 import 避免循环依赖
    from tools.builtin import weather  # noqa: F401  (import 触发 register)
