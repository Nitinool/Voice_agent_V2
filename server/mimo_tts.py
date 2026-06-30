"""MiMo TTS service —— pipecat 自定义 TTS（小米 mimo-v2.5-tts）.

API 形态：
- 走 OpenAI-兼容的 chat completions 端点（不是标准 audio.speech）
- POST https://api.xiaomimimo.com/v1/chat/completions
- messages = [{role:"user", content: 风格指令(可空)}, {role:"assistant", content: 待合成文本}]
- audio = {"format": "pcm16", "voice": "冰糖|茉莉|苏打|白桦|..."}
- stream=True 时 SSE 返回，每 chunk 的 delta.audio.data 是 base64 PCM16
- 输出固定 24kHz / 16-bit / mono / little-endian

设计要点：
- 继承 pipecat TTSService —— sample_rate 不一致由基类自动 resample
- voice 切换走标准 TTSUpdateSettingsFrame.settings={"voice": ...}（PersonaRouter 走的就这条）
- 用 AsyncOpenAI（mimo 文档明示兼容 OpenAI SDK）
- run_tts 是 AsyncGenerator，逐 chunk yield TTSAudioRawFrame，pipecat 自己拼时间戳/打 metric

用法：
    tts = MimoTTSService(
        api_key=os.environ["MIMO_API_KEY"],
        settings=MimoTTSService.Settings(voice="冰糖"),
    )
"""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import NOT_GIVEN, TTSSettings, _NotGiven
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts


# mimo-v2.5-tts 输出固定 24kHz/16bit/mono PCM
MIMO_SAMPLE_RATE = 24000

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "冰糖"

# 中文预置音色（来自官方文档）
VALID_VOICES = {"冰糖", "茉莉", "苏打", "白桦", "mimo_default"}


@dataclass
class MimoTTSSettings(TTSSettings):
    """MiMo TTS 设置.

    style_prompt: 可选的风格指令，写到 messages[0]（user role）。
        例如 "(温柔)用平静的语气" / "(活泼)用热情的语气"。空字符串=不加。
    """

    style_prompt: str | _NotGiven = field(default_factory=lambda: NOT_GIVEN)


class MimoTTSService(TTSService):
    """小米 MiMo-V2.5-TTS（chat completions 形态）.

    输出 24kHz PCM16，pipecat TTSService 基类自动处理重采样到 transport rate。
    """

    Settings = MimoTTSSettings
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        sample_rate: int | None = None,
        settings: Settings | None = None,
        **kwargs,
    ):
        # 1. 默认值
        default_settings = self.Settings(
            model=DEFAULT_MODEL,
            voice=DEFAULT_VOICE,
            language=None,
            style_prompt="",
        )

        # 2. 合并外部传入的 settings delta
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            sample_rate=sample_rate,  # None → 由 transport sample_rate 决定，基类负责 resample
            push_start_frame=True,
            push_stop_frames=True,
            settings=default_settings,
            **kwargs,
        )

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def can_generate_metrics(self) -> bool:
        return True

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """合成文本 → 流式 yield TTSAudioRawFrame."""
        logger.debug(f"{self}: Generating TTS [{text}]")

        voice = self._settings.voice
        if not voice:
            yield ErrorFrame(error="MimoTTS: voice must be set")
            return
        if voice not in VALID_VOICES:
            logger.warning(f"{self}: voice '{voice}' not in known list {VALID_VOICES} — passing through")

        style = self._settings.style_prompt or ""
        # mimo 要求 messages 至少有 user + assistant 两段；style 为空时仍占 user 槽
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": style},
            {"role": "assistant", "content": text},
        ]

        first_chunk = True
        try:
            await self.start_ttfb_metrics()
            stream = await self._client.chat.completions.create(
                model=self._settings.model or DEFAULT_MODEL,
                messages=messages,
                # mimo 私有字段，OpenAI SDK 透传到 body
                extra_body={"audio": {"format": "pcm16", "voice": voice}},
                stream=True,
            )
            await self.start_tts_usage_metrics(text)

            async for chunk in stream:
                # mimo 的 audio 字段是 OpenAI 标准之外的扩展，转 dict 拿最稳
                # （pydantic 可能把它放进 model_extra 或者忽略，统一走 model_dump）
                payload = chunk.model_dump() if hasattr(chunk, "model_dump") else dict(chunk)
                choices = payload.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                audio = delta.get("audio")
                if not audio:
                    continue
                data = audio.get("data") if isinstance(audio, dict) else None
                if not data:
                    continue
                pcm = base64.b64decode(data)
                if not pcm:
                    continue
                if first_chunk:
                    await self.stop_ttfb_metrics()
                    first_chunk = False
                yield TTSAudioRawFrame(
                    audio=pcm,
                    sample_rate=MIMO_SAMPLE_RATE,
                    num_channels=1,
                    context_id=context_id,
                )
        except Exception as e:
            logger.exception(f"{self}: TTS request failed")
            yield ErrorFrame(error=f"MimoTTS error: {e}")
        finally:
            # 兜底：若 0 个有效 chunk（或异常），stop_ttfb_metrics 永不调用，计时器泄漏
            if first_chunk:
                await self.stop_ttfb_metrics()
