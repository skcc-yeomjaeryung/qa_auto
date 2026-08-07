/** Logged-in user identity — projects are scoped per user. */
const KEY = "ai_test_user_id";
const NAME_KEY = "ai_test_user_name";

export function getCurrentUserId(): string {
  if (typeof window === "undefined") return "TEST";
  return window.localStorage.getItem(KEY) || "TEST";
}

export function getCurrentUserName(): string {
  if (typeof window === "undefined") return "TEST 사용자";
  return window.localStorage.getItem(NAME_KEY) || "TEST 사용자";
}
