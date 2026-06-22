// Persona 配置 —— 与后端 personas.yaml 对应
// 切换 persona = 前端 disconnect + 用对应 agent 重新 connect（每 agent 独立 session）

export interface PersonaDef {
  id: string;            // 后端 personas.yaml 的 key
  label: string;         // 按钮文字
  color: string;         // 主题色 (chip / msg-bubble border)
  emoji: string;         // 头像占位（M3 之前用 emoji 代替图片）
  wakeWords: string[];   // 唤醒词变体
  /** Plasma 三色渐变 [color1, color2, color3]，传入 PlasmaConfig.color1/2/3 */
  plasmaColors: [string, string, string];
}

export const PERSONAS: PersonaDef[] = [
  {
    id: 'doubao',
    label: '豆包',
    color: '#FFD700',
    emoji: '🤗',
    wakeWords: ['豆包', 'doubao'],
    plasmaColors: ['#FFD700', '#FFA94D', '#FF6B35'], // 金 / 橙 / 红橙 —— 暖活泼
  },
  {
    id: 'xiaoai',
    label: '小爱同学',
    color: '#FF6B6B',
    emoji: '❤️',
    wakeWords: ['小爱', 'xiaoai'],
    plasmaColors: ['#FF6B6B', '#FF1744', '#B2387F'], // 粉 / 玫红 / 紫 —— 温柔
  },
  {
    id: 'siri',
    label: 'Siri',
    color: '#A8DADC',
    emoji: '🎙️',
    wakeWords: ['siri', '西瑞'],
    plasmaColors: ['#A8DADC', '#5DADE2', '#2980B9'], // 青 / 蓝 / 深蓝 —— 克制
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    color: '#1D3557',
    emoji: '🐳',
    wakeWords: ['deepseek', '深度求索'],
    plasmaColors: ['#1D3557', '#3F51B5', '#7B1FA2'], // 深蓝 / 蓝紫 / 紫 —— 理性
  },
];

export const DEFAULT_PERSONA = 'doubao';

export function getPersona(id: string): PersonaDef {
  return PERSONAS.find((p) => p.id === id) ?? PERSONAS[0];
}

// 后端 /start endpoint（走 vite proxy 到 :7860）
export const BOT_START_URL = '/start';
