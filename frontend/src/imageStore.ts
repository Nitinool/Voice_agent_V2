/**
 * imageStore —— 图片生成结果存储（前端展示用）.
 *
 * 后端 generate_image 工具生成图后，推 RTVIServerMessageFrame{type:'image',url,prompt,id}
 * 给前端。ImageMessageListener 监听并存到这里（按 id 去重），PersonaConversation 渲染 <img>。
 *
 * 图片 URL 是本地 /generated/<id>.jpeg（vite serve public/generated/），稳定无时效。
 */

export interface GeneratedImage {
  id: string;
  url: string;
  prompt: string;
}

let images: GeneratedImage[] = [];
const listeners = new Set<() => void>();

export function addImage(id: string, url: string, prompt: string): void {
  // 按 id 去重（事件流重复触发时不会重复添加）
  if (images.some((i) => i.id === id)) return;
  images = [...images, { id, url, prompt }];
  emit();
}

export function getImages(): GeneratedImage[] {
  return images;
}

export function clearImages(): void {
  images = [];
  emit();
}

export function subscribeImages(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(): void {
  for (const fn of listeners) fn();
}
