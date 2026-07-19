import type { Metadata } from "next";
import "./globals.css";

import { I18nProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "US Importer Hunter · 潜客分析工作台",
  description:
    "为国际货代销售评估美国进口商资格，并生成仅供人工审核的开发信草稿。Qualify US importers and prepare human-reviewed outreach drafts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
