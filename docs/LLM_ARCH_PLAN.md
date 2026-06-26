# LLM 架构改造方案（v1 之后）

> 背景：v1（UI 确定版本）的 LLM 层是纯 chat completion + 手搓 persona 切换。
> 本次改造三件事：会话持久化、天气工具、persona 交接。**不走 multi-worker 路线。**

## 为什么不用 multi-worker

pipecat 的 multi-worker（官方明确不叫 agent）是 actor 模型：每个 worker 独立 pipeline + 独立 LLMContext，靠 job RPC 传 **dict** 通信，**不传实时音频帧流**。

语音 bot 的核心是音频帧流实时流淌。把 TTS 拆到 persona worker，音频帧没法通过 job 回到 transport.output()；TTS 集中在 router 则音色统一，persona 失去意义。pipecat 官方文档自己也说："stages within one conversation are Flows territory, not multi-worker"——多 persona 切换是对话内阶段切换，归类到 Flows / tools，不是 multi-worker。

结论：persona 切换保持 in-place（共享一个 LLMContext，换 messages），persona 间交接用 function calling 实现。

---

## #1 会话持久化

**目标**：断开重连/重启 bot 后，每个 persona 的对话历史不丢。

**做法**：`session_manager.py` 加 JSON 文件落盘层。

- 存储：`data/sessions/<persona>.json`（`data/` 已 gitignore）
- 内容：`messages` 列表（内存里的 `list[dict]`，天然 JSON 可序列化）
- 写时机：
  - `switch_to` 切走时存旧 persona
  - `apply_overrides` 改 prompt 时丢弃该 persona 缓存
  - `on_client_disconnected` 时存当前 active
- 读时机：
  - `SessionManager.__init__` 加载 yaml 后，用磁盘历史覆盖 `_saved_messages`
  - `_load_config` 末尾把 default persona 的磁盘历史灌进 context

**边界**：
- 文件不存在/损坏 → 当空历史，不崩
- system_prompt 被 override 改过 → 丢弃旧历史（沿用 `apply_overrides` 现有逻辑）
- 每次新连接是新 bot 进程（smallwebrtc 每连接 spawn 一个），"重连"即"新进程读旧文件"

**改动**：`session_manager.py`（加 `_persist`/`_load`）、`bot.py`（disconnected 触发持久化）。

---

## #2 persona 交接（handoff_to 工具）

**目标**：豆包说"这个问题让 DeepSeek 答"，真切到 DeepSeek 并转交问题。

**做法**：pipecat 原生 function calling，给 LLM 注册 `handoff_to` 工具。

```python
async def handoff_to(params: FunctionCallParams, target: str, question: str):
    """把当前问题转交给另一个助手回答。
    Args:
        target: 目标助手名，可选 doubao/xiaoai/siri/deepseek
        question: 要转交的问题（原样转述用户的问题）
    """
    if target == sm.active_name:
        await params.result_callback({"handed_off": False, "reason": "already active"})
        return
    await router.switch_to(target, triggered_by="handoff")
    sm.context.add_message({"role": "user", "content": question})
    await params.llm.push_frame(LLMRunFrame())
    await params.result_callback({"handed_off": True})
```

工具 schema 由 docstring + 类型签名自动生成，不写 JSON。

**system_prompt 配套**：每个 persona prompt 加"超出擅长领域可调用 handoff_to 转交"。

**待确认（动手第一步查 `FunctionCallResultProperties` 字段）**：工具返回后默认会触发当前 LLM 再生成一句，handoff 场景下当前 persona 不应再说话。需确认能否阻止当前 persona 的工具后回合。

**改动**：`bot.py`（注册工具 + context 带 tools）、`personas.yaml`（prompt 加 handoff 说明）。

---

## #3 天气查询工具

**目标**：用户问"北京天气"，bot 调工具查 weather.com.cn 后自然语言回答。

**做法**：function calling + httpx 请求。

```python
async def get_weather(params: FunctionCallParams, city: str):
    """查询指定城市的实时天气。
    Args:
        city: 城市名，如"北京"、"上海"、"深圳"
    """
    code = CITY_CODE_MAP.get(city)
    if not code:
        await params.result_callback({"error": f"未找到城市 {city}"})
        return
    async with httpx.AsyncClient() as c:
        r = await c.get(f"http://t.weather.itboy.net/api/weather/city/{code}", timeout=5)
    data = r.json()
    today = data["data"]["forecast"][0]
    await params.result_callback({
        "city": data["cityInfo"]["city"],
        "weather": today["type"],
        "temp": f"{today['low']}~{today['high']}",
        "now": data["data"]["wendu"] + "℃",
    })
```

- CITY_CODE_MAP：内置 20 个常用城市 9 位码
- 工具结果回灌 LLM，LLM 自然语言说出
- 加 `httpx` 依赖

**待确认（动手第一步 curl 验证）**：itboy 镜像不稳定，挂了换官方 `http://www.weather.com.cn/data/sk/{code}.html`（GBK 编码 JSON）。

**改动**：`bot.py`（注册工具）、新建 `server/weather_tool.py`（工具 + 城市码表）、`pyproject.toml`（加 httpx）。

---

## 实现顺序

#1 持久化（最独立、风险低）→ #3 天气工具（验证 function calling 跑通）→ #2 handoff（最复杂，依赖前两者）。

## 自审记录

1. handoff 后当前 persona 多说话问题 → 待确认 `FunctionCallResultProperties`
2. handoff_to 的 target 不能是自己 → handler 加 guard ✅
3. 持久化与 handoff 交互 → handoff 的 add_message 在 switch 之后，下次 switch_to 会存 ✅
4. weather 接口可能挂 → 动手先 curl ✅
5. 城市码表 → 内置 20 个够演示 ✅
6. tool_choice → 默认 auto，不用改 ✅
7. 不碰 multi-worker ✅
