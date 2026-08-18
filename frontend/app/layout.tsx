import type { Metadata } from "next";

import "../styles/globals.css";
import { WorkbenchShell } from "../components/workbench-shell";
import { I18nProvider } from "../components/i18n-provider";

export const metadata: Metadata = {
  title: "研究台面 | Quant 控制面",
  description: "可审计的量化研究控制面",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <I18nProvider>
          <WorkbenchShell>{children}</WorkbenchShell>
        </I18nProvider>
      </body>
    </html>
  );
}
