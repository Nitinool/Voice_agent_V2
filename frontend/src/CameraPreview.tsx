/**
 * CameraPreview —— 可拖动的摄像头小窗（画中画）+ 摄像头开关.
 *
 * plasma 保留主视觉，摄像头作为小窗浮在 app-stage 上，可拖动到任意位置。
 * 用 PipecatClientVideo(participant="local") 显示本地摄像头画面。
 * 拖动用 pointer 事件（mouse + touch 通用），位置存 state（不持久化，刷新复位）。
 *
 * 连接前 / 摄像头关时不显示小窗。
 */
import { useEffect, useRef, useState } from 'react';
import { PipecatClientVideo, usePipecatClient, usePipecatClientCamControl } from '@pipecat-ai/client-react';
import { usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';

interface Pos {
  x: number;
  y: number;
}

export function CameraPreview() {
  const client = usePipecatClient();
  const { isConnected } = usePipecatConnectionState();
  const { isCamEnabled } = usePipecatClientCamControl();

  // 小窗位置（相对 app-stage 左上角的偏移）。默认右下角，用 null 表示"未拖动过用 CSS 定位"
  const [pos, setPos] = useState<Pos | null>(null);
  const dragging = useRef(false);
  const dragStart = useRef<{ px: number; py: number; ox: number; oy: number }>({ px: 0, py: 0, ox: 0, oy: 0 });
  const stageRef = useRef<HTMLElement | null>(null);

  // 连上后记一下 app-stage 容器，用于计算拖动边界
  useEffect(() => {
    stageRef.current = document.querySelector('.app-stage');
  }, [isConnected]);

  // pointer 拖动
  const onPointerDown = (e: React.PointerEvent) => {
    if (!stageRef.current) return;
    const stage = stageRef.current.getBoundingClientRect();
    const el = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // 初始位置：相对 stage 的左上角偏移
    const startOx = pos ? pos.x : stage.width - el.width - 16;
    const startOy = pos ? pos.y : stage.height - el.height - 16;
    dragging.current = true;
    dragStart.current = { px: e.clientX, py: e.clientY, ox: startOx, oy: startOy };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current || !stageRef.current) return;
    const stage = stageRef.current.getBoundingClientRect();
    const el = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const dx = e.clientX - dragStart.current.px;
    const dy = e.clientY - dragStart.current.py;
    // 边界约束：不拖出 stage
    const nx = Math.max(0, Math.min(dragStart.current.ox + dx, stage.width - el.width));
    const ny = Math.max(0, Math.min(dragStart.current.oy + dy, stage.height - el.height));
    setPos({ x: nx, y: ny });
  };

  const onPointerUp = (e: React.PointerEvent) => {
    dragging.current = false;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  };

  // 未连接 / 摄像头关 → 不显示
  if (!client || !isConnected || !isCamEnabled) return null;

  const style: React.CSSProperties = pos
    ? { left: pos.x, top: pos.y, right: 'auto', bottom: 'auto' }
    : {}; // 无 pos 时用 CSS 默认（右下角）

  return (
    <div
      className="camera-preview"
      style={style}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <PipecatClientVideo participant="local" fit="cover" />
    </div>
  );
}
