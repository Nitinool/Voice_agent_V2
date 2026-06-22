import { createRoot } from 'react-dom/client';
import { ThemeProvider } from '@pipecat-ai/voice-ui-kit';
import App from './App';
import './index.css';

// 固定 light mode：disableStorage 让 ThemeProvider 不读 localStorage，
// 每次刷新都回到 light. demo 不暴露主题切换.
createRoot(document.getElementById('root')!).render(
  <ThemeProvider defaultTheme="light" disableStorage>
    <App />
  </ThemeProvider>
);
