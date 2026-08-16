import type { Metadata } from "next";

import "../styles/globals.css";
import { WorkbenchShell } from "../components/workbench-shell";
import { I18nProvider } from "../components/i18n-provider";
import { getServerLocale } from "../lib/server-locale";

export const metadata: Metadata = {
  title: "Research desk | Quant Control Plane",
  description: "Auditable quant research control plane",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getServerLocale();
  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body>
        <I18nProvider initialLocale={locale}>
          <WorkbenchShell>{children}</WorkbenchShell>
        </I18nProvider>
      </body>
    </html>
  );
}
