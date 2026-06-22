/**
 * usePersonaPlasmaState —— 根据 agent phase 调 Plasma 动画参数.
 *
 * 跟 usePersonaPlasma（颜色）解耦：本 hook 只动 *动画* 类配置项
 * （plasmaSpeed / ringSpeed / intensity / ring* 等），不动颜色 / persona。
 *
 * 状态映射：
 *   idle       → 慢、柔、暗（安静呼吸）
 *   listening  → 中速、环明显（在听，有节奏）
 *   thinking   → 快、躁动、内聚（脑子转得快）
 *   speaking   → 中速、幅度大、外扩（正在表达）
 *
 * Plasma 内部 `lerpSpeed` 自动把参数变化做平滑过渡，所以这里只需要 push 目标值.
 */
import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';
import type { PlasmaConfig, PlasmaRef } from '@pipecat-ai/voice-ui-kit/webgl';
import { useAgentState, type AgentPhase } from './useAgentState';

export interface UsePersonaPlasmaStateOptions {
  /** Plasma 实例的 ref —— 由调用方持有，与 usePersonaPlasma 共用 */
  plasmaRef: RefObject<PlasmaRef | null>;
}

/** 每个 phase 的目标动画参数 —— 当前 4 个状态都设为 voice-ui-kit 默认值，等你手动调整.
 *
 *  全部可调参数（参考 PlasmaConfig，节选）：
 *    plasmaSpeed      0–3    背景流动速度
 *    ringSpeed        0–3    圆环旋转速度
 *    ringAmplitude    0–2    圆环波动幅度
 *    ringSpread       0–2    圆环间距
 *    ringVisibility   0–1    圆环可见度（透明度）
 *    ringCount        int    圆环数量
 *    ringDistance     0–2    圆环到中心的距离
 *    ringThickness    0–20   圆环粗细
 *    ringSharpness    0–10   圆环边缘锐利度
 *    ringSegments     int    圆环分段数
 *    ringBounce       0–2    圆环弹性
 *
 *  谨慎使用（会改变整体大小/强度）：
 *    intensity / effectScale / radius
 */
const PHASE_CONFIG: Record<AgentPhase, Partial<PlasmaConfig>> = {
  idle: {
    plasmaSpeed: 1,
    ringSpeed: 1.2,
    ringAmplitude: 0.03,
    ringSpread: 0.08,
    ringVisibility: 0.16,
  },
  listening: {
    plasmaSpeed: 0.3,
    ringSpeed: 1.2,
    ringAmplitude: 0.03,
    ringSpread: 0.08,
    ringVisibility: 0.32,
  },
  thinking: {
    plasmaSpeed: 0.3,
    ringSpeed: 1.2,
    ringAmplitude: 0.03,
    ringSpread: 0.2,
    ringVisibility: 0.32,
  },
  speaking: {
    plasmaSpeed: 0.6,
    ringSpeed: 2,
    ringAmplitude: 0.3,
    ringSpread: 0.2,
    ringVisibility: 0.32,
  },
};

export function usePersonaPlasmaState(options: UsePersonaPlasmaStateOptions): void {
  const { plasmaRef } = options;
  const { phase } = useAgentState();
  const lastPhaseRef = useRef<AgentPhase | null>(null);

  useEffect(() => {
    if (phase === lastPhaseRef.current) return;
    const cfg = PHASE_CONFIG[phase];
    if (!cfg) return;
    plasmaRef.current?.updateConfig(cfg);
    lastPhaseRef.current = phase;
  }, [phase, plasmaRef]);
}
