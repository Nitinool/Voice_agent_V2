"""天气查询工具 —— function calling 示例.

LLM 注册 get_weather 后，用户问"北京天气怎么样"，LLM 会自动调用本工具，
工具返回结构化数据，LLM 再用自然语言说出来。

数据源：t.weather.itboy.net（社区维护的中国天气网镜像，返回标准 JSON）。
城市用 9 位 citycode（中国天气网编码，如北京 101010100）。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from pipecat.services.llm_service import FunctionCallParams

# 常用城市 9 位 citycode（演示用，覆盖 20 个主要城市）
# 来源：中国天气网城市编码
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

# 接口地址（{code} 替换为 9 位 citycode）
WEATHER_API = "http://t.weather.itboy.net/api/weather/city/{code}"


async def get_weather(params: FunctionCallParams, city: str) -> None:
    """查询指定城市的实时天气情况。

    当用户询问某个城市的天气、温度、是否下雨等问题时调用此工具。

    Args:
        city: 城市中文名，如"北京"、"上海"、"深圳"。必须是常用城市。
    """
    code = CITY_CODE_MAP.get(city)
    if not code:
        # 城市不在码表里 —— 告诉 LLM 支持哪些城市，让它引导用户
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
        await params.result_callback({"error": f"查询{city}天气失败: {data.get('message', '未知错误')}"})
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
