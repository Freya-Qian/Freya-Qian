import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProdForge AI",
  description: "Web 端 AI 产品孵化工作台",
  icons: { icon: "/prodforge-logo.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
