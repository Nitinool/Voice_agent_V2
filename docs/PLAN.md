# 多 Persona 语音 Agent 设计方案 v1

> **目标**：单会话内多个 AI 助手（豆包 / 小爱同学 / Siri / DeepSeek）共存，
> 每个 assistant 输出用**头像 + 配色气泡**区分，带**忙碌状态点**（红/黄/绿）。
>
> **核心原则**：后端用 pipecat **原生多 agent 框架**；前端**尽量用 voice-ui-kit 官方组件**，
> 仅在官方没有的部分（按 persona 区分消息、忙碌点）做**最小自定义**，且自定义部分**严格参考官方范式**（见 [UI_PATTERN_REFERENCE.md](./UI_PATTERN_REFERENCE.md)）。
>
> **创建**：2026-06-18 · **状态**：待评审

---

## 1. 需求清单（用户确认）

| # | 需求 | 满足方式 |
|---|---|---|
| R1 | 用 pipecat **原生多 agent 框架** | 后端改用 `LLMContextWorker` + `activate_worker`（替代手写 SessionManager） |
| R2 | 尽量用 **pipecat 官方 UI 组件** | voice-ui-kit：`PipecatAppBase`、`VoiceVisualizer`、`ControlBar`、`Conversation`/`MessageContent`、`useConversation` |
| R3 | 所有 agent 对话在**同一个会话** | 单 WebRTC 连接、共享一条对话流（不改传输层） |
| R4 | 每个 agent **不同声音** | 每个 `LLMContextWorker` 自带独立 `CartesiaTTSService`（官方推荐做法） |
| R5 | 不同 agent 输出用**头像 / 不同颜色气泡**区分 | **自定义** `PersonaMessage`（参考官方 `MessageContainer` 范式） |
| R6 | 每个 agent 有**头像** | **自定义** `PersonaAvatar`（参考官方组件分层） |
| R7 | **忙碌状态点**：做任务时红/黄，空闲+在线=绿 | **自定义** `AgentStatusDot`，状态走官方 RTVI `ServerMessage` 协议推送 |
| R8 | **不改语音传输层** | 仅后端 pipeline 内部重构，transport 不动 |

---

## 2. 架构决策

### 后端：pipecat 原生多 agent（worker + bus + handoff，method A 路由）

替换当前 M1 的手写 `SessionManager` + `PersonaRouter`：

```
SmallWebRTCTransport（不动）
    │ input
    ▼
DeepgramSTTService（中文，保留）
    │
    ▼
GreeterAgent (LLMContextWorker)
   - 自带 LLM + TTS
   - 注册官方 @tool: transfer_to_agent(name)
    │
    │  用户说"我想找小爱" → LLM 自己判断调用
    │  transfer_to_agent("xiaoai") → activate_worker(...)
    ▼  handoff via bus
┌───────────────┬───────────────┬───────────────┬───────────────┐
│ DoubaoAgent   │ XiaoaiAgent   │ SiriAgent     │ DeepSeekAgent  │
│ (LLMContext   │ (LLMContext   │ (LLMContext   │ (LLMContext    │
│  Worker)      │  Worker)      │  Worker)      │  Worker)       │
│ 自带 LLM+TTS  │ 自带 LLM+TTS  │ 自带 LLM+TTS  │ 自带 LLM+TTS   │
│ (voice=Hua)   │ (voice=Mei)   │ (voice=Lan)   │ (voice=Tao)    │
└───────────────┴───────────────┴───────────────┴───────────────┘
```

每个 agent：
```python
class XiaoaiAgent(LLMContextWorker):
    def __init__(self):
        llm = OpenAILLMService(..., system_instruction="你是小爱同学...")
        tts = CartesiaTTSService(..., voice=MEI_VOICE_ID)
        super().__init__("xiaoai", llm=llm, pipeline=Pipeline([llm, tts]))
```

**路由方式 A（官方范式）：LLM 用 tool 触发 handoff**
```python
class GreeterAgent(LLMContextWorker):
    @tool
    async def transfer_to_agent(self, params, agent_name: str):
        """用户想找其他助手（小爱/Siri/DeepSeek）时调用"""
        await self.activate_worker(agent_name, deactivate_self=True)
```
- 用户说"我想用小爱" → 接待 agent 的 LLM **自己判断**调用 `transfer_to_agent("xiaoai")`
- 每个 agent 也能再 handoff 回去（互转）
- 官方原话："a handoff sounds like a real transfer between distinct speakers"

> **开场白保护**：不用自写 InputGate（非官方）。改用官方 VAD 参数
> （`SileroVADAnalyzer(params=VADParams(confidence=0.8, min_volume=0.8))`），
> 配合官方 turn-taking。如果实测仍被打断，再用官方的 turn 策略调整，不自写帧丢弃。

### 前端：官方组件 + 最小自定义

```
PipecatAppBase (官方) ── 管理连接生命周期、mic、事件流
    │
    ├── VoiceVisualizer (官方) ── 声波可视化
    ├── ControlBar (官方) ── 麦克风/连接按钮
    │
    └── 对话区（自定义渲染层，数据来自官方 useConversation hook）
        │
        ├── PersonaAvatar (自定义, 参考官方 MessageContainer 分层)
        ├── PersonaMessage  (自定义, 包官方 MessageContent 处理文本)
        └── AgentStatusDot  (自定义, 状态来自官方 RTVI ServerMessage)
```

---

## 3. 官方 vs 自定义 分工（关键）

| 层 | 用什么 | 说明 |
|---|---|---|
| 连接/传输 | ✅ 官方 `PipecatAppBase` + `small-webrtc-transport` | 不动 |
| 音频可视化 | ✅ 官方 `VoiceVisualizer` | 不动 |
| 控制条 | ✅ 官方 `ControlBar` + `ConnectButton` | 不动 |
| 对话**数据** | ✅ 官方 `useConversation` hook | 拿 `ConversationMessage[]` |
| 消息**文本渲染** | ✅ 官方 `MessageContent`（karaoke 高亮等）复用 | 不重造轮子 |
| 状态推送协议 | ✅ 官方 RTVI `ServerMessage` | persona/状态都走这个 |
| **persona 头像** | ❌ **自定义** `PersonaAvatar` | 参考官方 MessageContainer 的 avatar 分层 |
| **按 persona 配色气泡 + 名字** | ❌ **自定义** `PersonaMessage` | 参考官方 MessageContainer 结构，把 role-label 换成 persona-label |
| **忙碌状态点** | ❌ **自定义** `AgentStatusDot` | 参考官方 `Badge`/状态组件范式 + RTVI 推送 |
| 顶部 4 头像卡片 + 高亮动画 | ❌ **自定义** | 已有基础，参考官方主题变量 |

**自定义总量**：约 3 个组件 + 1 个状态 store。**全部有官方兄弟组件可照抄结构**（见范式文档）。

---

## 4. 自定义组件规格

### 4.1 `PersonaMessage`（参考官方 `MessageContainer`）
```
PersonaMessage
├── PersonaAvatar (emoji + persona 色背景)
├── <div className="msg-col">
│     ├── <span className="msg-name" style={color}> {persona.display_name} </span>
│     └── <MessageContent message={...} />   ← 官方组件，复用 karaoke 等
│   </div>
```
- props：`message: ConversationMessage`、`personaId: string`
- 每条 bot 消息按"说话时活跃的 persona"配色 + 头像 + 名字
- 用户消息：右对齐、标"你"、不绑 persona（参考官方 clientLabel）

### 4.2 `PersonaAvatar`
- 圆形 / 圆角方，背景=persona 色，内容=emoji（M3 前用 emoji 占位，M3 接真实头像图）
- 参考官方主题变量（`--theme` / CSS 变量）

### 4.3 `AgentStatusDot`
- persona 头像右下角小圆点
- 状态：`online`（绿）、`busy`（黄）、`error`（红）、`idle`（灰）
- 数据来自 RTVI `ServerMessage` `{type:"agent_status", persona, status}`

---

## 5. 忙碌状态的数据流（R7）

```
后端：Agent 开始执行任务（如做 PPT）
  → 推 RTVIServerMessageFrame({type:"agent_status", persona:"xiaoai", status:"busy"})
  → 任务完成 → 推 {status:"online"}

前端：usePipecatEventStream 监听 ServerMessage
  → 维护 statusByPersona: {xiaoai: "busy", doubao: "online", ...}
  → AgentStatusDot 读这个 state 渲染
```

> 注：M1 阶段"任务"可用模拟（发个延时事件）验证 UI；真实异步任务（真的做 PPT）是后续阶段。

---

## 6. 范式参考原则（重点）

**所有自定义组件必须参考 voice-ui-kit 官方实现**，不得凭空发明：
1. **DOM 结构**：照 `MessageContainer` 的分层（avatar / role-label / content / thinking / time）
2. **CSS 插槽**：用官方的 `classNames` 插槽约定（container / messageContent / role / thinking / time）
3. **主题**：用官方 CSS 变量（`--background`、`--foreground` 等 Tailwind 4 + CSS var 体系），不自建色板
4. **文本渲染**：bot 消息内容**直接复用官方 `MessageContent`**（含 karaoke/captions/instant 三模式），不重写
5. **数据**：消息来自官方 `useConversation`，persona/状态来自官方 RTVI `ServerMessage`

详见 **[UI_PATTERN_REFERENCE.md](./UI_PATTERN_REFERENCE.md)**（官方范式抽取）。

---

## 7. 实施阶段

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P1 前端迁官方骨架 + 消息区分** | ① 前端整体迁到 voice-ui-kit：`PipecatAppBase`+`ThemeProvider`+`VoiceVisualizer`+`ControlBar`/`ConnectButton`（官方连接/声波/控制条，避免手写 client-js 的连接坑）② 在官方 `useConversation`+`MessageContent` 之上做最小自定义 `PersonaMessage`（头像+名字+配色气泡，emoji 占位） | UI 基于官方组件；连接稳定无手写报错；同会话内不同 agent 消息用不同头像+配色+名字 |
| **P2 忙碌状态点** | `AgentStatusDot` + RTVI `agent_status` 协议 + 前端 status store | 让小爱"做 PPT"（模拟任务）→ 头像出现黄点 → 完成回绿点 |
| **P3 后端原生多 agent 迁移（method A）** | `LLMContextWorker` 替代手写 SessionManager；`@tool transfer_to_agent` + `activate_worker` 替代 in-place 文本匹配路由 | 每个 agent 独立 worker + 独立 TTS，切换走官方 LLM tool handoff，"听起来像真人换手" |
| **P4 真实头像图 + 切换动效** | 4 头像卡片换真图、切换高亮动画、chime | 切换瞬间视觉冲击力强 |
| **P5 真实异步任务** | sidecar worker 真的执行任务（如真生成 PPT 大纲） | 忙碌态与真实任务进度联动 |

> **建议顺序**：先 P1（解决当前最大痛点"诡异"），再 P2，后端 method A 迁移 P3 后置。
> **关键**：P1 先把前端迁到 voice-ui-kit 官方骨架（解决手写 client-js 的连接/假麦等坑），
> 再在官方 `useConversation`/`MessageContent` 之上做 per-persona 自定义。
> P1 在当前 M1 in-place 后端上即可跑（后端已推 `persona_switch` 事件）。
> method A 的"LLM 自己决定切换"效果要到 P3 才能看到。

---

## 8. 待确认 / 风险

1. **persona 元数据来源**（已定方案）：官方 `ConversationMessage` 没有 persona 字段 →
   前端按"消息到达时活跃的 persona"打标（persona 切换事件 + 消息时间戳对齐）。简单可靠。
2. **method A 路由可靠性**：LLM 自己决定是否调用 `transfer_to_agent`，可能偶发不切/误切。
   演示前需调好 system_instruction + 工具描述，确保"提到其他助手名字"就切。
   若实测不可靠，再退回文本匹配路由（method B，仅路由判定自写，agent/handoff 仍官方）。
3. **busy 状态真实化**：P5 才接真任务，P2 用模拟数据演示 UI。
4. **method A 的"看效果"**：要到 P3（后端迁移）才能看到 LLM-driven handoff。
   P1/P2 只在当前 M1 in-place 后端上验证前端展示效果。

---

## 9. 相关文档
- [UI_PATTERN_REFERENCE.md](./UI_PATTERN_REFERENCE.md) — voice-ui-kit 官方组件范式抽取（自定义组件的参照模板）
- `PROJECT_PLAN.md` — 项目总规划
