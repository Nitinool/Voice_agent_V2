"""唤醒名检测 FrameProcessor（in-place 切换）+ 前端主动切换入口.

插在 STT → user_aggregator 之间。
两条切换路径都汇到 `switch_to(target)` method：

  A. 语音唤醒：TranscriptionFrame 命中 persona 别名 → _maybe_switch → switch_to
  B. 前端点击：RTVI client-message type=set_persona → bot.py handler → switch_to

切换做的事（一次性）：
1. SessionManager.switch_to（换 LLMContext.messages）
2. AgentStatusManager.mark_active（更新 4 个 persona 状态）
3. push TTSUpdateSettingsFrame（切 voice）
4. push RTVIServerMessageFrame{persona_switch}（P1：前端 UI 主题）
5. push RTVIServerMessageFrame{agent_status}（P2：前端状态点）
"""

from __future__ import annotations

from loguru import logger

from pipecat.frames.frames import Frame, TranscriptionFrame, TTSUpdateSettingsFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from agent_status import AgentStatusManager
from session_manager import PersonaConfig, SessionManager


class PersonaRouter(FrameProcessor):
    def __init__(
        self,
        session_manager: SessionManager,
        agent_status: AgentStatusManager,
    ):
        super().__init__()
        self._sm = session_manager
        self._as = agent_status

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text:
            await self._maybe_switch(frame.text)

        await self.push_frame(frame, direction)

    async def _maybe_switch(self, text: str) -> None:
        """语音路径：转写命中别名才切。"""
        wake = self._sm.detect_wake_name(text)
        if wake is None:
            return
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
