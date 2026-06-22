/**
 * StatusOverlay —— plasma 中央的状态指示浮层.
 *
 * 显示规则：
 *   connecting → SpinLoader + "Connecting…"
 *   listening  → "Listening…"
 *   thinking   → "Thinking…"（纯文字，无动画 —— 跟 listening/speaking 保持统一）
 *   speaking   → "Speaking…"
 *   idle       → 不显示
 *
 * 注意：idle 时一律不输出，连上了但无事发生就保持干净。
 * "Listening" 由后端 userStartedSpeaking 事件触发。
 *
 * 放在 transcript-stage 同区域，karaoke 字幕在 speaking 阶段也会显示，
 * 两者一起出现没问题（字幕居中，状态文字独立一行）.
 */
import {
  SpinLoader,
  usePipecatConnectionState,
} from '@pipecat-ai/voice-ui-kit';
import { useAgentState } from './useAgentState';

export function StatusOverlay() {
  const { isConnected, isConnecting } = usePipecatConnectionState();
  const { phase } = useAgentState();

  // 连接中优先显示
  if (isConnecting || !isConnected) {
    return (
      <div className="status-overlay">
        <SpinLoader />
        <span className="status-label">Connecting…</span>
      </div>
    );
  }

  // 已连接时 idle → "Listening…"，其他阶段按实际显示
  const displayPhase = phase === 'idle' ? 'listening' : phase;

  let label = '';
  if (displayPhase === 'listening') label = 'Listening…';
  else if (displayPhase === 'thinking') label = 'Thinking…';
  else if (displayPhase === 'speaking') label = 'Speaking…';
  else return null;

  return (
    <div className="status-overlay">
      <span className="status-label">{label}</span>
    </div>
  );
}
