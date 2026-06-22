/**
 * usePersonaPlasma —— 把 RTVI persona_switch 事件桥接到 Plasma 配色.
 *
 * 风格对齐 voice-ui-kit 自有 hook（usePipecatEventStream / usePipecatConnectionState）：
 * - `UsePersonaPlasmaOptions` / `UsePersonaPlasmaResult` 接口
 * - readonly 返回字段
 * - 副作用全部走 useEffect，hook 本体不直接操作 DOM
 *
 * 用法：
 *   const plasmaRef = useRef<PlasmaRef>(null);
 *   const { activePersonaId } = usePersonaPlasma({ plasmaRef });
 *   <Plasma ref={plasmaRef} initialConfig={...} />
 */
import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';
import type { PlasmaRef } from '@pipecat-ai/voice-ui-kit/webgl';

import { DEFAULT_PERSONA, getPersona } from './config';

export interface UsePersonaPlasmaOptions {
  /** Plasma 实例的 ref —— 由调用方持有，挂在 <Plasma ref={...}/> 上 */
  plasmaRef: RefObject<PlasmaRef | null>;
  /** 颜色过渡速度（0.1 - 3.0，传给 PlasmaConfig.colorCycleSpeed）。默认 1.0 */
  colorCycleSpeed?: number;
}

export interface UsePersonaPlasmaResult {
  /** 当前活跃 persona id（无 persona_switch 事件时回落到 DEFAULT_PERSONA） */
  readonly activePersonaId: string;
}

/**
 * Drive Plasma's `color1` / `color2` / `color3` from RTVI `persona_switch`
 * server messages. Reads `plasmaColors` from the persona registry and pushes
 * `updateConfig({useCustomColors:true, color1, color2, color3})` whenever the
 * active persona changes. The Plasma WebGL shader interpolates between colors
 * using its own `colorCycleSpeed`, so the transition is smooth without extra
 * tweening here.
 */
export function usePersonaPlasma(
  options: UsePersonaPlasmaOptions,
): UsePersonaPlasmaResult {
  const { plasmaRef, colorCycleSpeed = 1.0 } = options;
  const { events } = usePipecatEventStream({ maxEvents: 200 });

  const [activePersonaId, setActivePersonaId] = useState<string>(DEFAULT_PERSONA);
  // 防抖：同一 persona 重复推送时，不重复 updateConfig
  const lastAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    // 倒序找最近一条 persona_switch
    let next: string | null = null;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i] as any;
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'persona_switch' &&
        d.persona
      ) {
        next = String(d.persona);
        break;
      }
    }
    if (!next || next === lastAppliedRef.current) return;

    const cfg = getPersona(next);
    const [color1, color2, color3] = cfg.plasmaColors;
    plasmaRef.current?.updateConfig({
      useCustomColors: true,
      color1,
      color2,
      color3,
      colorCycleSpeed,
    });
    lastAppliedRef.current = next;
    setActivePersonaId(next);
  }, [events, plasmaRef, colorCycleSpeed]);

  return { activePersonaId } as const;
}
