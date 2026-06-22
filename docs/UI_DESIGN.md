# UI 设计方案 (P2.5：UI 大改 → 演示风)

> 目标：把当前 minimal 骨架（chips + 自写消息流 + 柱状 VoiceVisualizer + ControlBar）
> 升级成"plasma 全屏 + 字幕浮层 + 左侧历史抽屉"的演示场景 UI。
> 几乎所有视觉组件来自 voice-ui-kit 0.11，最小化自写代码。

---

## 1. 设计目标

| # | 目标 | 怎么验证 |
|---|---|---|
| 1 | 大屏（投影/会议室）观众一眼看懂"谁在说话" | active agent → plasma 配色 + 大字幕都在变 |
| 2 | 视觉延续 voice-ui-kit 官方风格 | 90% 组件来自 `@pipecat-ai/voice-ui-kit` |
| 3 | 多 agent 区分鲜明（解决最初的"诡异感"） | persona color 同时驱动 plasma + chip + 字幕边框 |
| 4 | 支持 dark/light 切换 | `ThemeProvider` + `ThemeModeToggle` |
| 5 | 演示焦点不被信息干扰 | 历史消息默认隐藏（左侧抽屉收起） |

---

## 2. 信息架构（z 轴自底向上）

```
┌──────────────────────────────────────────────────────────┐
│ z-0  Plasma 全屏背景（per-persona color1/2/3）            │
│      ↑ 用 ref.updateConfig() 实时切色                     │
│                                                          │
│ z-1  顶部条                                               │
│      左：[≡] 抽屉切换 + AgentStatusBar（缩小、半透明）    │
│      右：ThemeModeToggle                                  │
│                                                          │
│ z-1  左侧抽屉（默认收起，展开 320px）                     │
│      历史消息（保留现有 PersonaConversation）             │
│                                                          │
│ z-2  中央字幕                                             │
│      TranscriptOverlay participant="bot"  （用户说话时    │
│      TranscriptOverlay participant="local" 显示用户字幕） │
│      → 巨字 + 半透明背景片，呼应 plasma demo              │
│                                                          │
│ z-1  底部 ControlBar                                      │
│      UserAudioControl + ConnectButton + TextInput        │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 组件分配（哪些用官方、哪些自写）

| 区域 | 组件 | 来源 | 备注 |
|---|---|---|---|
| 主题系统 | `ThemeProvider` + `ThemeModeToggle` + `useTheme()` | 官方 | dark/light 切换 + localStorage 持久化都自带 |
| 全屏壳 | `FullScreenContainer` | 官方 | 已用 |
| 应用基座 | `PipecatAppBase` (smallwebrtc) | 官方 | 已用，不变 |
| **中央 Plasma** | `Plasma`（底层，可 ref.updateConfig） | `@pipecat-ai/voice-ui-kit/webgl` | **核心**；需要装 three.js |
| 字幕浮层（bot） | `TranscriptOverlay participant="bot"` | 官方 | karaoke 实时滚动 |
| 字幕浮层（user） | `TranscriptOverlay participant="local"` | 官方 | 演示时也显示用户在说什么 |
| 控制条壳 | `ControlBar` + `ControlBarDivider` | 官方 | 已用 |
| 麦克风 | `UserAudioControl` | 官方 | 已用 |
| 连接按钮 | `ConnectButton` | 官方 | 已用 |
| 文本输入 | `TextInput` | 官方 | **新加** —— 演示时偶尔不想说话 |
| Agent chips | `AgentStatusBar`（自写，P2 已做） | 自有 | 缩小、移到左上 + 半透明 |
| 历史消息 | `PersonaConversation`（自写，P1 已做） | 自有 | 移到左侧抽屉，默认收起 |
| Plasma 配色驱动 | `usePersonaPlasma()` hook | **自写新加** | 监听 persona_switch → 更新 plasma config |

---

## 4. per-persona Plasma 配色

`config.ts` 给每个 persona 加一个 `plasmaColors: [c1, c2, c3]` 字段。颜色基调跟 chip 保持一致，三色给 Plasma 做渐变层。

| Persona | chip color (P1 已定) | plasma color1 | plasma color2 | plasma color3 |
|---|---|---|---|---|
| 豆包 | `#FFD700` | `#FFD700` 金 | `#FFA94D` 橙 | `#FF6B35` 红橙 |
| 小爱同学 | `#FF6B6B` | `#FF6B6B` 粉红 | `#FF1744` 玫红 | `#B2387F` 紫 |
| Siri | `#A8DADC` | `#A8DADC` 青 | `#5DADE2` 蓝 | `#2980B9` 深蓝 |
| DeepSeek | `#1D3557` | `#1D3557` 深蓝 | `#3F51B5` 蓝紫 | `#7B1FA2` 紫 |

切换流程：

```
TranscriptionFrame("小爱同学")
  → PersonaRouter._maybe_switch
    → push RTVIServerMessageFrame{type:persona_switch, persona:"xiaoai"}
      → 前端 usePersonaPlasma() 监听
        → plasmaRef.current.updateConfig({color1, color2, color3})
          → Plasma WebGL 平滑过渡到新色（自带 colorCycleSpeed 插值）
```

---

## 5. 主题切换

直接用官方 `ThemeProvider` —— 把它包在 `PipecatAppBase` 外层。

```tsx
<ThemeProvider defaultTheme="dark" storageKey="voice-agent-theme">
  <PipecatAppBase ...>
    {(props) => <AppShell {...props} />}
  </PipecatAppBase>
</ThemeProvider>
```

`ThemeModeToggle` 放右上角。

voice-ui-kit 的官方组件**已经支持** dark/light（`./styles` 全局样式里已经有 CSS variables）。我们自写的 `.agent-chip` / `.messages` / `.msg-bubble` 等也要改成 CSS variables，而不是硬编码 `#1e1e2e` 这种。

具体做法：参考 `@pipecat-ai/voice-ui-kit/styles` 里的 `--background` / `--foreground` / `--card` / `--border` 等变量，把硬编码颜色替换成 `var(--background)` 之类，自动跟主题切。

---

## 6. 实现拆解（按 commit 粒度）

| Step | 改什么 | 风险 |
|---|---|---|
| **6.1** | `pnpm add three` + 验证 `import { Plasma } from "@pipecat-ai/voice-ui-kit/webgl"` 不报错 | 低，纯依赖 |
| **6.2** | `ThemeProvider` 包根 + `ThemeModeToggle` 加到右上 + 自有 CSS 切到 CSS variables | 中，要 audit 现有 CSS |
| **6.3** | 中央加 Plasma 全屏背景 + 写 `usePersonaPlasma` hook | 中，需测 ref 时机和 webgl 性能 |
| **6.4** | 加 `TranscriptOverlay` × 2（bot/local），删 `VoiceVisualizer` | 低 |
| **6.5** | `AgentStatusBar` 缩小 + 移到左上 + 半透明 | 低，纯样式 |
| **6.6** | 左侧抽屉容器 + `PersonaConversation` 装进去（默认收起，按钮展开） | 中，新组件 |
| **6.7** | `ControlBar` 里加 `TextInput` | 低 |
| **6.8** | `personas.yaml` / `config.ts` 加 plasma 三色字段 | 低 |

---

## 7. 不做（明确边界）

- **不**自写 theme 系统：用官方 `ThemeProvider`
- **不**自写 audio visualizer：plasma 自带
- **不**改 active speaker 检测逻辑：仍走 RTVI persona_switch 文本匹配（这是 P3 method A 才换）
- **不**改后端协议（RTVI persona_switch + agent_status 不变）
- **不**做真实 avatar 图（emoji 占位继续，P4 阶段才换）
- **不**做切换时的飞入/缩放动画（plasma 自身的颜色平滑过渡 + chip pulse 已经够明显，再加动画会过度）

---

## 8. 风险/未知

- `Plasma` 在 Windows + Chrome + WebGL 真实跑分如何（CPU/GPU 占用）？P2.5 第一步要量一下，太重就回退到 PlasmaVisualizer（不可配色版）或者 CircularWaveform。
- `TranscriptOverlay` 内部用 `BotOutput` 事件源 —— 需要确认它对 `aggregated_by="sentence"` 的处理（P1 PersonaConversation 是按 sentence 累积的，TranscriptOverlay 可能是 word/token）。
- `useConversation` 的 ProviderContext bug（P1 那次踩到）会不会影响 `TranscriptOverlay`？需要先验证。
- 三色配色给到 Plasma 实际效果（颜色饱和度、对比度）是否好看 —— 可能要现场调。

---

## 9. 顺序

按 6.1 → 6.8 顺序提交，每一步独立可见可回滚。
6.3 完成后就能看到 plasma 全屏 + 配色切换，已经基本是演示形态；6.6 左侧抽屉是锦上添花。
