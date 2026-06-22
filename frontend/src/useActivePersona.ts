/**
 * useActivePersona —— 当前活跃 persona（监听 RTVI persona_switch）.
 *
 * 倒序找最近一条 persona_switch，回落到 DEFAULT_PERSONA。
 * 复用给 ControlPanel / AgentStatusBar / 任何需要"当前是谁"的组件，
 * 避免每个组件各自内联监听逻辑。
 *
 * 风格对齐官方 hook：UseXxxResult + readonly.
 */
import { useMemo } from 'react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';

import { DEFAULT_PERSONA, getPersona, type PersonaDef } from './config';

export interface UseActivePersonaResult {
  /** 当前活跃 persona id */
  readonly activePersonaId: string;
  /** 当前活跃 persona 完整定义 */
  readonly activePersona: PersonaDef;
}

export function useActivePersona(): UseActivePersonaResult {
  const { events } = usePipecatEventStream({ maxEvents: 200 });

  const { id, persona } = useMemo(() => {
    let foundId: string | null = null;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i] as any;
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'persona_switch' &&
        d.persona
      ) {
        foundId = String(d.persona);
        break;
      }
    }
    const finalId = foundId ?? DEFAULT_PERSONA;
    return { id: finalId, persona: getPersona(finalId) };
  }, [events]);

  return { activePersonaId: id, activePersona: persona } as const;
}
