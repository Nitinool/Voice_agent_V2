/**
 * ImageMessageListener —— 监听后端 image server message，存图片到 imageStore.
 *
 * 后端 generate_image 工具生成图后推 RTVIServerMessageFrame{type:'image',url,prompt,id}，
 * 本组件监听并存到 imageStore（按 id 去重，事件流重复触发不重复添加）。
 * PersonaConversation 据此渲染 <img>。
 *
 * 分内外两层：外层用 usePipecatClient 探测，client 没就绪时 return null。
 */
import { useEffect, useRef } from 'react';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';
import { addImage } from './imageStore';

export function ImageMessageListener() {
  const client = usePipecatClient();
  if (!client) return null;
  return <ImageMessageListenerInner />;
}

function ImageMessageListenerInner() {
  const { events } = usePipecatEventStream({ maxEvents: 500 });
  // 用 ref 记录已处理的 id，避免每次 render 重新遍历时重复 addImage
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const ev of events as any[]) {
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'image' &&
        typeof d.url === 'string' &&
        typeof d.id === 'string'
      ) {
        if (!seen.current.has(d.id)) {
          seen.current.add(d.id);
          addImage(d.id, d.url, String(d.prompt || ''));
        }
      }
    }
  }, [events]);

  return null;
}
