import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "智巡护航 NEXUS-OMNIGUARD · 具身智能决策中枢",
  description: "三亚跨境仓储具身智能巡检决策系统 — 基于 RAG 与 LangGraph 的工业级决策平台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body style={{ margin: 0, padding: 0 }}>{children}</body>
    </html>
  );
}
