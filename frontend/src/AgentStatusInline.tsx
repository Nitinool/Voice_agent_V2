/**
 * AgentStatusInline —— 嵌入头像栏的极简状态指示.
 *
 * 一个圆点 + 一个状态文字。
 * 连接 + 阶段 合并显示：
 *   未连接/连接中 → "未连接" / "连接中"
 *   已连接：
 *     idle → Listening（只要连得上就默认在听，用户感知更直观）
 *     listening/thinking/speaking → 保持原样
 */
import { usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';
import { useAgentState, type AgentPhase } from './useAgentState';

function phaseLabel(phase: AgentPhase): string {
  switch (phase) {
    case 'idle':    // 连上但 idle → 统一显示 Listening
    case 'listening':
      return 'Listening';
    case 'thinking':
      return 'Thinking';
    case 'speaking':
      return 'Speaking';
    default:
      return 'Idle';
  }
}

function phaseColor(phase: AgentPhase): string {
  switch (phase) {
    case 'idle':    // idle / listening 同色（都是 "待命听"）
    case 'listening':
      return '#3b82f6';
    case 'thinking':
      return '#f59e0b';
    case 'speaking':
      return '#22c55e';
    default:
      return 'var(--color-muted-foreground)';
  }
}

export function AgentStatusInline() {
  const { isConnected, isConnecting } = usePipecatConnectionState();
  const { phase } = useAgentState();

  let dotColor: string;
  let label: string;
  let pulse = false;

  if (isConnecting) {
    dotColor = '#f59e0b';
    label = 'Connecting';
    pulse = true;
  } else if (!isConnected) {
    dotColor = '#6b7280';
    label = 'Offline';
  } else {
    dotColor = phaseColor(phase);
    label = phaseLabel(phase);
    // 只要不是 idle（即用户真正在说 / AI 在想 / AI 在说），才加呼吸
    // idle/listening（系统在待听，但是安静的）都不 pulse
    pulse = phase !== 'idle';
  }

  return (
    <span className="agent-status-inline" title={label}>
      <span
        className={pulse ? 'agent-status-inline-dot is-pulse' : 'agent-status-inline-dot'}
        style={{ background: dotColor }}
      />
      <span className="agent-status-inline-label">{label}</span>
    </span>
  );
}
