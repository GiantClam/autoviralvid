/**
 * MarpSlide v2 — Remotion 中渲染 Marp Markdown (含自定义主题)
 */

import React, { useMemo } from 'react';
import MarpCore from '@marp-team/marp-core';

// 自定义 premium-tech 主题 CSS
const PREMIUM_CSS = `
/* @theme modern-tailwind */
section {
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
  background-color: #f8fafc;
  color: #1e293b;
  font-size: 32px;
  line-height: 1.6;
}
h1 {
  font-size: 56px; font-weight: 800;
  background: linear-gradient(135deg, #1e3a5f, #2563eb);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  border-bottom: 4px solid #cbd5e1; padding-bottom: 12px; margin-bottom: 30px;
}
h2 { font-size: 36px; color: #1e3a5f; font-weight: 700; }
h3 { font-size: 28px; color: #2563eb; font-weight: 600; }
mark {
  background-color: transparent; color: #ef4444; font-weight: 800;
  border-bottom: 4px solid #ef4444; padding-bottom: 2px;
}
strong { color: #1e3a5f; font-weight: 700; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; margin-top: 24px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; margin-top: 24px; }
.card {
  background: white; padding: 28px; border-radius: 16px;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.08); border-top: 6px solid #3b82f6;
}
.card.accent { border-top-color: #8b5cf6; }
.card.success { border-top-color: #22c55e; }
table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-top: 20px;
}
thead { background: linear-gradient(135deg, #1e3a5f, #2563eb); color: white; }
th { padding: 16px 20px; font-weight: 700; text-align: left; font-size: 24px; }
td { padding: 14px 20px; border-bottom: 1px solid #e2e8f0; font-size: 22px; }
tbody tr:nth-child(even) { background-color: #f1f5f9; }
section.lead {
  display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;
  background: linear-gradient(135deg, #0f172a, #1e3a5f); color: white;
}
section.lead h1 {
  background: linear-gradient(135deg, #38bdf8, #a78bfa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  border-bottom: none; font-size: 72px;
}
section.lead mark { color: #38bdf8; border-bottom-color: #38bdf8; }
section.invert { background: linear-gradient(135deg, #0f172a, #1e3a5f); color: #e2e8f0; }
section.invert h1 { background: linear-gradient(135deg, #38bdf8, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
section.invert strong { color: #38bdf8; }
blockquote {
  border-left: 6px solid #3b82f6; background: linear-gradient(90deg, rgba(37,99,235,0.08), transparent);
  padding: 20px 28px; border-radius: 0 12px 12px 0; font-size: 36px; font-style: italic; color: #1e3a5f;
}
ul { list-style: none; padding-left: 0; }
ul li { position: relative; padding-left: 28px; margin-bottom: 12px; }
ul li::before { content: '▸'; position: absolute; left: 0; color: #3b82f6; font-weight: bold; }
.big-number { font-size: 96px; font-weight: 900; background: linear-gradient(135deg, #2563eb, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; line-height: 1.1; }
img { border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
`;


interface MarpSlideProps {
  markdown: string;
  theme?: string;
}

export const MarpSlide: React.FC<MarpSlideProps> = ({ markdown, theme = 'modern-tailwind' }) => {
  const { html, css } = useMemo(() => {
    const marp = new MarpCore({ html: true, inlineSVG: true });

    // 注入自定义主题 CSS
    marp.themeSet.default = marp.themeSet.add(PREMIUM_CSS);

    const fullMd = `---
theme: ${theme}
---
${markdown}`;

    try {
      return marp.render(fullMd);
    } catch (e) {
      return {
        html: `<section class="marpit"><div style="padding:40px;color:#333"><h1>Error</h1><pre>${markdown.substring(0, 200)}</pre></div></section>`,
        css: '',
      };
    }
  }, [markdown, theme]);

  return (
    <div style={{
      width: 1920, height: 1080, position: 'relative',
      overflow: 'hidden',
    }}>
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <style>{`
        section.marpit {
          width: 1920px !important; height: 1080px !important;
          max-width: 1920px !important; max-height: 1080px !important;
          padding: 60px 80px !important; box-sizing: border-box !important;
        }
        section.marpit.lead {
          display: flex !important; flex-direction: column !important;
          justify-content: center !important; align-items: center !important; text-align: center !important;
        }
      `}</style>
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
};
