/**
 * SendTextInput —— 自有 minimal 文本输入.
 *
 * 不用 voice-ui-kit 的 TextInput —— 它默认行为是 inject + sendText 都做，
 * 但样式上和我们的 ControlBar 配色不完全对齐。这里复刻 prebuilt 的两步动作：
 *   1. client.sendText(content)  —— 触发后端 LLM 接管
 *   2. injectMessage({role:'user', parts:[{text, final:true, ...}]}) —— 立即写入前端会话流
 *
 * 这样 PersonaConversation 通过 usePipecatConversation 拿到的 messages 就会立刻包含这条 user 消息，
 * 不再需要 window CustomEvent 桥接.
 */
import { useState, type KeyboardEvent } from 'react';
import { Input, Button, usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';
import { usePipecatClient, useConversationContext } from '@pipecat-ai/client-react';

export function SendTextInput() {
  // 同样防御：client 未就绪时 PipecatAppBase 没挂 ConversationProvider，不能调 useConversationContext
  const client = usePipecatClient();
  if (!client) return <SendTextInputFallback />;
  return <SendTextInputInner client={client} />;
}

function SendTextInputFallback() {
  return (
    <div className="control-text-input">
      <Input value="" disabled placeholder="Initializing…" size="md" />
      <Button disabled size="md" variant="default">Send</Button>
    </div>
  );
}

function SendTextInputInner({ client }: { client: NonNullable<ReturnType<typeof usePipecatClient>> }) {
  const { isConnected } = usePipecatConnectionState();
  const { injectMessage } = useConversationContext();
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);

  const send = async () => {
    const content = text.trim();
    if (!content || !isConnected || sending) return;
    setSending(true);
    try {
      await client.sendText(content, { audio_response: true });
      // 立刻把这条用户消息加入会话流（client.sendText 走 LLM 注入，不触发 userTranscript 事件）
      injectMessage({
        role: 'user',
        parts: [
          {
            text: content,
            final: true,
            createdAt: new Date().toISOString(),
          },
        ],
      });
      setText('');
    } catch (err) {
      console.error('sendText failed', err);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="control-text-input">
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={!isConnected || sending}
        placeholder={isConnected ? 'Type and press Enter to send…' : 'Connect to start'}
        size="md"
      />
      <Button
        onClick={send}
        disabled={!isConnected || !text.trim() || sending}
        size="md"
        variant="default"
      >
        Send
      </Button>
    </div>
  );
}
