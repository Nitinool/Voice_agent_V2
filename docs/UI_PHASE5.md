# UI Phase 5：字幕 / 历史 与音频"同步显示"（karaoke 模式）

> 当前问题：字幕和历史栏要等 bot 念完一整句后才显示（滞后 1–3s）。
> 这一版照搬 `pipecat_ai_prebuilt` 的做法，让字幕跟音频开口同步出现，逐句"灰→黑"。

---

## 1. 当前为什么会滞后

字幕（voice-ui-kit 的 `TranscriptOverlay`）和历史栏（我们自己写的 `PersonaConversation`）都在事件流里过滤
`botOutput` 的 `spoken === true`：

```ts
if ((t === 'botOutput' || t === 'bot-output') && d?.spoken === true && d?.text) { ... }
```

而 pipecat 后端只有在 **整句 TTS 合成完毕、对应 audio chunks 全部追加到 audio context 后** 才会推
`TTSTextFrame` —— observer 拿到它才发 `spoken=true` 的 `bot-output` 事件
（`pipecat/processors/frameworks/rtvi/observer.py:722-748`）。

→ 音频已经播了几秒，文字才到。

---

## 2. prebuilt 的做法（最终参照）

prebuilt 字幕用的是 `@pipecat-ai/client-react@1.6.0` 的公开 hook **`usePipecatConversation`**：

| 行为 | 实现位置 | 数据 |
|------|----------|------|
| 监听 `BotOutput`（含 `spoken=true/false`）→ 写入 jotai atom | `client-react/dist/index.js:1081`, `1196-1211` | 一个 assistant message 的 `parts[]` 累积 |
| 维护 cursor `(currentPartIndex, currentCharIndex)` | atom `Bo` | 当前已说到哪个 part 的哪个字符 |
| 渲染时按 cursor 把 `parts[i].text` 拆成 `{spoken, unspoken}` | hook 内 `useMemo`（`index.js:2458`） | 给消费者的已经是切好的 |
| 30 秒内同 role 自动合 1 条 message | `i$()`（`index.js:5337` in prebuilt bundle） | 一轮多句 → 一个气泡 |
| `BotStoppedSpeaking` 后 2.5s 把 cursor 推到末尾、标 final | `index.js:1007-1080` | unspoken 全变 spoken（视觉上整句变黑） |
| 字幕不 fade、不清空 | `xQ`/`SQ` 渲染（prebuilt bundle ~11000） | 三种模式 Karaoke/Captions/Instant，karaoke 用 `text-muted-foreground` class 给 unspoken 上灰色 |

### 同步感的来源

`BotOutput` 的 `spoken=false`（unspoken 预览）事件，在 observer 里被 queued（`observer.py:626-629`），
**等 `BotStartedSpeakingFrame` 到了才 flush** —— 即 **bot 真正开口的瞬间，unspoken 文字到达前端**。
所以 prebuilt 看起来"文字跟音频同步开始"，本质上是 unspoken 字幕跟音频开口对齐。

### Mimo 这种无 word-timestamp 的 TTS 会怎样

后端按句只会发 `new`（`spoken=false`，整句在 remaining_text）和 `completed`（`spoken=true`，整句在 accumulated_text）两次。
cursor 跳 0 → 整句尾。视觉上 = **整句一次性灰 → 该句念完瞬间整句变黑**。
这正是你之前用 prebuilt + 普通 TTS 时的"同步"感。

---

## 3. 关键依赖确认（全部 verified）

| 依赖 | 确认 |
|------|------|
| `usePipecatConversation` 是 `@pipecat-ai/client-react` 公开 export | ✅ `client-react/dist/index.d.ts:1462` |
| 返回 `messages` + `injectMessage` + `botOutputEvents` | ✅ 同上 |
| `BotOutputText = { spoken: string, unspoken: string }` | ✅ `index.d.ts:16-19` |
| `ConversationMessagePart.text: ReactNode \| BotOutputText` | ✅ `index.d.ts:81-87` |
| `PipecatClientProvider` 内部已经包了 `PipecatConversationProvider` | ✅ `client-react/dist/index.js:1787`（PipecatAppBase 已挂 PipecatClientProvider，无需再包） |
| `useConversationContext().injectMessage` 可用于 demo 自注入 user 消息 | ✅ `index.d.ts:947-958` |
| voice-ui-kit 的 `ConversationProvider` 是 `@deprecated` no-op | ✅ `voice-ui-kit/dist/index.d.ts:1781-1786`（不用包） |

---

## 4. 改动清单

| # | 文件 | 类型 | 改什么 |
|---|------|------|--------|
| 1 | `src/PersonaConversation.tsx` | 重写 | 用 `usePipecatConversation` 取代手写 `usePipecatEventStream` 拼装；persona 标注仍走 `usePipecatEventStream` 监 `persona_switch` |
| 2 | `src/SendTextInput.tsx` | 改 | 发送成功后 `injectMessage({role:'user', parts:[{text, final:true, ...}]})` 替代 window CustomEvent |
| 3 | `src/PersonaKaraokeOverlay.tsx` | 新建 | 取 `messages` 最后一条 assistant，渲染所有 parts 的 `{spoken, unspoken}`，spoken 黑 / unspoken 灰 |
| 4 | `src/App.tsx` | 改 1 行 | `<TranscriptOverlay participant="remote">` → `<PersonaKaraokeOverlay/>` |
| 5 | `src/index.css` | 加 | `.karaoke-overlay` + `.karaoke-spoken` + `.karaoke-unspoken` 样式 |

---

## 5. 设计要点

### 5.1 PersonaConversation 重构思路

- `usePipecatConversation()` 给的 `messages` 是顶级真实状态（cursor 拆分、合并、防抖都做完了）。
- assistant 消息：把所有 parts 的 `{spoken, unspoken}` 拼成 `spoken + unspoken` 完整字符串显示在气泡里（历史不需要 karaoke 视觉，只要"出现得早"）。
- user 消息：`parts[].text` 通常是字符串 / ReactNode，直接 `String(text)` 即可（语音转写 + 文本注入都是字符串）。
- persona 标注：单独 `usePipecatEventStream({ includeEvents: [RTVIEvent.ServerMessage] })` 收集 `persona_switch` 事件，按 message 的 `createdAt` 二分 / 线性查找最近一次切换。

### 5.2 PersonaKaraokeOverlay 渲染规则

```tsx
const { messages } = usePipecatConversation();
const last = useMemo(() => {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') return messages[i];
  }
  return null;
}, [messages]);

if (!last) return null;

return (
  <div className="karaoke-overlay">
    {last.parts.map((p, i) => {
      const t = p.text;
      if (t && typeof t === 'object' && 'spoken' in t) {
        return (
          <Fragment key={i}>
            {t.spoken && <span className="karaoke-spoken">{t.spoken}</span>}
            {t.unspoken && <span className="karaoke-unspoken">{t.unspoken}</span>}
          </Fragment>
        );
      }
      return <Fragment key={i}>{String(t ?? '')}</Fragment>;
    })}
  </div>
);
```

**不做 fadeOut**（照官方）。说完的字留在屏幕上；下一轮 bot 开口时 `usePipecatConversation` 会创建新 message
（如果间隔 >30s）或在当前 message 上加新 parts。`UserStartedSpeaking` 时可选地加 `is-hiding` class 触发 CSS fade
（这一步先不做，先看自然行为是否够看）。

### 5.3 SendTextInput 注入策略

`prebuilt` 的文本输入（`AQ` 组件，prebuilt bundle line 102 / offset ~16907）做了两件事：
1. `client.sendText(content)` —— 触发后端 LLM 接管
2. `injectMessage({role:'user', parts:[{text:content, final:true, ...}]})` —— 立即在前端历史显示

我们改成完全一致。删掉 `window.dispatchEvent('voice-agent:user-text', ...)`，
`PersonaConversation` 里那段 window 监听一并删掉。

### 5.4 字幕样式（CSS）

```css
.karaoke-overlay {
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.04em;
  line-height: 1.5;
  text-align: center;
  color: #000;
  word-break: break-word;
}
.karaoke-spoken   { color: #000; }
.karaoke-unspoken { color: rgba(0, 0, 0, 0.4); }
```

延用现有 `.transcript-stage` 的居中 / 宽度容器。

---

## 6. 风险与边界

| 边界 | 表现 | 处理 |
|------|------|------|
| 被打断 | 2.5s 后 cursor 跳到末尾，未说完的 unspoken 整段变黑 | 接受（prebuilt 行为） |
| 一轮 3 句 | 合并到一个 assistant message，3 个 parts；当前正说那句灰，已说的黑 | 自然处理 |
| 一直没新轮次 | 字幕停在最后一条 assistant 上不消失 | 接受；后续如需可加 UserStartedSpeaking 隐藏 |
| 文本注入 vs 真实回复顺序 | 注入是同步加 parts，sendText 触发的 LLM 回复是后续 BotOutput 写入 | jotai 原子保序，无问题 |
| local 字幕 | 保留官方 `<TranscriptOverlay participant="local">` | STT 没有 spoken/unspoken 概念 |

---

## 7. 验证

1. `pnpm exec tsc --noEmit` 0 错
2. 文本输入回车 → 历史立刻出现 user 气泡（同 prebuilt）
3. bot 开口瞬间 → 字幕灰色文字出现；该句念完瞬间整句变黑
4. 多句连续输出 → 一个气泡逐句黑化
5. 历史栏的 bot 气泡 → 内容跟字幕同步增长（不再滞后）
6. 切 persona / 多 agent → 历史里仍按 persona 着色（persona_switch 标注仍工作）
