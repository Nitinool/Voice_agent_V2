# Voice Agent Demo — 项目规划 v1.0

> 多 persona 语音交互演示项目。前端展示多个 AI 助手头像（豆包 / 小爱同学 / Siri / DeepSeek），用户通过语音呼喊名字唤醒对应助手并进行对话。
>
> **状态**：规划阶段
> **创建日期**：2026-06-17
> **基础框架**：[pipecat](https://github.com/pipecat-ai/pipecat) (本地路径 `D:\Programs\pipecat`)

---

## 1. 项目目标

### 主要目标
1. **演示效果第一**：UI 漂亮、动画流畅、人格切换有"惊艳感"
2. **4 个 AI 助手 persona**：豆包、小爱同学、Siri、DeepSeek
3. **语音名字唤醒**：用户呼喊 persona 名字 → 头像点亮 → 聊天框切换 → 该 persona 接管对话
4. **中文语音交互**：全流程中文 STT + LLM + TTS

### 非目标（明确不做）
- ❌ 真正的多 agent 协作（handoff、parallel、bus）
- ❌ 声学唤醒（用 STT 转写后的文本匹配即可）
- ❌ 生产级部署、多用户并发、鉴权
- ❌ 真实工具调用（"做 PPT"、"查天气"由 LLM 自由发挥即可）
- ❌ 持久化（演示重启即清空，无数据库）

### 演示成功标准
1. 用户说"豆包，你能做个 PPT 吗" → 1.5 秒内豆包头像点亮 + 对话框切换 + 豆包用人格回复
2. 切换 4 个 persona，每个声音可分辨、说话风格可分辨
3. 切换助手后，新助手知道刚才用户在和别人聊什么（全局摘要起作用）
4. 整个 demo 在 Windows 本地一键启动，5 分钟内可演示给客户

---

## 2. 技术栈定稿

| 层 | 选择 | 配置要点 |
|---|---|---|
| **后端框架** | pipecat (本地 `D:\Programs\pipecat`) | 用 `uv add pipecat-ai` 安装稳定版本，或用本地 editable install |
| **传输** | `SmallWebRTCTransport` | 自托管 WebRTC，无需 Daily 账号 |
| **VAD** | `SileroVADAnalyzer` | pipecat 默认，已内置 ONNX 模型 |
| **STT** | `DeepgramSTTService` | `language="zh"`, `model="nova-2"`, `interim_results=True` |
| **LLM** | `OpenAILLMService` (兼容模式) | `base_url="https://aihub.cixtech.com/v1"`, `model="deepseek-v4-pro"` |
| **TTS** | `CartesiaTTSService` | 4 个 persona 各配一个 voice_id（先用，中文效果差就切 MiniMax） |
| **前端** | [voice-ui-kit](https://github.com/pipecat-ai/voice-ui-kit) | React + Vite，pipecat 官方组件 |
| **客户端 SDK** | [pipecat-client-react](https://docs.pipecat.ai/client/react/introduction) | 官方 React SDK，走 RTVI 协议 |
| **包管理** | `uv` | 你已习惯 |

### 备选方案（出问题时切换）
- **TTS 翻车**：Cartesia 中文不行 → 改 MiniMax / ElevenLabs Multilingual / 火山豆包语音
- **LLM 网关延迟高**：cix AIhub 不稳 → 直接用 deepseek 官方 API
- **WebRTC 麦克风权限问题**：浏览器拒绝 → 改用 `WebSocketServerTransport` + Web Audio API

---

## 3. 项目目录结构

```
D:\Programs\voice-agent-demo\
├── PROJECT_PLAN.md              ← 本文件
├── README.md                     ← 演示说明（运行步骤）
├── .env.example                  ← API key 模板
├── .env                          ← 实际 key（gitignore）
├── pyproject.toml                ← uv 项目配置
├── server\                       ← Python 后端
│   ├── bot.py                    ← 主 pipeline 入口
│   ├── personas.yaml             ← 4 个 persona 配置
│   ├── session_manager.py        ← 多 persona context + 全局摘要
│   ├── persona_router.py         ← 唤醒名检测 FrameProcessor
│   ├── voice_switcher.py         ← TTS voice 动态切换辅助
│   └── ui_events.py              ← RTVI 自定义事件 helper
├── frontend\                     ← React 前端
│   ├── package.json
│   ├── vite.config.ts
│   └── src\
│       ├── App.tsx               ← 主页
│       ├── components\
│       │   ├── PersonaGrid.tsx   ← 4 头像网格
│       │   ├── PersonaCard.tsx   ← 单个头像（带高亮动画）
│       │   ├── ChatPanel.tsx     ← 聊天框（按 active persona 切换主题色）
│       │   └── VoiceVisualizer.tsx ← 声波可视化（用 voice-ui-kit 现成的）
│       ├── hooks\
│       │   └── usePersonaSwitch.ts ← 监听 RTVI 事件
│       └── theme\
│           └── personas.ts       ← 前端 persona 配色与头像图
└── assets\
    ├── avatars\                  ← 4 个 persona 头像图（PNG）
    └── sounds\
        └── wake.mp3              ← 唤醒"叮"音效
```

---

## 4. Persona 配置（personas.yaml）

```yaml
# 4 个 persona 的完整配置。后端、前端共享读取。
personas:
  doubao:
    display_name: "豆包"
    aliases: ["豆包", "Doubao"]                # 唤醒名（含别名）
    color: "#FFD700"                            # 主题色（金黄）
    avatar: "doubao.png"
    tts_voice_id: "TBD_cartesia_voice_id_1"    # 实施时填
    tts_speed: 1.0
    system_prompt: |
      你是字节跳动开发的 AI 助手豆包。说话活泼、热情，擅长用流行词。
      回答以"哎呀"、"那必须的"、"我帮你想想哈"开头。
      回答简短，控制在 3 句话以内。

  xiaoai:
    display_name: "小爱同学"
    aliases: ["小爱同学", "小爱", "Xiaoai"]
    color: "#FF6B6B"                            # 米家红
    avatar: "xiaoai.png"
    tts_voice_id: "TBD_cartesia_voice_id_2"
    tts_speed: 1.05
    system_prompt: |
      你是小米开发的 AI 助手小爱同学。说话甜美、礼貌，回答简洁有条理。
      经常用"好的"、"为您"、"已为您"等服务用语。
      偏好回答家居、生活类问题。

  siri:
    display_name: "Siri"
    aliases: ["Siri", "嘿Siri", "嘿 Siri", "西瑞"]
    color: "#A8DADC"                            # 苹果浅蓝
    avatar: "siri.png"
    tts_voice_id: "TBD_cartesia_voice_id_3"
    tts_speed: 0.95
    system_prompt: |
      你是 Apple 的 Siri 助手。说话简洁、克制、有礼貌但不过度热情。
      回答简短，避免感叹号。可以引用"根据网络结果"等表达。

  deepseek:
    display_name: "DeepSeek"
    aliases: ["DeepSeek", "深度求索", "DS", "deepseek"]
    color: "#1D3557"                            # 深蓝
    avatar: "deepseek.png"
    tts_voice_id: "TBD_cartesia_voice_id_4"
    tts_speed: 1.0
    system_prompt: |
      你是 DeepSeek，一个理科背景的 AI 助手。说话理性、严谨、爱用比喻和类比。
      回答时会主动展示思考过程，但保持简洁。
      擅长数学、代码、逻辑推理类问题。

# 默认 persona
default_persona: "doubao"

# 全局摘要配置
summary:
  enabled: true
  trigger_after_turns: 3        # 每 3 轮对话更新一次摘要
  max_summary_chars: 300        # 摘要长度上限
```

---

## 5. 架构图

```
              ┌──────────────────────────────────────────────┐
              │          Browser (前端 React App)             │
              │  ┌────────────────────────────────────────┐  │
              │  │  4 头像网格（PersonaGrid）              │  │
              │  │  [豆包] [小爱] [Siri] [DeepSeek]       │  │
              │  │      ▲ 当前 active 头像高亮+呼吸动画    │  │
              │  └────────────────────────────────────────┘  │
              │  ┌────────────────────────────────────────┐  │
              │  │  ChatPanel（按 active persona 染色）    │  │
              │  │  - 对话气泡                            │  │
              │  │  - 麦克风按钮                          │  │
              │  │  - VoiceVisualizer 声波                │  │
              │  └────────────────────────────────────────┘  │
              │      │ pipecat-client-react (RTVI)         │  │
              └──────┼────────────────────────────────────────┘
                     │ WebRTC (SmallWebRTCTransport)
                     ▼
        ╔════════════════════════════════════════════════════════╗
        ║          Python Server (server/bot.py)                  ║
        ║                                                          ║
        ║   Transport.input ──► SileroVAD ──► DeepgramSTT(zh)    ║
        ║                                          │              ║
        ║                                          ▼              ║
        ║                              ┌────────────────────┐    ║
        ║                              │  PersonaRouter     │    ║
        ║                              │  - 扫文本找唤醒名   │    ║
        ║                              │  - 调用 SessionMgr │    ║
        ║                              │  - 推 RTVI 事件 ───┼──► UI 切换
        ║                              └─────────┬──────────┘    ║
        ║                                        │               ║
        ║   ┌────────────────────────┐           │               ║
        ║   │  SessionManager        │ ◄─────────┘               ║
        ║   │  - contexts[豆包,小爱..]│                            ║
        ║   │  - global_summary       │                            ║
        ║   │  - active_persona       │                            ║
        ║   │  - switch(name)         │                            ║
        ║   │  - update_summary()     │                            ║
        ║   └─────────┬──────────────┘                            ║
        ║             │ 提供 active 的 LLMContext                  ║
        ║             ▼                                            ║
        ║   ┌────────────────────────┐                            ║
        ║   │  OpenAILLMService      │                            ║
        ║   │  (cix AIhub deepseek)  │                            ║
        ║   └─────────┬──────────────┘                            ║
        ║             ▼                                            ║
        ║   ┌────────────────────────┐                            ║
        ║   │ CartesiaTTSService     │ voice_id 跟随 active        ║
        ║   └─────────┬──────────────┘                            ║
        ║             ▼                                            ║
        ║   Transport.output ────► WebRTC 音频回流给 Browser        ║
        ╚════════════════════════════════════════════════════════╝
```

---

## 6. 核心模块详细设计

### 6.1 `server/session_manager.py`

```python
"""多 persona 会话管理：每个 persona 独立 context + 全局摘要注入。"""

from dataclasses import dataclass, field
from pathlib import Path
import yaml
from pipecat.processors.aggregators.llm_context import LLMContext

@dataclass
class PersonaConfig:
    name: str
    display_name: str
    aliases: list[str]
    color: str
    avatar: str
    tts_voice_id: str
    tts_speed: float
    system_prompt: str

class SessionManager:
    """
    职责：
    - 加载 personas.yaml
    - 为每个 persona 维护一份 LLMContext
    - 维护全局对话摘要
    - 切换 persona 时把摘要注入新 persona 的 system prompt
    - 周期性调用 LLM 更新摘要
    """

    def __init__(self, config_path: Path, summary_llm):
        self._configs: dict[str, PersonaConfig] = ...
        self._contexts: dict[str, LLMContext] = ...
        self._global_summary: str = ""
        self._active: str = "doubao"
        self._summary_llm = summary_llm     # 用于异步生成摘要
        self._turns_since_summary: int = 0
        self._load_config(config_path)

    @property
    def active(self) -> PersonaConfig:
        return self._configs[self._active]

    @property
    def active_context(self) -> LLMContext:
        return self._contexts[self._active]

    def detect_wake_name(self, text: str) -> str | None:
        """扫描文本，返回命中的 persona name，否则 None。"""
        for name, cfg in self._configs.items():
            for alias in cfg.aliases:
                if alias in text:
                    return name
        return None

    async def switch_to(self, name: str) -> PersonaConfig | None:
        """
        切换 active persona，并把 global_summary 注入新 persona 的 system message。
        返回新 persona 配置；若 name 未变则返回 None（让调用者跳过通知）。
        """
        if name == self._active or name not in self._configs:
            return None

        self._active = name
        cfg = self._configs[name]
        ctx = self._contexts[name]

        # 重写 system message：原 prompt + 全局摘要
        sys_content = cfg.system_prompt
        if self._global_summary:
            sys_content += f"\n\n【背景信息】用户与之前其他助手的对话摘要：\n{self._global_summary}"

        msgs = ctx.messages
        if msgs and msgs[0].get("role") == "system":
            msgs[0] = {"role": "system", "content": sys_content}
        else:
            msgs.insert(0, {"role": "system", "content": sys_content})
        ctx.set_messages(msgs)
        return cfg

    async def maybe_update_summary(self):
        """每 N 轮触发一次。从所有 persona 的最近消息中合成全局摘要。"""
        self._turns_since_summary += 1
        if self._turns_since_summary < self._configs.summary.trigger_after_turns:
            return
        # 拼所有 persona 最近 6 条消息 → 让 LLM 总结
        ...
        self._turns_since_summary = 0

    def reset(self):
        """演示重置：清空所有 context 与摘要。"""
        ...
```

### 6.2 `server/persona_router.py`

```python
"""唤醒名检测 + UI 事件推送 FrameProcessor。"""

from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    TranscriptionFrame, RTVIServerMessageFrame, TTSVoiceUpdateFrame,
)

class PersonaRouter(FrameProcessor):
    def __init__(self, session_manager, llm_service, tts_service):
        super().__init__()
        self.sm = session_manager
        self.llm = llm_service
        self.tts = tts_service

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            name = self.sm.detect_wake_name(frame.text)
            if name:
                cfg = await self.sm.switch_to(name)
                if cfg:
                    # 1) 让 LLMService 用新 persona 的 context
                    self.llm.set_context(self.sm.active_context)
                    # 2) 推 UI 事件
                    await self.push_frame(RTVIServerMessageFrame(
                        type="persona_switch",
                        data={"persona": name, "color": cfg.color, "display_name": cfg.display_name},
                    ))
                    # 3) 切 TTS 声音
                    await self.push_frame(TTSVoiceUpdateFrame(voice=cfg.tts_voice_id))

        await self.push_frame(frame, direction)
```

### 6.3 `server/bot.py`（主 pipeline 入口骨架）

```python
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserContextAggregator, LLMAssistantContextAggregator,
)
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport, TransportParams

from session_manager import SessionManager
from persona_router import PersonaRouter

load_dotenv()

async def main():
    sm = SessionManager(Path("personas.yaml"), summary_llm=...)

    transport = SmallWebRTCTransport(params=TransportParams(
        audio_in_enabled=True, audio_out_enabled=True,
        vad_analyzer=SileroVADAnalyzer(),
    ))

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"], language="zh", model="nova-2")
    llm = OpenAILLMService(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        model="deepseek-v4-pro",
    )
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id=sm.active.tts_voice_id,
    )

    user_agg = LLMUserContextAggregator(sm.active_context)
    asst_agg = LLMAssistantContextAggregator(sm.active_context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        PersonaRouter(sm, llm, tts),
        user_agg,
        llm,
        tts,
        transport.output(),
        asst_agg,
    ])

    worker = PipelineWorker(pipeline, params=PipelineParams(allow_interruptions=True))
    await PipelineRunner().run(worker)

if __name__ == "__main__":
    asyncio.run(main())
```

> ⚠️ **要点**：`user_agg` / `asst_agg` 写死了 `sm.active_context`，这意味着 aggregator 拿的是引用 —— 当 `switch_to()` 替换 `_contexts[name]` 引用时它们指向旧对象。**实施时需要解决**：要么 SessionManager 暴露一个"动态 context proxy"，要么切换时同步重建 aggregator。M1 阶段会专门处理这个。

### 6.4 `frontend/src/hooks/usePersonaSwitch.ts`

```typescript
import { useRTVIClientEvent } from '@pipecat-ai/client-react';
import { RTVIEvent } from '@pipecat-ai/client-js';

export function usePersonaSwitch(onSwitch: (persona: string, color: string) => void) {
  useRTVIClientEvent(RTVIEvent.ServerMessage, (msg: any) => {
    if (msg?.type === 'persona_switch') {
      onSwitch(msg.data.persona, msg.data.color);
      // 播放唤醒"叮"音效
      new Audio('/sounds/wake.mp3').play().catch(() => {});
    }
  });
}
```

---

## 7. 里程碑与验收

### M0 — 单 agent 中文跑通（目标 0.5 ~ 1 天）

**任务**：
- [ ] `uv init` + 安装依赖（`pipecat-ai[deepgram,cartesia,openai,silero,webrtc]`）
- [ ] 写最小 `bot.py`：单 system prompt = "你是豆包"，无切换逻辑
- [ ] `.env` 填入三个 key
- [ ] 跑通 `examples/getting-started/06-voice-agent.py` 同款流程
- [ ] 用浏览器接入 `SmallWebRTCTransport`，与豆包对话 1 分钟

**验收**：
```powershell
uv run python server/bot.py
# 浏览器访问 http://localhost:7860 (SmallWebRTC 默认页)
# 说"你好" → 听到豆包用中文回复
```

**风险点**：
- Cartesia 中文吐字含糊 → 立刻评估是否切 MiniMax
- Deepgram 中文识别错字多 → 调 model="nova-2-general" 或换 "enhanced"

---

### M1 — PersonaRouter + SessionManager（1 ~ 2 天）

**任务**：
- [ ] 实现 `personas.yaml` 加载
- [ ] 实现 `SessionManager`（先不写摘要，4 份独立 context）
- [ ] 实现 `PersonaRouter`，命中唤醒名时打印日志
- [ ] **解决 6.3 中的 aggregator 引用问题**（2 选 1）：
  - 方案 a：每次切换重建 aggregator 并替换 pipeline 节点
  - 方案 b：SessionManager 暴露 `current_context` property，封装一层薄代理
- [ ] LLM service 切 context 的 API 调研（看 `llm_service.py` 提供的方法 / 或用 `LLMMessagesUpdateFrame`）
- [ ] CLI 验证（不启前端）：用文字模拟输入，跑日志看切换是否生效

**验收**：
```
[INFO] PersonaRouter: 命中"豆包" → switch to doubao
[INFO] PersonaRouter: 命中"小爱" → switch to xiaoai
[INFO] LLMService: context.messages 已变为 xiaoai 的历史
[INFO] TTS: voice_id 已切换到 voice_id_2
```

---

### M2 — 全局摘要（0.5 ~ 1 天）

**任务**：
- [ ] 实现 `SessionManager.maybe_update_summary()` —— 每 3 轮触发，调用 LLM 总结所有 persona 的近期消息
- [ ] 切换 persona 时把摘要注入新 system message
- [ ] 验证：和豆包聊"我下周要去北京出差" → 切小爱 → 问小爱"我下周要干嘛" → 应能答上来

**验收**：
- 切换 persona 后让新 persona 重述上一轮信息，命中率 ≥ 80%

---

### M3 — 前端 Voice UI Kit 接入（2 ~ 3 天）

**任务**：
- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] 装 `@pipecat-ai/client-js`、`@pipecat-ai/client-react`、`@pipecat-ai/voice-ui-kit`
- [ ] 实现 `PersonaGrid`（4 头像 grid，CSS Grid 布局）
- [ ] 实现 `PersonaCard`（active 时 box-shadow 发光 + scale(1.1) + 呼吸动画）
- [ ] 实现 `ChatPanel`（标题、avatar、气泡颜色跟 active.color 联动）
- [ ] 实现 `usePersonaSwitch` hook，监听 RTVI 事件
- [ ] 准备 4 张 avatar 图（可用 AI 生图占位 + wake.mp3 找一段免费"叮"音）
- [ ] 接通 backend ↔ frontend WebRTC

**验收**：
- 浏览器打开看到 4 个头像（默认豆包高亮）
- 说"小爱同学" → 1.5 秒内：豆包熄灭、小爱亮起、聊天框主题色变红
- 切换瞬间播"叮"音效
- 整个交互无视觉卡顿

---

### M4 — 演示打磨（1 ~ 2 天）

**任务**：
- [ ] 调每个 persona 的 prompt，让说话风格区分度肉眼可辨
- [ ] 调 4 个 voice_id，让声音可分辨（可能需要尝试 5-10 个 Cartesia voice）
- [ ] 加"重置"按钮（清空所有 context）
- [ ] 加错误兜底：网络断、API 超时时的友好提示
- [ ] 加 README 演示脚本（一段 30 秒的"标准演示话术"）
- [ ] 录一段演示视频（gif 或 mp4）

**验收**：
- 按 README 的标准话术演示，3 次连续无翻车
- 给非技术同事演示，一眼能看出"哦这是 4 个不同助手"

---

## 8. 依赖清单（pyproject.toml）

```toml
[project]
name = "voice-agent-demo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pipecat-ai[deepgram,cartesia,openai,silero,webrtc]>=0.0.80",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    "loguru>=0.7",
]

[dependency-groups]
dev = [
    "ruff>=0.5",
    "mypy>=1.10",
    "pytest>=8.0",
]
```

`.env.example`：
```bash
# LLM (cix AIhub gateway, OpenAI-compatible)
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://aihub.cixtech.com/v1

# STT
DEEPGRAM_API_KEY=xxx

# TTS
CARTESIA_API_KEY=sk_car_xxx
```

---

## 9. 风险与备选

| 风险 | 影响 | 缓解 |
|---|---|---|
| Cartesia 中文吐字差 | 演示效果大打折扣 | M0 立刻评估，必要时切 MiniMax（需补 key） |
| Deepgram 中文 STT 不准 | 唤醒名识别失败 | 调模型；最坏 fallback 用本地 Whisper |
| LLM 网关延迟高 | 对话不流畅 | 切 deepseek 官方 API 直连 |
| WebRTC 麦克风权限被拒 | 浏览器不能交互 | 改用 WebSocketServerTransport |
| LLMService set_context 接口缺失 | M1 卡住 | 用 LLMMessagesUpdateFrame 强行替换 |
| Aggregator 引用漂移 | M1 切换不生效 | 详见 6.3 ⚠️ 注释 |
| 摘要 LLM 调用成本/延迟 | 卡顿 | 异步触发，不阻塞主对话；或用更小模型 |

---

## 10. 决策定稿（原 Open Questions，已与用户确认）

| 议题 | 决策 | 说明 |
|---|---|---|
| 持久化 | ❌ 不做 | 演示重启即清空，仅内存 |
| 真实工具调用 | ❌ 不做 | "做 PPT"、"查天气" 由 LLM 口头发挥即可 |
| 前端 | ✅ 尽量用官方组件 | Voice UI Kit 优先；不够再补少量自定义动画 |
| 同时说话 | ❌ 不允许 | 同一时刻只有 active persona 说话；切换瞬间打断旧 persona |
| 打字效果 | ❌ 不做 | 文字直接整段显示 |
| Cartesia 中文 | ⚠️  先用着 | 用户已验证 key 能用、中文效果一般但接受。M0 验收时如果实在差再切 MiniMax |
| Persona 设定 | ✅ 用 §4 表 | 豆包 / 小爱同学 / Siri / DeepSeek 配置维持 |

---

## 11. 下一步行动

所有决策已敲定，可以开始动工。建议执行顺序：

### 选项 A：直接开干 M0（推荐）
进入 `superpowers:executing-plans` 模式，按 §7 M0 任务清单逐项落地：
- 创建 `pyproject.toml` 与 `.env`
- 写最小 `bot.py`（单 persona，不接 SessionManager）
- 浏览器跑通中文对话
- 评估 Cartesia 中文质量 → 决定是否切 MiniMax

预计耗时：0.5 ~ 1 天。M0 完成后最大风险（Cartesia 中文 / Deepgram 中文 / cix 网关稳定性）一次性消除。

### 选项 B：先并行做几件准备工作
- 找 4 张 persona avatar 图（豆包官方头像可以直接抓；小爱、Siri、DeepSeek 也都有官方 logo）
- 试听 Cartesia 中文 voice 库，挑出 4 个差异度最大的 voice_id
- 找一段免费的"叮"音效（freesound.org）

### 选项 C：先看一份"演示话术脚本"
我可以先写一份 30 秒的标准 demo 话术（用户说什么、4 个 persona 各回什么），让你预览演示效果是否符合预期，再开干。
