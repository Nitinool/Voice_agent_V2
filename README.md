# Voice Agent Demo

多 persona 语音对话演示，基于 [pipecat](https://github.com/pipecat-ai/pipecat) + React + voice-ui-kit。

四个 persona 共享一条 WebRTC 连接和一条 pipeline：用户说出唤醒名（"豆包"、"小爱同学"、"Siri"、"DeepSeek"）或点击侧边栏头像，就能切换 system prompt + TTS 音色，每个 persona 各自维护一份对话历史，互不串台。

## 功能一览

- **4 persona 语音切换** — 说出名字或点头像即切，每个 persona 独立对话历史，共享同一条 pipeline
- **Plasma WebGL 可视化** — 跟随 persona 配色 + 当前会话阶段（idle / listening / thinking / speaking）变化
- **Karaoke 字幕** — 跟随音频播放节奏，spoken 字段黑色 / unspoken 灰色，bot 说完 1s 后渐隐
- **左侧 sidebar** — 顶部头像栏 + 当前状态指示 + 每个 persona 独立消息历史，可折叠
- **Settings 抽屉** — Agents tab 改 display_name / system_prompt / TTS voice；Provider tab 只读展示 LLM / TTS / STT 元信息（无 API key）
- **文本输入** — 不方便说话时直接打字发送

## 技术栈

| 层 | 选型 |
|---|---|
| LLM | OpenAI-compatible 接口（默认走 cix AIhub 网关的 deepseek-v4-pro，可换其他兼容 API） |
| STT | Deepgram nova-3，zh-CN |
| TTS | [MiMo v2.5](https://github.com/XiaomiMiMo/MiMo-Audio)（小米 mimo-v2.5-tts），4 个中文预置音色：冰糖 / 茉莉 / 苏打 / 白桦 |
| 后端 | Python 3.11 + pipecat 1.4 + FastAPI（pipecat runner 内置）+ SmallWebRTC transport |
| 前端 | React 18 + TypeScript + Vite + [@pipecat-ai/voice-ui-kit](https://www.npmjs.com/package/@pipecat-ai/voice-ui-kit) + Three.js（Plasma 着色器） |

## 启动

需要两个终端：一个跑后端，一个跑前端。

### 后端

```powershell
cd D:\Programs\voice-agent-demo

# 1. 装依赖（uv 会自动建 .venv）
uv sync

# 2. 配置 .env（参考 .env.example）
#    需要：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / DEEPGRAM_API_KEY / MIMO_API_KEY

# 3. 启动 bot（WebRTC 模式，监听 :7860）
#    Windows 必须设 UTF-8 否则 pipecat 启动横幅里的 emoji 会让 Python 崩
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
uv run python server\bot.py -t webrtc
```

### 前端

```powershell
cd D:\Programs\voice-agent-demo\frontend

# 1. 装依赖（推荐 pnpm，也支持 npm）
pnpm install

# 2. 启动 dev server（默认 :5173，已配 /api/offer 代理到 :7860）
pnpm dev
```

浏览器访问 [http://localhost:5173](http://localhost:5173)，授权麦克风后即可对话。

## 使用

- **切 persona**：说"小爱同学"、"Siri"、"DeepSeek"、"豆包" 任意别名 → 自动切换；或点击左侧头像栏
- **看对话历史**：左侧 sidebar 显示当前 persona 的消息记录，会自动滚动到最新
- **改设置**：右上角齿轮图标 → 抽屉打开后可改 display_name / system_prompt / 音色，点 Apply 才下发
- **断线重连**：先点 Disconnect，再点 Connect — Connect 会触发整页刷新（参见下方"已知限制"）

## 项目结构

```
voice-agent-demo/
├── server/
│   ├── bot.py              # 主入口：pipeline 装配 + RTVI 路由（set_persona / get_config / update_config）
│   ├── persona_router.py   # STT 文本中检测唤醒名 → 切 persona
│   ├── session_manager.py  # 每 persona 独立历史 + override 合并
│   ├── agent_status.py     # 4 persona 在线/idle 状态，推 RTVIServerMessage 给前端
│   ├── mimo_tts.py         # 自实现的 MimoTTSService（继承 TTSService）
│   └── personas.yaml       # 4 persona 配置（display_name / aliases / 音色 / prompt）
├── frontend/src/
│   ├── App.tsx             # 顶层布局：sidebar + 主区（plasma + 字幕 + 控制条）
│   ├── HistorySidebar.tsx  # 左侧 sidebar：头像栏 + 状态 + 历史 + 设置入口
│   ├── SettingsDrawer.tsx  # 右侧滑出抽屉，两 tab：Agents / Provider
│   ├── StatusOverlay.tsx   # 中央状态浮层：Connecting / Listening / Thinking / Speaking
│   ├── PersonaKaraokeOverlay.tsx  # plasma 下方 karaoke 字幕
│   ├── PersonaConversation.tsx    # 当前 persona 的消息列表（带颜色+头像）
│   ├── usePersonaPlasma.ts       # plasma 配色跟随 persona
│   ├── usePersonaPlasmaState.ts  # plasma 动画跟随会话阶段
│   ├── useAgentState.ts          # 从 RTVI 事件流推断 phase
│   ├── useServerConfig.ts        # 通过 RTVI client-request 拉/推 settings
│   └── useSettings.ts            # 前端 localStorage 持久化（agent rename / sidebar collapsed 等）
└── docs/                  # 各阶段方案文档
```

## 实时看日志

```powershell
cd D:\Programs\voice-agent-demo
Get-Content logs\bot.log -Wait -Tail 50
```

`logs/bot.log` 是 UTF-8、按 10MB 滚动；VS Code 也能直接打开自动刷新。

## 已知限制

- **Disconnect 后重连必须刷新页面**：pipecat 1.4 的 small-webrtc-transport 底层的 DailyMediaManager 在 `leave()` 后无法复用 Daily call 对象，`startCamera()` 不再 resolve。前端做了取巧：Connect 按钮的 onClick 改成 `window.location.reload()`，让一切重新挂载。等 SDK 修复后可以撤掉这一层
- **Windows 启动必须设 UTF-8 环境变量**：`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，否则 loguru 输出含 emoji 的启动横幅时会因 GBK 编码崩溃
- **Settings 修改实时但需切换才生效**：override 写入 `SessionManager._configs[pid]` 是即时的，但 prompt / 音色要下次切到该 persona 时才会推送给 LLM / TTS

## 常见问题

**问：浏览器报麦克风权限错？**
答：Windows 上确认 Chrome 已授权当前页麦克风。`localhost` 默认会被当作 secure context，不需要 https。

**问：bot 启动后前端连不上 / 一直 Connecting？**
答：检查 `frontend/vite.config.ts` 的代理配置是否把 `/api/offer` 指向 `http://localhost:7860`。Vite 默认 5173 + bot 默认 7860 是约定。

**问：LLM 报 401 / unauthorized？**
答：`.env` 里 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 都要对齐你用的 OpenAI-compatible 服务。

**问：MiMo TTS 报 voice not supported？**
答：`tts_voice_id` 必须是 `冰糖 / 茉莉 / 苏打 / 白桦` 其中之一（小米 mimo v2.5 当前的中文预置音色）。
