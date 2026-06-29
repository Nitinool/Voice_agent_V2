"""tools — 结构化工具包.

每个 tool 是 builtin/ 下的一个模块，定义 handler + ToolDef 并调用 register()。
bot.py 启动时调 register_all()，所有 tool 自动挂到 LLMContext。
"""
