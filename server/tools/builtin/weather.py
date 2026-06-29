"""tools/builtin/weather.py — 天气查询工具（迁移自 weather_tool.py）.

结构化版本：用 ToolDef 显式定义 JSON Schema + async handler，
注册到 tools.registry。pipecat 的 FunctionSchema 自动注册到 LLM service。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from pipecat.services.llm_service import FunctionCallParams

from tools.base import ToolDef
from tools.registry import register

# 常用城市 9 位 citycode（中国天气网编码）
CITY_CODE_MAP: dict[str, str] = {
    "北京": "101010100",
    "上海": "101020100",
    "深圳": "101280601",
    "广州": "101280101",
    "杭州": "101210101",
    "南京": "101190101",
    "成都": "101270101",
    "重庆": "101040100",
    "武汉": "101200101",
    "西安": "101110101",
    "天津": "101030100",
    "苏州": "101190401",
    "长沙": "101250101",
    "郑州": "101180101",
    "青岛": "101120201",
    "厦门": "101230201",
    "大连": "101130201",
    "昆明": "101290101",
    "哈尔滨": "101050101",
    "济南": "101120101",
}

WEATHER_API = "http://t.weather.itboy.net/api/weather/city/{code}"


async def _get_weather(params: FunctionCallParams) -> None:
    """查询指定城市的实时天气情况.

    当用户询问某个城市的天气、温度、是否下雨等问题时调用此工具。
    支持多城市对比：用户问"北京和上海哪个凉快"时，分别调用本工具查每个城市。
    """
    # FunctionSchema handler 只收 params，参数从 params.arguments 取
    # （pipecat 调 FunctionCallHandler 时只传 params，不像 direct function 拆关键字参数）
    city = params.arguments.get("city", "")
    if not city:
        await params.result_callback({"error": "缺少城市参数 city"})
        return
    code = CITY_CODE_MAP.get(city)
    if not code:
        supported = "、".join(CITY_CODE_MAP.keys())
        await params.result_callback(
            {"error": f"暂不支持查询「{city}」的天气", "supported_cities": supported}
        )
        return

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(WEATHER_API.format(code=code))
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"get_weather 请求失败 city={city}: {e}")
        await params.result_callback({"error": f"查询{city}天气失败，请稍后再试"})
        return

    if data.get("status") != 200:
        await params.result_callback(
            {"error": f"查询{city}天气失败: {data.get('message', '未知错误')}"}
        )
        return

    city_info = data.get("cityInfo", {})
    weather_data = data.get("data", {})
    forecast = weather_data.get("forecast", [])
    today = forecast[0] if forecast else {}

    await params.result_callback(
        {
            "city": city_info.get("city", city),
            "current_temp": weather_data.get("wendu", "未知") + "℃",
            "humidity": weather_data.get("shidu", "未知"),
            "air_quality": weather_data.get("quality", "未知"),
            "today_weather": today.get("type", "未知"),
            "today_temp_range": f"{today.get('low', '?')}~{today.get('high', '?')}",
            "cold_advice": weather_data.get("ganmao", ""),
        }
    )


# 模块导入时自动注册到全局 registry
register(ToolDef(
    name="get_weather",
    description=(
        "查询指定城市的实时天气情况。当用户询问某个城市的天气、温度、是否下雨等"
        "问题时调用此工具。支持多城市对比：用户问『北京和上海哪个凉快』时，"
        "分别调用本工具查每个城市，再自己对比。"
    ),
    properties={
        "city": {
            "type": "string",
            "description": "城市中文名，如『北京』、『上海』、『深圳』。必须是常用城市。",
        },
    },
    required=["city"],
    handler=_get_weather,
    read_only=True,
))
