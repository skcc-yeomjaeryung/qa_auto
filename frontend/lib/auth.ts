/** Simple fixed-credential login (Pilot). ID: TEST / PS: 1 */

const SESSION_KEY = "ai_test_session";
const USER_ID_KEY = "ai_test_user_id";
const USER_NAME_KEY = "ai_test_user_name";

export const FIXED_LOGIN = { id: "TEST", password: "1" } as const;

export type Session = {
  userId: string;
  userName: string;
  loggedInAt: string;
};

export function isLoggedIn(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.localStorage.getItem(SESSION_KEY));
}

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function login(
  id: string,
  password: string,
): { ok: true; session: Session } | { ok: false; error: string } {
  const normalizedId = id.trim().toUpperCase();
  const normalizedPw = password.trim();
  if (normalizedId !== FIXED_LOGIN.id || normalizedPw !== FIXED_LOGIN.password) {
    return {
      ok: false,
      error: "아이디 또는 비밀번호가 올바르지 않습니다. (TEST / 1)",
    };
  }
  const session: Session = {
    userId: FIXED_LOGIN.id,
    userName: "TEST 사용자",
    loggedInAt: new Date().toISOString(),
  };
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  window.localStorage.setItem(USER_ID_KEY, session.userId);
  window.localStorage.setItem(USER_NAME_KEY, session.userName);
  return { ok: true, session };
}

/** Demo one-click login */
export function loginAsDemo(): Session {
  const result = login(FIXED_LOGIN.id, FIXED_LOGIN.password);
  if (!result.ok) {
    throw new Error(result.error);
  }
  return result.session;
}

export function logout(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_KEY);
}
