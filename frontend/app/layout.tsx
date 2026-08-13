import type { Metadata } from "next";

import "../styles/globals.css";
import { WorkbenchShell } from "../components/workbench-shell";

export const metadata: Metadata = {
  title: "Research desk | Quant Control Plane",
  description: "Auditable quant research control plane",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <WorkbenchShell>{children}</WorkbenchShell>
      </body>
    </html>
  );
}
