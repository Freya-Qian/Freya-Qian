import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AI Avatar Twin · 数字人短视频工作台',
  description: '面向 AI 行业内容创作者的选题发现 → 脚本生成 → 数字人口播视频制作工作台',
  icons: { icon: '/brand-mark.svg' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
