/**
 * PersonaConversation —— per-persona 对话区（karaoke 模式，照搬 prebuilt）.
 *
 * 数据源：官方公开 hook `usePipecatConversation` —— 与 pipecat_ai_prebuilt 同一 hook.
 *   - assistant 消息的 parts[i].text 是 {spoken, unspoken}，由 hook 内部按 cursor 拆好
 *   - 30s 内同 role 自动合并到一条 message
 *   - BotStoppedSpeaking 2.5s 后自动 finalize
 *
 * persona 标注：单独监听 RTVI serverMessage 的 persona_switch，按 message.createdAt 时间
 * 二分到"消息生成时活跃的 persona"。
 *
 * 显示策略：历史栏不做 karaoke 视觉，spoken + unspoken 拼成完整字符串显示（出现得早即可）.
 * karaoke 灰/黑视觉由独立的 PersonaKaraokeOverlay 字幕组件承担.
 */
import { Fragment, useEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import {
  usePipecatConversation,
  usePipecatClient,
  type ConversationMessage,
  type ConversationMessagePart,
  type BotOutputText,
} from '@pipecat-ai/client-react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';
import { DEFAULT_PERSONA, getPersona } from './config';
import { getHistoryEntries, subscribeHistoryEntries } from './historyPersonaStore';
import { getImages, subscribeImages } from './imageStore';

/** persona_switch 事件按时间戳排序后的轨迹，用于给 message 标 persona. */
interface PersonaSwitchPoint {
  ts: number;
  persona: string;
}

function isBotOutputText(t: unknown): t is BotOutputText {
  return !!t && typeof t === 'object' && 'spoken' in t && 'unspoken' in t;
}

/** 把一个 part 的 text 渲染成普通字符串（spoken + unspoken 拼接）. */
function partToText(part: ConversationMessagePart): string {
  const t = part.text;
  if (isBotOutputText(t)) return t.spoken + t.unspoken;
  if (typeof t === 'string') return t;
  // ReactNode 的其它形态（数字/JSX/null 等）—— 历史栏不展示富内容，回退到空串
  if (t == null) return '';
  return String(t);
}

/** 整条 message 的纯文本内容（拼所有 parts）. */
function messageToText(msg: ConversationMessage): string {
  return msg.parts.map(partToText).join('');
}

/** 按 createdAt 时间戳找该 message 生成时活跃的 persona. */
function personaAt(switches: PersonaSwitchPoint[], createdAt: string): string {
  if (switches.length === 0) return DEFAULT_PERSONA;
  const ts = new Date(createdAt).getTime();
  // 线性倒查（switches 数量极少，<<100）
  for (let i = switches.length - 1; i >= 0; i--) {
    if (switches[i].ts <= ts) return switches[i].persona;
  }
  return DEFAULT_PERSONA;
}

export function PersonaConversation() {
  // PipecatAppBase 在 client 初始化前直接 render children（无 Provider 包裹），
  // 这一帧 usePipecatConversation 会因 useConversationContext 报错。所以先检测.
  const client = usePipecatClient();
  if (!client) return <PersonaConversationFallback />;
  return <PersonaConversationInner />;
}

function PersonaConversationFallback() {
  return (
    <div className="messages">
      <div className="empty">Initializing…</div>
    </div>
  );
}

function PersonaConversationInner() {
  const { messages } = usePipecatConversation();
  const { events } = usePipecatEventStream({ maxEvents: 500 });
  // 历史消息独立存储（不走 jotai，避免被合并且能带 persona 字段）
  const historyEntries = useSyncExternalStore(subscribeHistoryEntries, getHistoryEntries);
  // 生成的图片（后端 generate_image 工具推来的）
  const images = useSyncExternalStore(subscribeImages, getImages);

  // 提取 persona_switch 轨迹（按时间升序）
  const switches = useMemo<PersonaSwitchPoint[]>(() => {
    const out: PersonaSwitchPoint[] = [];
    for (const ev of events as any[]) {
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'persona_switch' &&
        d.persona
      ) {
        const ts = ev?.timestamp ? new Date(ev.timestamp).getTime() : 0;
        out.push({ ts, persona: String(d.persona) });
      }
    }
    return out;
  }, [events]);

  // 头部"当前 persona"用于空状态文案
  const headPersona = switches.length > 0 ? switches[switches.length - 1].persona : DEFAULT_PERSONA;

  // 过滤要显示的消息：只 user / assistant，且非空
  const displayMessages = useMemo(
    () =>
      messages.filter((m) => {
        if (m.role !== 'user' && m.role !== 'assistant') return false;
        return messageToText(m).trim().length > 0;
      }),
    [messages],
  );

  // 自动滚到底部：消息总长度变化时（新消息到达或现有消息内容增长）将滚动条推到 scrollHeight.
  // 用消息总文字长度做依赖，避免增量更新（karaoke 增字）时不触发 scroll.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const totalLen = useMemo(
    () =>
      historyEntries.reduce((sum, m) => sum + m.content.length, 0) +
      displayMessages.reduce((sum, m) => sum + messageToText(m).length, 0),
    [historyEntries, displayMessages],
  );
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [totalLen, displayMessages.length, historyEntries.length]);

  return (
    <div className="messages" ref={scrollRef}>
      {displayMessages.length === 0 && historyEntries.length === 0 && (
        <div className="empty">Once connected, {getPersona(headPersona).label} will say hi…</div>
      )}
      {/* 历史消息（独立存储，自带 persona，准确显示） */}
      {historyEntries.map((h, i) => {
        const key = `h-${i}`;
        if (h.role === 'user') {
          return (
            <div key={key} className="msg user">
              <span className="msg-bubble user">{h.content}</span>
              <span className="msg-you">You</span>
            </div>
          );
        }
        const mp = getPersona(h.persona || DEFAULT_PERSONA);
        return (
          <div key={key} className="msg bot" style={{ ['--c' as any]: mp.color }}>
            <span className="msg-avatar" style={{ background: mp.color }}>{mp.emoji}</span>
            <div className="msg-col">
              <span className="msg-name" style={{ color: mp.color }}>{mp.label}</span>
              <span className="msg-bubble bot" style={{ borderColor: mp.color }}>{h.content}</span>
            </div>
          </div>
        );
      })}
      {/* 实时消息（jotai，persona 靠 persona_switch 轨迹） */}
      {displayMessages.map((msg, i) => {
        const text = messageToText(msg);
        if (msg.role === 'user') {
          return (
            <div key={`l-${i}`} className="msg user">
              <span className="msg-bubble user">{text}</span>
              <span className="msg-you">You</span>
            </div>
          );
        }
        const pid = personaAt(switches, msg.createdAt);
        const mp = getPersona(pid);
        return (
          <div key={`l-${i}`} className="msg bot" style={{ ['--c' as any]: mp.color }}>
            <span className="msg-avatar" style={{ background: mp.color }}>{mp.emoji}</span>
            <div className="msg-col">
              <span className="msg-name" style={{ color: mp.color }}>{mp.label}</span>
              <span className="msg-bubble bot" style={{ borderColor: mp.color }}>{text}</span>
            </div>
          </div>
        );
      })}
      {/* 生成的图片（实时，不进历史） */}
      {images.map((img) => (
        <div key={`img-${img.id}`} className="msg bot">
          <span className="msg-bubble bot msg-image-bubble">
            <img src={img.url} alt={img.prompt} className="msg-image" />
            <span className="msg-image-prompt">{img.prompt}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// 抑制未使用的 Fragment（保留 import 以便后续渲染富内容）
void Fragment;
