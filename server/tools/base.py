"""tools/base.py — ToolDef：结构化工具定义，桥接 pipecat FunctionSchema.

借鉴 Code_Agent 的 ToolDef（name/description/parameters/func/read_only），
但 handler 用 pipecat 的 async + FunctionCallParams 范式（调 result_callback
回灌结果，不返回字符串）。

每个 ToolDef 通过 to_function_schema() 转成 pipecat FunctionSchema（带 handler，
LLMContext(tools=[...]) 时自动注册，无需单独 register_function）。
"""

from dataclasses import dataclass, field
from typing import Any

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallHandler


@dataclass
class ToolDef:
    """工具定义 — 注册到 registry 的最小单元.

    Attributes:
        name: 工具名（LLM 调用时用），如 "get_weather".
        description: 自然语言描述（LLM 看的，决定何时调用）.
        properties: JSON Schema 参数定义，如 {"city": {"type":"string","description":...}}.
        required: 必填参数名列表.
        handler: pipecat FunctionCallHandler，async (params, **kwargs) -> None，
            内部调 params.result_callback 回灌结果.
        read_only: 只读工具标记（预留权限检查，目前不影响行为）.
    """

    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
    handler: FunctionCallHandler
    read_only: bool = False

    def to_function_schema(self) -> FunctionSchema:
        """转成 pipecat FunctionSchema（带 handler，自动注册到 LLM service）."""
        return FunctionSchema(
            name=self.name,
            description=self.description,
            properties=self.properties,
            required=self.required,
            handler=self.handler,
        )
