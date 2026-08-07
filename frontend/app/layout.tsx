import type { ReactNode } from "react";
import { AppShell } from "../components/AppShell";
import "./styles.css";

export const metadata = {
  title: "AI_TEST 품질 콘솔",
  description: "Code-to-E2E 관통 테스트 품질 콘솔",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" data-brand="sk">
      <body className="is-soft-shell">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
