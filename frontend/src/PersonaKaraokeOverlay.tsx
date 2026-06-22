/**
 * PersonaKaraokeOverlay —— plasma 下方的字幕（karaoke 模式，照搬 prebuilt karaoke tab）.
 *
 * 取 usePipecatConversation 返回的 messages 里最后一条 assistant message，
 * 渲染它所有 parts 的 {spoken, unspoken}：
 *   spoken   → 纯黑（继承色）
 *   unspoken → 35% 灰
 *
 * 字幕只在 AI 真正说话时显示：
 *   speaking → 立即显示（visible）
 *   idle     → 等 1s 再启动 800ms 渐隐（让最后一句话留个尾巴）
 *   thinking → 立刻隐藏（bot 正在生成新回复，上一条已无关）
 *   listening→ 立刻隐藏（用户在说话，自己的话不该叠在 plasma 上）
 *
 * 这套规则解决了"用户输入文字时仍然显示上一条 AI 回复"的问题 ——
 * 之前 phase 离开 idle 一律 setVisibility('visible')，会把已经 fade 掉的
 * 旧消息又拉回来.
 */
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  usePipecatConversation,
  usePipecatClient,
  type ConversationMessage,
  type BotOutputText,
} from '@pipecat-ai/client-react';
import { useAgentState } from './useAgentState';

function isBotOutputText(t: unknown): t is BotOutputText {
  return !!t && typeof t === 'object' && 'spoken' in t && 'unspoken' in t;
}

/** idle → wait → fading → hidden 状态机的 timer 配置（ms） */
const HOLD_BEFORE_FADE = 1000;
const FADE_DURATION = 800;

export function PersonaKaraokeOverlay() {
  // 在 PipecatClient 创建完成前 PipecatAppBase 渲染 children 时没有 Provider；
  // 此时不能调 usePipecatConversation（会因 useConversationContext 抛错）.
  const client = usePipecatClient();
  if (!client) return null;
  return <PersonaKaraokeOverlayInner />;
}

function PersonaKaraokeOverlayInner() {
  const { messages } = usePipecatConversation();
  const { phase } = useAgentState();

  // 取最后一条 assistant message
  const last = useMemo<ConversationMessage | null>(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return messages[i];
    }
    return null;
  }, [messages]);

  // 三态：visible（正常显示）/ fading（透明度过渡中）/ hidden（彻底 unmount）
  const [visibility, setVisibility] = useState<'visible' | 'fading' | 'hidden'>('hidden');
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 清掉所有 timer 的工具
  const clearTimers = () => {
    if (holdTimerRef.current) clearTimeout(holdTimerRef.current);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    holdTimerRef.current = null;
    fadeTimerRef.current = null;
  };

  useEffect(() => {
    clearTimers();
    if (phase === 'speaking') {
      // bot 正在说话 → 立即 visible
      setVisibility('visible');
      return;
    }
    if (phase === 'idle') {
      // 刚说完 / 还没说 —— 留 1s 尾巴再 fade（hidden 状态保持 hidden 即可）
      if (visibility === 'visible') {
        holdTimerRef.current = setTimeout(() => {
          setVisibility('fading');
          fadeTimerRef.current = setTimeout(() => {
            setVisibility('hidden');
          }, FADE_DURATION);
        }, HOLD_BEFORE_FADE);
        return clearTimers;
      }
      return;
    }
    // listening / thinking → 立刻隐藏，避免上一条 AI 回复回弹
    setVisibility('hidden');
  }, [phase]);

  if (!last) return null;
  if (visibility === 'hidden') return null;

  // 内容全空（刚创建 placeholder 还没收到 BotOutput）→ 不渲染
  const hasContent = last.parts.some((p) => {
    const t = p.text;
    if (isBotOutputText(t)) return (t.spoken + t.unspoken).length > 0;
    if (typeof t === 'string') return t.length > 0;
    return false;
  });
  if (!hasContent) return null;

  return (
    <div
      className={`karaoke-overlay ${visibility === 'fading' ? 'is-fading' : ''}`}
      style={{ ['--fade-duration' as any]: `${FADE_DURATION}ms` }}
    >
      {last.parts.map((p, i) => {
        const t = p.text;
        if (isBotOutputText(t)) {
          return (
            <Fragment key={i}>
              {t.spoken && <span className="karaoke-spoken">{t.spoken}</span>}
              {t.unspoken && <span className="karaoke-unspoken">{t.unspoken}</span>}
            </Fragment>
          );
        }
        if (typeof t === 'string' && t) {
          return <span key={i} className="karaoke-spoken">{t}</span>;
        }
        return null;
      })}
    </div>
  );
}
