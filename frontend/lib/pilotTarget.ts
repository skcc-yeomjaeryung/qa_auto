/**
 * 파일럿 샌드박스 기본 실행 대상 (SSOT).
 * Backend: app/services/environment_models.PILOT_SANDBOX_BASE_URL 과 값을 맞춘다.
 */
export const CYMBAL_BANK_ORIGIN = "https://cymbal-bank.fsi.cymbal.dev";
export const CYMBAL_BANK_HOME_PATH = "/home";
export const PILOT_SANDBOX_NAME = "Pilot Sandbox";
/** 연결 URL은 origin이다. 진입 화면(`/home`)은 health check 경로로 따로 쓴다. */
export const PILOT_SANDBOX_BASE_URL = CYMBAL_BANK_ORIGIN;
