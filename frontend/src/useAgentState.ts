/**
 * useAgentState —— 从 RTVI 事件流推断 bot 当前会话阶段.
 *
 * 用状态机重放（从前往后扫 events，started 设状态、stopped 回 idle），
 * 比单查最后一条事件精确 —— 能正确处理「bot 说完话回到 idle」.
 *
 * 风格对齐官方 hook：UseXxxResult + readonly 字段 + TSDoc.
 *
 * 状态机：
 *   userStartedSpeaking → listening
 *   userStoppedSpeaking  → listening? idle
 *   botLlmStarted        → thinking
 *   botLlmStopped        → thinking? idle
 *   botStartedSpeaking   → speaking
 *   botStoppedSpeaking   → speaking? idle
 *
 * connecting 不在这里推（走 usePipecatConnectionState 更准），调用方自行合并。
 */
import { useMemo } from 'react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';

export type AgentPhase = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface UseAgentStateResult {
  /** 当前会话阶段 */
  readonly phase: AgentPhase;
}

const START_PHASE: Record<string, AgentPhase> = {
  userStartedSpeaking: 'listening',
  botLlmStarted: 'thinking',
  botStartedSpeaking: 'speaking',
};

export function useAgentState(): UseAgentStateResult {
  const { events } = usePipecatEventStream({ maxEvents: 500 });

  const phase = useMemo<AgentPhase>(() => {
    let s: AgentPhase = 'idle';
    for (let i = 0; i < events.length; i++) {
      const t = (events[i] as any)?.type as string | undefined;
      if (!t) continue;
      if (t in START_PHASE) {
        s = START_PHASE[t];
      } else if (t === 'userStoppedSpeaking' && s === 'listening') {
        s = 'idle';
      } else if (t === 'botLlmStopped' && s === 'thinking') {
        s = 'idle';
      } else if (t === 'botStoppedSpeaking' && s === 'speaking') {
        s = 'idle';
      }
    }
    return s;
  }, [events]);

  return { phase } as const;
}
