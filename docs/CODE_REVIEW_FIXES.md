# Code Review 修复计划

> 来源：外部 AI review（两轮，2026-06-30）
> 现状：项目 v6（commit 3fd7717），handoff/vision/会话管理/工具框架已跑通
> 原则：不影响现有能跑的功能，分批改，改完测

## 两条最初判断的纠正

### #1 handoff 消息序——不会 400（reviewer 自纠）
- 核对 v1.4 源码：`FunctionCallInProgressFrame` 在 handler 执行前广播，aggregator 已把 `assistant{tool_calls}` + `tool{IN_PROGRESS}` 一起写进 context
- handler 的 `add_message(user)` 追加在末尾，`result_callback` 走 `_update_function_call_result` 原地替换 IN_PROGRESS 占位
- 真实顺序：`assistant(tool_calls) → tool(result) → user([转交自])`，协议合法
- **竞态是真的**：`push_frame(LLMRunFrame())` 在 `result_callback` 前，target 推理时 tool 还是 IN_PROGRESS 占位 → context 留 IN_PROGRESS 幻影。清理项，非炸弹

### #10-https——别改（reviewer 实测）
- `https://t.weather.itboy.net` SSL 握手失败，`http://` 200
- 改 https 会 break weather 工具。**删除不改**

## 第一批：零风险清理（现在改，不影响功能）

### 1.1 第 6 条 — 删 default_persona 重复赋值
- 文件：`server/session_manager.py:140-145`
- 改法：删掉重复的一组
- 风险：零

### 1.2 第 7 条 — _derive_title 复用 GREETING_PROMPTS
- 文件：`server/session_manager.py:431` + `server/bot.py`
- 改法：把 GREETING_PROMPTS 传进 SessionManager 或导出，`_derive_title` 用集合判断
- 风险：零

### 1.3 第 10c 条 — mimo_tts 0 chunk 时 TTFB 计时器泄漏
- 文件：`server/mimo_tts.py:124`
- 改法：finally 兜底调 stop_ttfb_metrics
- 风险：低

### 1.4 第 10b 条 — replay 跳过 [转交自XX] 消息
- 文件：`server/bot.py`（on_client_connected 的 history_replay 逻辑）
- 改法：replay 过滤时跳过 `content.startswith("[转交自")`
- 风险：低

### 1.5 第 5 条 — 删 switchSession 预切换
- 文件：`frontend/src/useSessions.ts`
- 改法：switchSession 直接 reload，不发预切换
- 风险：低

## 第二批：中风险（改完必须测）

### 2.1 第 8 条 — 封装 SessionManager.replay_messages()
- 文件：`server/bot.py` + `server/session_manager.py`
- 改法：bot.py 探 `_sessions` 的逻辑搬进 `SessionManager.replay_messages()`；`__dict__` 换 `dataclasses.asdict`
- 风险：中（动 replay 主路径）
- 测试：历史回放正常 + persona 头像正确

### 2.2 第 3 条 — 唤醒词误触发（方案 A）
- 文件：`server/persona_router.py`
- 问题：interim 转写 + 纯子串匹配 → "我觉得 Siri 不好"中途切走
- 改法（方案 A，保响应性）：
  - 保持 interim 检测
  - 句首判定：`transcript.startswith(alias)` 或别名前是标点/空格
  - debounce：切过一次后 ~2s 内不再切
- 风险：中（行为变化：非句首别名不切）
- 测试：
  - 正常："小爱同学，今天天气"能切
  - 误触发："我觉得小爱不好"不切
  - 双切："豆包和 siri 哪个好"只切一次

### 2.3 第 4 条 — persona 合并错位
- 文件：`server/session_manager.py` `_sync_context_to_session`
- 改法：按 (role, content) 匹配 persona，不按下标。同 role+content 重复时第一个赢
- 风险：中（改 sync 逻辑）
- 测试：handoff 后历史消息 persona 头像/颜色正确

## 第三批：高风险（先验证再改）

### 3.1 第 1 条 — handoff 竞态 + IN_PROGRESS 幻影
- 改法：
  1. 先加临时 debug log，handoff 后 dump context，确认 `tool(IN_PROGRESS)` + `[转交自]` user
  2. 改成 `result_callback(f"[转交自{from_display}] {question}", run_llm=True)`，去掉手动 add_message + LLMRunFrame
  3. switch_to 在 result_callback 之前完成
- 机制已验证：aggregator:1693 `properties.run_llm` 控制是否跑 LLM
- 风险：高（改坏 handoff 直接坏）
- 测试：handoff 后 target 正常开口 + context 无 IN_PROGRESS 幻影

## 暂缓（不轻易动）

### 3.2 第 2 条 — 转交话 voice 靠 prompt 约束
- 现状：关 reasoning 后 prompt 约束够用
- 不改原因：flush TTS 阻塞 function call 可能卡死
- 触发条件：频繁观察到 farewell 走错 voice 再改

## 留尾观察（不动）

- #9 latency_observer._handle_bot_started_speaking 不调 super 是必要的（要发 ExtendedLatencyBreakdown），加注释说明；usage 实测非空
- 架构1 per-connection SessionManager + 磁盘共享，demo 单用户先留
- 架构2 身份提示 + skill 拼 system prompt，留意 context 膨胀

## 执行顺序

1. 第一批（1.1-1.5）：零风险，一次性改
2. 第二批（2.1-2.3）：中风险，逐条改 + 测
3. 第三批（3.1）：高风险，先 debug log 验证再改
4. 暂缓 + 留尾观察
