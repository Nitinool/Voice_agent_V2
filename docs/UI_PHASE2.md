# UI Phase 3 设计方案

> 上一版（P2.5）落地了 plasma 全屏 + 字幕 + 抽屉 + 控制条。
> 这一版解决「演示信息传达」：状态可见、切换可控、抽屉可用、字幕可读。

---

## 1. 目标

| # | 目标 | 解决的痛点 |
|---|---|---|
| 1 | 可点击切换 persona | 现在只能语音唤醒，演示时不可控 |
| 2 | 状态指示（thinking/listening/connecting/error） | LLM 跑 3-9s 时屏幕静止，观众以为卡了 |
| 3 | 字幕可读性 | 深色字幕叠深色 plasma 会糊 |
| 4 | 抽屉可用性 | 顶部加 agent 头像栏、宽度可调、设置入口 |

---

## 2. 架构决策：前端点击切换 persona

### 链路（已验证）

```
前端点击头像
  → client.sendClientMessage("set_persona", { persona: "xiaoai" })
    → RTVI client-message (type="set_persona")
      → 后端 RTVIProcessor._handle_client_message
        → @rtvi.event_handler("on_client_message")
          → do_switch_persona(target="xiaoai")
            → SessionManager.switch_to
            → AgentStatusManager.mark_active
            → push TTSUpdateSettingsFrame{voice}
            → push RTVIServerMessageFrame{persona_switch}
            → push RTVIServerMessageFrame{agent_status}
```

后端把切换逻辑从 `PersonaRouter._maybe_switch` 抽成独立函数 `do_switch_persona(sm, asm, target) -> cfg | None`，`PersonaRouter` 和新的 `on_client_message` handler 都调用它。**避免重复逻辑**。

### 后端改动文件

| 文件 | 改动 |
|---|---|
| `server/persona_switch.py`（新建） | `do_switch_persona(sm, asm, target)` 公共函数，接收 SessionManager + AgentStatusManager + target name，返回新 PersonaConfig 或 None；内部 push 三个 frame（TTS voice + persona_switch + agent_status）|
| `server/persona_router.py` | `_maybe_switch` 改为调用 `do_switch_persona`，去掉重复的 push 逻辑 |
| `server/bot.py` | 注册 `@rtvi.event_handler("on_client_message")`，type=`set_persona` 时调 `do_switch_persona(target)` |

注意：`do_switch_persona` 要拿到 pipeline 的 push 能力（push_frame）。它需要一个能 push_frame 的载体 —— `PersonaRouter` 本身是 FrameProcessor 能 push。所以 `do_switch_persona` 设计成接收一个"pusher"（FrameProcessor）参数，由 router 传 self，由 bot 的 client-message handler 传... 

**问题**：bot.py 里 `on_client_connected` 用的是 `worker.queue_frames()`，但 `on_client_message` 是 RTVI processor 的事件，handler 里没有直接的 worker/pipeline 引用。

**方案**：`do_switch_persona` 接收 `pusher: FrameProcessor`。在 PersonaRouter 里传 `self`。在 bot 里注册的 client-message handler 需要一个能 push 的 processor —— 可以用一个专门的 `PersonaRouter` 实例（已经在 pipeline 里），handler 调用 `router.handle_client_switch(target)`。让 PersonaRouter 暴露一个 public method `async def switch_to(self, target)`，内部调 `do_switch_persona(self, sm, asm, target)`。bot 的 client-message handler 直接调 `router.switch_to(target)`。

这样 router 既是 pipeline 里的 FrameProcessor（能 push frame），又提供 switch_to 给 client-message handler 调用。干净。

---

## 3. 状态指示器（P3.2）

### 状态来源（全用官方 hook）

| 状态 | 来源 |
|---|---|
| connecting / connected / disconnected / error | `usePipecatConnectionState()` → `state` / `isConnected` / `isConnecting` / `isDisconnected` |
| bot thinking（LLM 在跑） | 监听 `usePipecatEventStream` 的 `botLLMStarted` / `botLLMStopped` 事件 |
| user speaking | 监听 `userStartedSpeaking` / `userStoppedSpeaking` 事件（或 `BotStartedSpeaking`/`BotStoppedSpeaking`） |

### 显示位置

- **thinking**：plasma 中央叠一个 voice-ui-kit `Thinking` 组件（三点呼吸）—— 跟 TranscriptOverlay 同区域，但互斥（thinking 时无字幕，有字幕说明已开始说）
- **connecting**：plasma 中央叠 `SpinLoader` + "连接中..."
- **error**：底部弹 voice-ui-kit `Banner`（variant=warning/error）
- **user speaking**：ControlBar 的 mic 按钮 pulse（CSS 动画），或 transcript overlay 的 local 字幕本身就是反馈

复用组件：`Thinking` / `SpinLoader` / `StripeLoader` / `Banner` 都在 voice-ui-kit。

---

## 4. 字幕可读性（P3.3）

TranscriptOverlay 外层 `.transcript-stage` 加：

```css
.transcript-stage {
  /* 已有居中布局 */
}
.transcript-stage > * {
  background: color-mix(in oklch, var(--color-background) 45%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  padding: 6px 16px;
  border-radius: 10px;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
}
```

半透明背景片 + blur 让字幕在任何 plasma 配色下都清晰。text-shadow 双保险。

---

## 5. 左侧控制面板（P3.4）

常驻左侧（不 hover 触发），用 voice-ui-kit `Panel` 组件：

```
┌─────────────┐
│ STATUS      │  ← PanelHeader
├─────────────┤
│ ● connected │  ← 连接状态 LED
│ 豆包        │  ← 当前 active persona
│ ⏱ 00:45    │  ← 会话时长（可选）
│ 💭 thinking │  ← thinking 时显示
├─────────────┤
│ (可视化?)   │  ← 可选小型 visualizer
└─────────────┘
```

宽度固定 ~200px，`flex-shrink: 0`。plasma 在它后面透出（半透明 + blur）。

复用：`Panel` / `PanelHeader` / `PanelTitle` / `PanelContent` / `LED`（状态灯）/ `SpinLoader`。

---

## 6. 历史抽屉改造（P3.5）

### 6.1 顶部 agent 头像栏

抽屉顶部加一栏，4 个 persona 头像横排（圆形 emoji avatar），**可点击切换**：

```
┌──────────────────────────┐
│  🤗   ❤️   🎙️   🐳   ⚙️  │  ← 头像栏 + 设置齿轮
├──────────────────────────┤
│  (历史消息列表)           │
│  🤗 豆包: 哎呀你好...     │
│        你: 你好           │
└──────────────────────────┘
```

- 当前 active 头像：persona color 描边 + glow
- 点击非 active 头像 → `client.sendClientMessage("set_persona", {persona})`
- 最右齿轮 → DropdownMenu 设置

### 6.2 宽度拖拽

用 voice-ui-kit `ResizablePanelGroup` + `ResizableHandle`：

```tsx
<ResizablePanelGroup direction="horizontal">
  <ResizablePanel defaultSize={20} minSize={15} maxSize={35}>  {/* 控制面板 */}
    <ControlPanel />
  </ResizablePanel>
  <ResizableHandle />
  <ResizablePanel defaultSize={80}>  {/* 主区 */}
    <PlasmaBackground + 主内容 />
  </ResizablePanel>
</ResizablePanelGroup>
```

但历史抽屉是 hover 浮层，不在 ResizablePanelGroup 里。宽度拖拽应用到**控制面板**（左侧常驻），历史抽屉保持 hover 浮层固定 320px。

**修正**：宽度拖拽针对左侧控制面板（常驻），不是历史抽屉。历史抽屉保持 hover。

### 6.3 设置 DropdownMenu

齿轮点击 → DropdownMenu：
- 「Agent 命名」：4 个输入框改 display_name，存 localStorage（`voice-agent-agent-names`）
- 「抽屉自动开关」：toggle，控制历史抽屉是 hover 自动还是常显/常隐

```tsx
<DropdownMenu>
  <DropdownMenuTrigger><SettingsIcon /></DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuLabel>Agent 命名</DropdownMenuLabel>
    {/* 4 个 Input */}
    <DropdownMenuSeparator />
    <DropdownMenuLabel>抽屉</DropdownMenuLabel>
    {/* toggle: 自动开关 */}
  </DropdownMenuContent>
</DropdownMenu>
```

agent 命名改完后，通过 `window.dispatchEvent(new CustomEvent('agent-rename'))` 通知各组件重读 localStorage。

---

## 7. 实现顺序

| Step | 内容 | 风险 |
|---|---|---|
| P3.1 | 后端 set_persona（抽 do_switch_persona + on_client_message handler） | 中，动后端 |
| P3.2 | 状态指示器 | 中，要测各状态时机 |
| P3.3 | 字幕可读性 | 低，纯 CSS |
| P3.4 | 左侧控制面板 | 中，新组件 + 布局调整 |
| P3.5 | 抽屉改造（头像栏 + 设置菜单） | 中高，最复杂 |

P3.1 是前端头像点击的前置（没它点击无效），先做。

---

## 8. 不做

- 真实 avatar 图（emoji 继续占位，P4）
- agent 命名持久化到后端 yaml（只 localStorage）
- 控制面板里的可视化（plasma 已经是主可视化，不需要第二个）
- 会话时长（可选，时间够再加）
