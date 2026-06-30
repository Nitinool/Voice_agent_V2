"""唤醒名检测 FrameProcessor（in-place 切换）+ 前端主动切换入口.

插在 STT → user_aggregator 之间。
两条切换路径都汇到 `switch_to(target)` method：

  A. 语音唤醒：TranscriptionFrame 命中 persona 别名 → _maybe_switch → switch_to
  B. 前端点击：RTVI client-message type=set_persona → bot.py handler → switch_to

唤醒匹配（方案 A，保响应性避免误触发）：
  - 句首判定：别名在句首或前面是标点/空格（独立称呼），见 session_manager.detect_wake_name
  - debounce：切过一次后 2s 内不再切，避免一句话多次命中（"豆包和 siri 哪个好"双切）

vision 注入在 bot.py 用 user_aggregator 的 on_user_turn_started 事件实现
（VAD 在 aggregator 内部，本 processor 在它上游收不到 UserStartedSpeakingFrame）。
"""

from __future__ import annotations

import time

from loguru import logger

from pipecat.frames.frames import Frame, TranscriptionFrame, TTSUpdateSettingsFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from agent_status import AgentStatusManager
from session_manager import PersonaConfig, SessionManager

# 唤醒切换 debounce 窗口：切过一次后 2s 内不再切，避免一句话多次命中
_WAKE_DEBOUNCE_SECS = 2.0


class PersonaRouter(FrameProcessor):
    def __init__(
        self,
        session_manager: SessionManager,
        agent_status: AgentStatusManager,
    ):
        super().__init__()
        self._sm = session_manager
        self._as = agent_status
        # debounce：上次切换的时间戳
        self._last_switch_ts: float = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text:
            await self._maybe_switch(frame.text)

        await self.push_frame(frame, direction)

    async def _maybe_switch(self, text: str) -> None:
        """语音路径：转写命中别名（句首判定）才切，且 2s debounce."""
        now = time.monotonic()
        if now - self._last_switch_ts < _WAKE_DEBOUNCE_SECS:
            return  # debounce 窗口内，跳过
        wake = self._sm.detect_wake_name(text)
        if wake is None:
            return
        self._last_switch_ts = now
        await self.switch_to(wake, triggered_by=f"voice '{text}'")

    async def switch_to(
        self, target: str, triggered_by: str = "manual"
    ) -> PersonaConfig | None:
        """切到指定 persona。target 无效或已是当前 active 返回 None。

        语音路径和前端点击路径共用此方法，保证切换行为一致。
        """
        cfg = self._sm.switch_to(target)
        if cfg is None:
            return None
        logger.info(
            f"PersonaRouter: switched to {cfg.display_name} (by {triggered_by})"
        )

        # 1) 更新 agent 状态
        self._as.mark_active(cfg.name)

        # 2) 切 TTS voice
        await self.push_frame(TTSUpdateSettingsFrame(settings={"voice": cfg.tts_voice_id}))

        # 3) 通知前端切 UI 主题（P1 协议）
        await self.push_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "persona_switch",
                    "persona": cfg.name,
                    "display_name": cfg.display_name,
                    "color": cfg.color,
                    "avatar": cfg.avatar,
                }
            )
        )

        # 4) 推全量 agent 状态（P2 协议）
        await self.push_frame(RTVIServerMessageFrame(data=self._as.snapshot()))

        return cfg
