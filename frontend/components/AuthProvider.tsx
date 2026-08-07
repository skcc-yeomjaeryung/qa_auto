"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { isLoggedIn } from "../lib/auth";
import { installApiAuthFetch } from "../lib/apiClient";

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    installApiAuthFetch();
  }, []);

  useEffect(() => {
    const logged = isLoggedIn();

    if (!logged && !isLogin) {
      setReady(false);
      router.replace("/login");
      return;
    }

    if (logged && isLogin) {
      setReady(true);
      router.replace("/");
      return;
    }

    setReady(true);
  }, [pathname, isLogin, router]);

  // Login page always renders immediately (no blank "세션 확인 중")
  if (isLogin) {
    return <>{children}</>;
  }

  if (!ready) {
    return (
      <div className="auth-boot" data-testid="auth-boot">
        <p>세션 확인 중…</p>
      </div>
    );
  }

  return <>{children}</>;
}
