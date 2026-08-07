"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, InputField } from "../../components/ui";
import { FIXED_LOGIN, isLoggedIn, login, loginAsDemo } from "../../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [userId, setUserId] = useState<string>(FIXED_LOGIN.id);
  const [password, setPassword] = useState<string>("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (isLoggedIn()) {
      router.replace("/");
    }
  }, [router]);

  function goHome() {
    setDone(true);
    window.setTimeout(() => {
      window.location.assign("/");
    }, 400);
  }

  function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = login(userId, password);
      if (!result.ok) {
        setError(result.error);
        setBusy(false);
        return;
      }
      goHome();
    } catch (e) {
      setError(e instanceof Error ? e.message : "로그인 실패");
      setBusy(false);
    }
  }

  function demoLogin() {
    setBusy(true);
    setError(null);
    try {
      loginAsDemo();
      setUserId(FIXED_LOGIN.id);
      setPassword(FIXED_LOGIN.password);
      goHome();
    } catch (e) {
      setError(e instanceof Error ? e.message : "로그인 실패");
      setBusy(false);
    }
  }

  return (
    <div className="login-shell is-saas" data-testid="login-page">
      <div className="login-bg" aria-hidden>
        <img className="login-bg-shape" src="/saas-mock/sign-in-bg-shape.svg" alt="" />
        <img className="login-bg-lines" src="/saas-mock/sign-in-lines.svg" alt="" />
        <img className="login-bg-geometry" src="/saas-mock/sign-in-geometry.svg" alt="" />
      </div>

      <div className="login-stack">
        <div className="login-brand">
          <span className="login-brand-mark" aria-hidden>
            AI
          </span>
          <strong>AI_TEST</strong>
        </div>

        <main className="login-card anim-fade-in">
          <h1>계정에 로그인</h1>
          <p className="login-lead">
            데모 계정으로 로그인한 뒤 프로젝트를 생성하면 분석·시나리오·실행을 사용할 수 있습니다.
          </p>

          {done ? (
            <div className="login-pane anim-slide-up" data-testid="login-success">
              <p className="login-success">로그인되었습니다. 대시보드로 이동합니다…</p>
            </div>
          ) : (
            <form
              className="login-pane anim-slide-up"
              data-testid="login-form"
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <InputField
                label="아이디"
                name="userId"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                autoComplete="username"
                data-testid="login-id"
              />
              <InputField
                label="비밀번호"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="1"
                data-testid="login-password"
                action={
                  <span className="login-demo-hint">
                    데모 · <strong>TEST</strong> / <strong>1</strong>
                  </span>
                }
                trailing={
                  <button
                    type="button"
                    className="ui-field-icon-btn"
                    aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"}
                    onClick={() => setShowPassword((v) => !v)}
                  >
                    <img src="/icons/saas/eye.svg" width={16} height={16} alt="" />
                  </button>
                }
              />

              {error && (
                <p className="login-error" data-testid="login-error">
                  {error}
                </p>
              )}

              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                disabled={busy}
                data-testid="login-submit"
              >
                {busy ? "확인 중…" : "계속"}
              </Button>

              <button
                type="button"
                className="login-text-link"
                disabled={busy}
                onClick={demoLogin}
                data-testid="login-demo"
              >
                TEST / 1 로 바로 로그인
              </button>
            </form>
          )}
        </main>

        <footer className="login-foot">
          <p>
            파일럿 콘솔 · <span>Contact</span> · <span>Privacy</span>
          </p>
        </footer>
      </div>
    </div>
  );
}
