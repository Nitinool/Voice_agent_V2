# UI Phase 4 设计方案：可折叠左栏 + 真正的右栏居中

> 当前问题：plasma 用 `position: fixed; inset: 0` 全屏覆盖，所以视觉中心在屏幕中央而不是右栏中央，导致"看起来 plasma 跨在两栏之间"。
> 这一版彻底修正：plasma 限制在右栏内，字幕放 plasma 正下方，左栏支持折叠成竖向窄条。

---

## 1. 目标

| # | 目标 | 解决的痛点 |
|---|---|---|
| 1 | 右栏元素真正居中 | 现在 plasma 跨屏，视觉重心偏左 |
| 2 | 字幕在 plasma 下方而不是叠在 plasma 中 | 现在字幕浮层在 plasma 中央，遮挡 plasma 核心动画 |
| 3 | 左栏可折叠成 48px 窄条 | 演示时想最大化 plasma 舞台、不想要历史 |
| 4 | 折叠时头像竖排 + 状态点 + 齿轮仍可用 | 折叠不能丢功能 |

---

## 2. 视觉草图

### 2.1 展开状态（默认 300px）

```
┌──────────────────────────────────────────────────────────┐
│ 🤗 ❤️ 🎙️ 🐳   ●待命   ⚙️ ↤  │                            │
│ ──────────────────────────  │      ╭───────────╮         │
│                              │    ╱   PLASMA    ╲        │
│   🤗 豆包: 哎呀你好呀…       │   │   (右栏内)    │       │
│       你: 你好               │   │              │       │
│   ❤️ 小爱: 您好...            │    ╲            ╱         │
│                              │      ╰───────────╯        │
│                              │                            │
│                              │   "哎呀，你好呀…"        │  ← Plasma 正下方
│                              │                            │
│                              │   🎙 mic · 🔌 · 💬 input  │
└──────────── 300px ───────────┴──────── 主区 ─────────────┘
```

### 2.2 折叠状态（48px 窄条）

```
┌──────────────────────────────────────────────────────────┐
│ ↦  │                                                     │
│────│                ╭─────────────╮                      │
│ 🤗 │              ╱     PLASMA     ╲                    │
│    │             │   (主区更宽)    │                    │
│ ❤️ │              ╲                ╱                    │
│    │                ╰─────────────╯                      │
│ 🎙️ │                                                     │
│    │           "哎呀，你好呀…"                          │
│ 🐳 │                                                     │
│    │           🎙 mic · 🔌 · 💬 input                   │
│ ●  │                                                     │
│ ⚙️ │                                                     │
└48px┴───────────── 主区（更宽）───────────────────────────┘
```

---

## 3. 关键技术决策

### 3.1 Plasma 改成限制在右栏内

**当前**：`.app-plasma { position: fixed; inset: 0; }` → 覆盖整个 viewport，包括 sidebar 下面
**改后**：`.app-plasma { position: absolute; inset: 0; }` 挂在 `.app-main` 里，只填满右栏

**影响**：
- 左栏 sidebar 不再有 plasma 透过来 → sidebar 用纯色背景（var(--color-card)），不需要 backdrop-filter blur
- plasma 中心严格在右栏中心，符合"右栏元素居中"的预期

### 3.2 字幕从"叠在 plasma 中央"改成"plasma 下方"

**当前**：`.transcript-stage { top: 55%; transform: translate(-50%, -50%); }` —— 叠在 plasma 中央
**改后**：

```
.app-stage 内部纵向 flex 居中：
  ┌─────────┐
  │  flex   │  ← spacer top
  ├─────────┤
  │ plasma  │  ← 居中（占据可用空间的大头）
  │ 视觉锚  │
  ├─────────┤
  │ 字幕    │  ← plasma 下方
  ├─────────┤
  │  flex   │  ← spacer bottom（让 plasma+字幕整体居中）
  └─────────┘
```

但 plasma 是全填 absolute 背景，不参与 flex 排版。所以实际做法是：
- plasma 仍 `absolute inset:0` 填满 `.app-main`
- `.transcript-stage` 用 absolute 定位在 `.app-stage` 底部偏上（比如 `bottom: 80px`），不再 transform 居中

这样视觉上字幕"在 plasma 的下半部分"，控制条在最下面。

### 3.3 左栏折叠

**状态**：`collapsed: boolean`（localStorage 持久化）

**折叠按钮**：放 sidebar 顶部右上角，点击切换；同时键盘 `Cmd/Ctrl+B` 切换（可选）

**布局切换**：
- 展开 width=300px：当前的横排 header（avatars + status + settings）+ 历史消息区
- 折叠 width=48px：
  - 顶部展开按钮 ↦
  - 4 个头像**纵排**（每个 28px，gap 8px）
  - 状态点（无文字）
  - 齿轮（DropdownMenu 弹向右）
  - **历史消息区完全隐藏**

**动画**：`transition: width 0.25s ease`，子元素用 CSS 让 max-width=0 + overflow:hidden 平滑收起。

### 3.4 头像横竖切换实现

不用 JS 改结构，纯 CSS：

```css
.history-avatar-bar {
  display: flex;
  /* 默认横排 */
}
.history-sidebar.is-collapsed .history-avatar-bar {
  flex-direction: column;
}
```

但 header 本身（avatars / status / settings 三段）在展开时是 row，折叠时是 column —— 也用 CSS：

```css
.history-header {
  display: flex;
  flex-direction: row;
}
.history-sidebar.is-collapsed .history-header {
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
```

折叠时 `agent-status-inline` 的文字隐藏，只剩圆点：
```css
.history-sidebar.is-collapsed .agent-status-inline-label {
  display: none;
}
```

### 3.5 折叠状态保留功能

| 功能 | 展开 | 折叠 |
|---|---|---|
| 头像点击切 agent | ✅ 横排 | ✅ 竖排 |
| 状态指示 | ✅ 圆点+文字 | ✅ 只圆点（hover tooltip 看文字） |
| 设置 DropdownMenu | ✅ 弹向下/右 | ✅ 弹向右 |
| 历史消息列表 | ✅ | ❌ 隐藏 |
| 折叠按钮 | ↤ | ↦ |

---

## 4. 实现拆解

| Step | 改动 | 风险 |
|---|---|---|
| 4.1 | Plasma 改成 absolute 挂在 `.app-main`，删 fixed | 低 |
| 4.2 | 字幕浮层从 `top:55% translate` 改成 `bottom: 80px`（plasma 下方） | 低 |
| 4.3 | sidebar 加 `collapsed` 状态到 `useSettings`（localStorage 持久化） | 低 |
| 4.4 | sidebar header 加折叠按钮 + 状态切换 CSS | 中 |
| 4.5 | sidebar 折叠 CSS（width、flex-direction、隐藏 messages） | 中 |
| 4.6 | 状态浮层（StatusOverlay）位置同步调整：thinking/connecting 仍放在 plasma 中央偏上 | 低 |

---

## 5. 涉及文件

| 文件 | 改动 |
|---|---|
| `useSettings.ts` | 加 `collapsed: boolean` 字段 + `setCollapsed` setter |
| `HistorySidebar.tsx` | 加折叠按钮 + `cn('is-collapsed', settings.collapsed)`；DropdownMenu 折叠时 align-side 调整 |
| `App.tsx` | 把 `<PlasmaBackground />` 从 PipecatAppBase 外挪到 `<main>` 内 |
| `index.css` | plasma 改 absolute；transcript-stage 改 bottom 锚定；sidebar 折叠样式（width transition、column 布局、隐藏 messages） |
| `icons.tsx` | 加 PanelLeft / PanelLeftClose 折叠图标 |

---

## 6. 不做（明确边界）

- **不**做 sidebar 拖拽改宽度（折叠/展开两个固定档够用）
- **不**做键盘快捷键（除非你想要）
- **不**做折叠状态下 hover 临时展开（行为复杂、易误触）
- **不**改 RTVI 协议、agent 切换逻辑、状态指示器内核

---

## 7. 验证清单

- 折叠/展开按钮可点，状态写入 localStorage 刷新保留
- 折叠时左栏 48px，头像竖排，状态只圆点（tooltip 看文字），齿轮可点弹出菜单
- 展开时恢复原貌
- plasma 严格限制在右栏内，sidebar 是纯色背景
- 字幕在 plasma 视觉下方居中
- 没有滚动条
- thinking/connecting 状态浮层在 plasma 中央偏上，不和字幕打架
