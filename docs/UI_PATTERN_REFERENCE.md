# voice-ui-kit 官方范式抽取（自定义组件参照模板）

> 本文档**固定** voice-ui-kit 的组件结构、props、classNames 插槽、主题、协议用法，
> 作为自定义组件（`PersonaMessage` / `PersonaAvatar` / `AgentStatusDot`）的**实现参照**。
> 自定义时严格照此结构改，不另起炉灶。
>
> 来源：`@pipecat-ai/voice-ui-kit@0.11.0` 类型定义 + GitHub README。
> 官方文档站：https://voiceuikit.pipecat.ai

---

## 1. 安装与引入（官方标准）

```bash
npm i @pipecat-ai/voice-ui-kit @pipecat-ai/client-js @pipecat-ai/client-react
npm i @pipecat-ai/small-webrtc-transport   # 传输层
npm i @fontsource-variable/geist @fontsource-variable/geist-mono  # 可选：官方默认字体
```

```tsx
// 入口
import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import '@pipecat-ai/voice-ui-kit/styles';   // ← 官方主题样式（Tailwind 4 + CSS 变量）
```

---

## 2. 官方组件 / Hook 全清单

### 组合（模板）
| 组件 | 用途 |
|---|---|
| `ConsoleTemplate` | 开箱即用整页（debug 用，**不**支持多 persona） |
| `PipecatAppBase` | 自定义骨架，render-prop 拿 `{client, handleConnect, handleDisconnect, error}` |
| `ThemeProvider` | 主题提供者（必须包在最外层） |
| `FullScreenContainer` | 全屏容器 |

### 音视频 / 控制
`VoiceVisualizer`、`ControlBar`、`ConnectButton`、`UserAudioControl`、`BotAudioControl`、`BotVolumeSlider`、`ErrorCard`、`SpinLoader`、`StripeLoader`、`LoaderSpinner`

### 对话（核心范式来源）
| 组件 | 职责 |
|---|---|
| `ConversationProvider` | 对话上下文提供者 |
| `Conversation` | 对话列表（自动接 client SDK，自动滚动） |
| `ConversationPanel` | 对话面板容器 |
| `MessageContainer` | **单条消息**（avatar+label+content）← 自定义气泡的参照 |
| `MessageRole` | 角色标签（"assistant"/"user"/...） |
| `MessageContent` | 消息文本（karaoke/captions/instant 渲染）← **直接复用** |

### 状态 / 徽标
`ClientStatus`（连接态）、`Badge`（通用徽标）

### Hook（大部分从 `@pipecat-ai/client-react` re-export）
| Hook | 返回 |
|---|---|
| `useConversation` (= `usePipecatConversation`) | `messages: ConversationMessage[]` |
| `useConversationContext` | 对话 store |
| `usePipecatEventStream({maxEvents})` | 事件流（含 ServerMessage） |
| `usePipecatConnectionState` | `{isConnected, transportState}` |
| `usePipecatClient` | PipecatClient 实例 |
| `useBotAudioOutput` | bot 音频状态 |
| `useTheme` | 主题 |

---

## 3. 消息数据模型（**关键：只有 role，没有 persona**）

```ts
// 来自 @pipecat-ai/client-react
interface ConversationMessage {
  role: "user" | "assistant" | "system" | "function_call";
  final?: boolean;
  parts: ConversationMessagePart[];
  // ← 注意：没有 speakerId / personaId / agentId 字段
}
```

**含义**：官方数据模型是"单助手、按 role"。我们要做的"按 persona 区分"必须**前端自行打标**：
监听 persona 切换事件 + 消息到达时间，给每条 assistant 消息附上 `personaId`。

---

## 4. MessageContainer 范式（自定义气泡照抄结构）

### 4.1 Props
```ts
interface MessageContainerProps {
  message: ConversationMessage;
  assistantLabel?: string;      // 默认 "assistant"
  clientLabel?: string;         // 默认 "user"
  systemLabel?: string;         // 默认 "system"
  functionCallLabel?: string;   // 默认 "function call"
  functionCallRenderer?: FunctionCallRenderer;
  classNames?: {
    container?: string;
    messageContent?: string;
    role?: string;        // ← 角色标签的 className 插槽
    thinking?: string;
    time?: string;
  };
  botOutputRenderers?: Record<string, CustomBotOutputRenderer>;
  aggregationMetadata?: Record<string, AggregationMetadata>;
  textRenderMode?: "karaoke" | "captions" | "instant";  // 默认 "karaoke"
}
```

### 4.2 DOM 结构范式（推断）
```
<div className={classNames.container}>           ← MessageContainer 外层
  <MessageRole role={message.role}              ← 角色标签
      assistantLabel={...} ... className={classNames.role} />
  <MessageContent message={message}            ← 文本内容（复用官方）
      classNames={{ messageContent, thinking }}
      textRenderMode={...} />
  {可选 thinking / time}
</div>
```

### 4.3 自定义 PersonaMessage = 把 role-label 换成 persona-label
```
<div className="persona-msg">                  ← 照抄 MessageContainer 外层结构
  <PersonaAvatar personaId={...} />            ← 自定义头像（替 MessageRole）
  <div className="msg-col">
    <span className="msg-name"                 ← 名字（替角色标签文字）
          style={{color: persona.color}}>
      {persona.display_name}
    </span>
    <MessageContent message={message}          ← ★ 官方组件直接复用（karaoke 等白送）
        textRenderMode="karaoke" />
  </div>
</div>
```

**要点**：
- 结构照抄官方（外层 + label 行 + content）
- 名字/配色/头像由 persona 驱动（不是 role）
- **文本渲染 100% 复用官方 `MessageContent`**（不重造 karaoke）

---

## 5. Conversation 范式（列表）

```ts
interface ConversationProps {
  classNames?: { container?; message?; messageContent?; role?; time?; thinking? };
  noAutoscroll?: boolean;      // 默认 false
  reverseOrder?: boolean;      // 默认 false（新消息在底部）
  assistantLabel? / clientLabel? / systemLabel? / functionCallLabel?;
  noTextInput?: boolean;      // 默认 false
  noFunctionCalls?: boolean;
  functionCallRenderer?;
  botOutputRenderers?;
  aggregationMetadata?;
  textRenderMode?: "karaoke" | "captions" | "instant";
}
```
- 自动接 client SDK（内部用 `useConversation`）
- 自定义列表：可用官方 `Conversation` 但传 `classNames` 覆盖；或自己 `useConversation` 拿数据 + map 出 `PersonaMessage`（**推荐后者**，因为要按 persona 上色，官方列表没法注入 persona 信息）

---

## 6. 主题范式（Tailwind 4 + CSS 变量）

- 用 `ThemeProvider` 包裹（必须）
- 颜色全走 CSS 变量：`--background`、`--foreground`、`--primary` …（Tailwind 4 体系）
- **自定义组件必须用这套变量**，不要硬编码颜色（persona 色除外，persona 色是业务配置）
- persona 色用内联 `style={{ color: persona.color, background: persona.color }}`（来自 `personas.yaml`）

---

## 7. 自定义元数据协议范式（RTVI ServerMessage）

persona 切换 / 忙碌状态都走官方 RTVI `ServerMessage`（后端推 `RTVIServerMessageFrame`）：

### 后端（Python）
```python
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

await self.push_frame(RTVIServerMessageFrame(data={
    "type": "persona_switch",         # 已在用
    "persona": "xiaoai", "display_name": "小爱同学", "color": "#FF6B6B",
}))

await self.push_frame(RTVIServerMessageFrame(data={
    "type": "agent_status",           # 新增：忙碌状态
    "persona": "xiaoai", "status": "busy",   # busy | online | idle | error
}))
```

### 前端（监听）
```ts
// 用官方 usePipecatEventStream 或 client.on(RTVIEvent.ServerMessage)
client.on('serverMessage', (data) => {
  if (data.type === 'persona_switch') setPersona(data.persona);
  if (data.type === 'agent_status')   setStatusMap(prev => ({...prev, [data.persona]: data.status}));
});
```

**这是 100% 官方协议用法**（v2 项目已验证 persona_switch 能跑通）。

---

## 8. 客户端连接范式（官方推荐自定义 UI）

```tsx
import {
  ConnectButton, ControlBar, ErrorCard, FullScreenContainer,
  PipecatAppBase, SpinLoader, VoiceVisualizer, UserAudioControl,
  type PipecatBaseChildProps,
} from "@pipecat-ai/voice-ui-kit";

<FullScreenContainer>
  <PipecatAppBase transportType="smallwebrtc" connectParams={{ webrtcUrl: '/api/offer' }}>
    {({ client, handleConnect, handleDisconnect, error }: PipecatBaseChildProps) =>
      error ? <ErrorCard error={error} /> : (
        <>
          <VoiceVisualizer participantType="bot" />
          <ControlBar>
            <UserAudioControl />
            <ConnectButton onConnect={handleConnect} onDisconnect={handleDisconnect} />
          </ControlBar>
          {/* ← 这里插我们的自定义对话区 + 4 头像卡片 */}
        </>
      )
    }
  </PipecatAppBase>
</FullScreenContainer>
```

---

## 9. 自定义组件实现检查清单

实现 `PersonaMessage` / `PersonaAvatar` / `AgentStatusDot` 时逐条对照：

- [ ] 外层 DOM 结构对齐官方 `MessageContainer`（avatar + label 行 + content）
- [ ] 用官方 `classNames` 插槽命名约定（container / messageContent / role / thinking / time）
- [ ] 颜色走 CSS 变量（除 persona 业务色）
- [ ] bot 消息文本**复用官方 `MessageContent`**（不自己渲染文本）
- [ ] 消息数据来自官方 `useConversation`
- [ ] persona/状态来自官方 RTVI `ServerMessage`（不另开通道）
- [ ] 用 `ThemeProvider` 包裹，不自建主题

满足全部 → 自定义部分与官方组件风格一致，不是"另一套 UI"。
