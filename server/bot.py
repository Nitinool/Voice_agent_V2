"""voice-agent-demo M1 — in-place 多 persona 切换（单连接）.

工作模式：
- 一条 WebRTC 连接，一个 bot 进程，一条 pipeline
- 用户说"小爱同学" → STT 转写 → PersonaRouter 命中 → SessionManager 把 LLMContext
  的 messages 换成小爱的历史 → 推 TTSUpdateSettingsFrame 切 voice → 推 RTVI 通知前端
- 每个 persona 独立对话历史（互不串台），共享一个 LLMContext 对象（只换 messages）
- TTS 用 MiMo TTS（小米 mimo-v2.5-tts），4 个中文预置音色对应 4 个 persona

启动：
    uv run python server\\bot.py -t webrtc
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from agent_status import AgentStatusManager
from mimo_tts import MimoTTSService
from persona_router import PersonaRouter
from session_manager import SessionManager

load_dotenv(override=True)

# ============================================================================
# 日志：pipecat.runner.run.main() 内部 logger.remove()，文件 sink 在 bot() 入口加
# ============================================================================
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_FILE_SINK_ADDED = False
_PERSONAS_YAML = Path(__file__).resolve().parent / "personas.yaml"


def _ensure_file_log_sink() -> None:
    global _FILE_SINK_ADDED
    if _FILE_SINK_ADDED:
        return
    logger.add(
        _LOG_DIR / "bot.log",
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
        level="DEBUG",
    )
    _FILE_SINK_ADDED = True


# 开场提示词（user role —— deepseek-v4-pro 推理模型无 user 消息时 completion=0）
GREETING_PROMPTS: dict[str, str] = {
    "initial": "你好，请用一句简短的话向我打招呼并介绍你自己。",
    "welcome_back": (
        "我刚从别的助手那边切换回来找你。请用一句话简短欢迎我回来，"
        "如果你还记得我们刚才聊的内容，可以顺带提一句。"
    ),
    "none": "",
}


def _collect_provider_metadata() -> dict:
    """收集当前后端使用的 LLM / TTS / STT 元信息，供前端 Settings 面板只读展示.

    所有字段均不含 api_key（出于安全考虑），仅 url / model / language 这类
    标识信息. 前端 Settings → Provider 标签页消费这份数据.
    """
    from mimo_tts import DEFAULT_BASE_URL as MIMO_DEFAULT_BASE, MIMO_SAMPLE_RATE

    return {
        "llm": {
            "provider": "OpenAI-compatible",
            "model": os.environ.get("LLM_MODEL", ""),
            "base_url": os.environ.get("LLM_BASE_URL", ""),
        },
        "tts": {
            "provider": "MiMo v2.5",
            "base_url": os.environ.get("MIMO_BASE_URL", MIMO_DEFAULT_BASE),
            "sample_rate": MIMO_SAMPLE_RATE,
        },
        "stt": {
            "provider": "Deepgram",
            "model": "nova-3",
            "language": "zh-CN",
        },
    }


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    # SessionManager（先建空 context，让它填 default persona 的 system prompt）
    context = LLMContext()
    sm = SessionManager(_PERSONAS_YAML, context)
    # P2: agent 状态管理器，初始时 default persona = online，其余 = idle
    asm = AgentStatusManager(
        agent_names=list(sm.all_names()),
        active_name=sm.active_name,
    )
    logger.info(f"Starting M1 in-place bot, default persona = {sm.active.display_name}")

    # STT
    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(
            model="nova-3",
            language=Language.ZH_CN,
            interim_results=True,
        ),
    )

    # TTS（MiMo，初始 voice = default persona 的中文音色名）
    tts = MimoTTSService(
        api_key=os.environ["MIMO_API_KEY"],
        settings=MimoTTSService.Settings(voice=sm.active.tts_voice_id),
    )

    # LLM（不设 system_instruction，prompt 由 messages 第一项承载，避免重复警告）
    llm = OpenAILLMService(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        settings=OpenAILLMService.Settings(model=os.environ["LLM_MODEL"]),
    )

    # Aggregators（VAD 调严防误打断 —— 替代之前的 InputGate）
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.8,
                    min_volume=0.8,
                    start_secs=0.2,
                    stop_secs=0.2,
                )
            )
        ),
    )

    router = PersonaRouter(sm, asm)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            router,            # 唤醒名检测 + 切 persona
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected, greeting from {sm.active.display_name}")
        # P2: 先推一次 agent 状态全量快照，让前端拿到初始状态
        await worker.queue_frames(
            [RTVIServerMessageFrame(data=asm.snapshot())]
        )
        context.add_message(
            {"role": "user", "content": GREETING_PROMPTS["initial"]}
        )
        await worker.queue_frames([LLMRunFrame()])

    # P3.1 / P6: 前端 client message 路由
    # set_persona      → 切 persona（已有）
    # get_config       → 返回 personas_default + personas_current + provider 元信息
    # update_config    → 把前端 diff 合并进内存 override（下次切到该 persona 时生效）
    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        msg_type = getattr(message, "type", None)
        msg_data = message.data or {}

        if msg_type == "set_persona":
            target = msg_data.get("persona")
            if not target:
                return
            logger.info(f"Received set_persona client message: {target}")
            await router.switch_to(target, triggered_by="frontend click")
            return

        if msg_type == "get_config":
            payload = {
                "personas_default": {k: v.__dict__ for k, v in sm.defaults().items()},
                "personas_current": {k: v.__dict__ for k, v in sm.current().items()},
                "active_persona": sm.active_name,
                "default_persona": sm._default,
                "provider": _collect_provider_metadata(),
            }
            await rtvi.send_server_response(message, payload)
            return

        if msg_type == "update_config":
            applied = sm.apply_overrides(msg_data.get("personas", {}))
            logger.info(f"Applied persona overrides: {applied}")
            await rtvi.send_server_response(message, {"ok": True, "applied": applied})
            return

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    _ensure_file_log_sink()
    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        logger.error(f"Unsupported runner args type: {type(runner_args)}")
        return
    transport: SmallWebRTCTransport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
