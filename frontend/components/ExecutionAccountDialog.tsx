"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { apiFetch } from "../lib/apiClient";
import { parseCsv } from "../lib/csv";
import { PILOT_SANDBOX_BASE_URL } from "../lib/pilotTarget";
import { Button } from "./ui/Button";
import { InputField } from "./ui/InputField";
import { AssistantGuide } from "./AssistantGuide";

export type ExecutionEnvironmentChoice = {
  id: string;
  name: string;
  frontendBaseUrl: string;
  loginId?: string | null;
  loginRole?: string | null;
  hasLoginSecret?: boolean;
};

export type ExecutionAccountChoice = {
  id: string;
  environmentId: string;
  label: string;
  loginId: string;
  role: string;
  hasSecret: boolean;
  isDefault: boolean;
};

type ScenarioChoice = { scenarioId: string; name: string };

export function ExecutionAccountDialog({
  open,
  projectId,
  environment: initialEnvironment,
  initialAccounts,
  scenarios,
  onClose,
  onConfirm,
}: {
  open: boolean;
  projectId: string;
  environment: ExecutionEnvironmentChoice | null;
  initialAccounts: ExecutionAccountChoice[];
  scenarios: ScenarioChoice[];
  onClose: () => void;
  onConfirm: (environmentId: string, scenarioAccountIds: Record<string, string>) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] = useState(initialEnvironment);
  const [accounts, setAccounts] = useState(initialAccounts);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("관리자 테스트 계정");
  const [role, setRole] = useState("관리자");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setEnvironment(initialEnvironment);
    setAccounts(initialAccounts);
    const fallback = initialAccounts.find((account) => account.isDefault) ?? initialAccounts[0];
    setAssignments(Object.fromEntries(scenarios.map((scenario) => [scenario.scenarioId, fallback?.id ?? ""])));
    setMessage(null);
  }, [open, initialEnvironment, initialAccounts, scenarios]);

  if (!open) return null;

  async function createEnvironmentWithAccount(account: { label: string; role: string; loginId: string; loginPassword: string }) {
    const response = await apiFetch(`/api/projects/${projectId}/environments`, {
      method: "POST",
      body: JSON.stringify({
        name: "실행 시 등록 환경",
        frontendBaseUrl: PILOT_SANDBOX_BASE_URL,
        healthCheckPath: "/",
        browser: "chrome",
        loginId: account.loginId,
        loginPassword: account.loginPassword,
        loginRole: account.role,
        accessNotes: "테스트 수행 전 계정 확인 팝업에서 등록",
      }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "실행환경 등록 실패");
    const nextEnv = body as ExecutionEnvironmentChoice;
    const accountRes = await apiFetch(`/api/environments/${nextEnv.id}/accounts`, { cache: "no-store" });
    const nextAccounts = accountRes.ok ? ((await accountRes.json()) as ExecutionAccountChoice[]) : [];
    setEnvironment(nextEnv);
    setAccounts(nextAccounts);
    return { environment: nextEnv, accounts: nextAccounts };
  }

  async function addAccount() {
    if (!loginId.trim() || !password || !role.trim()) {
      setMessage("계정 ID·PASSWORD·권한을 모두 입력하세요.");
      return;
    }
    setBusy(true);
    try {
      let nextEnvironment = environment;
      let nextAccounts = accounts;
      if (!nextEnvironment) {
        const created = await createEnvironmentWithAccount({ label, role, loginId: loginId.trim(), loginPassword: password });
        nextEnvironment = created.environment;
        nextAccounts = created.accounts;
      } else {
        const response = await apiFetch(`/api/environments/${nextEnvironment.id}/accounts`, {
          method: "POST",
          body: JSON.stringify({ label: label.trim(), role: role.trim(), loginId: loginId.trim(), loginPassword: password, isDefault: nextAccounts.length === 0 }),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || "계정 등록 실패");
        nextAccounts = [...nextAccounts, body as ExecutionAccountChoice];
        setAccounts(nextAccounts);
      }
      const newest = nextAccounts[nextAccounts.length - 1] ?? nextAccounts[0];
      if (newest) setAssignments((current) => Object.fromEntries(scenarios.map((scenario) => [scenario.scenarioId, current[scenario.scenarioId] || newest.id])));
      setPassword("");
      setMessage(`권한 ${role} 계정을 등록했습니다. 비밀번호는 실행기에만 보관됩니다.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "계정 등록 실패");
    } finally {
      setBusy(false);
    }
  }

  async function importAccounts(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const rows = parseCsv(await file.text());
      if (rows.length === 0) throw new Error("계정 CSV에 데이터가 없습니다");
      let nextEnvironment = environment;
      const createdAccounts = [...accounts];
      for (const [index, row] of rows.entries()) {
        const account = {
          label: row.label || row["계정명"] || `CSV 계정 ${index + 1}`,
          loginId: row.loginId || row["ID"] || "",
          loginPassword: row.loginPassword || row["PASSWORD"] || "",
          role: row.role || row["권한"] || "사용자",
        };
        if (!account.loginId || !account.loginPassword || account.loginPassword === "작성 필요" || !account.role) {
          throw new Error(`${index + 2}행의 ID·PASSWORD·권한을 확인하세요`);
        }
        if (!nextEnvironment) {
          const created = await createEnvironmentWithAccount(account);
          nextEnvironment = created.environment;
          createdAccounts.splice(0, createdAccounts.length, ...created.accounts);
          continue;
        }
        const response = await apiFetch(`/api/environments/${nextEnvironment.id}/accounts`, {
          method: "POST",
          body: JSON.stringify({ ...account, isDefault: createdAccounts.length === 0 }),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || `${index + 2}행 계정 등록 실패`);
        createdAccounts.push(body as ExecutionAccountChoice);
      }
      setAccounts(createdAccounts);
      const fallback = createdAccounts.find((account) => account.isDefault) ?? createdAccounts[0];
      if (fallback) setAssignments(Object.fromEntries(scenarios.map((scenario) => [scenario.scenarioId, fallback.id])));
      setMessage(`CSV 계정 ${createdAccounts.length}건을 등록했습니다. 시나리오별 권한 계정을 선택하세요.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "계정 CSV 가져오기 실패");
    } finally {
      setBusy(false);
    }
  }

  const ready = Boolean(environment && scenarios.every((scenario) => assignments[scenario.scenarioId]));
  return (
    <div className="modal-backdrop" data-testid="execution-account-dialog">
      <section className="generation-modal account-modal" role="dialog" aria-modal="true" aria-labelledby="account-dialog-title">
        <header><div><p className="panel-kicker">테스트 계정 선택</p><h3 id="account-dialog-title">이 시나리오는 어떤 사용자로 실행할까요?</h3></div><button type="button" className="modal-close" disabled={busy} onClick={onClose} aria-label="닫기">×</button></header>
        <AssistantGuide compact title="계정은 실행에만 안전하게 사용해요" message="권한별 업무 흐름을 재현하며 비밀번호는 화면·로그·증적에 노출하지 않습니다." />
        <div className="account-modal-body">
          <div className={`connect-banner ${accounts.length ? "is-ok" : "is-warn"}`}>
            {accounts.length
              ? `${environment?.name}에서 바로 사용할 수 있는 계정이 ${accounts.length}개 있습니다.`
              : "아직 실행 계정이 없습니다. 로그인 화면을 지나려면 아래에서 계정을 먼저 추가해 주세요."}
          </div>
          <div className="account-add-grid">
            <InputField className="is-compact" label="계정 이름" value={label} onChange={(e) => setLabel(e.target.value)} />
            <InputField className="is-compact" label="사용자 역할" value={role} onChange={(e) => setRole(e.target.value)} placeholder="예: 관리자" />
            <InputField className="is-compact" label="로그인 ID" value={loginId} onChange={(e) => setLoginId(e.target.value)} autoComplete="off" />
            <InputField className="is-compact" label="비밀번호" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
          </div>
          <div className="generation-csv-actions">
            <Button size="sm" variant="secondary" busy={busy} onClick={() => void addAccount()}>계정 추가</Button>
            <a className="ghost-btn" href="/templates/execution-accounts-template.csv" download="execution-accounts-template.csv">계정 CSV 샘플</a>
            <Button size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>계정 CSV 업로드</Button>
            <input ref={fileRef} type="file" className="visually-hidden" accept=".csv,text/csv" onChange={importAccounts} />
          </div>
          {message && <p className="account-message">{message}</p>}
          <div className="account-assignment-list">
            {scenarios.map((scenario) => (
              <label key={scenario.scenarioId}>
                <span><strong>{scenario.name}</strong><em>{scenario.scenarioId}</em></span>
                <select value={assignments[scenario.scenarioId] || ""} onChange={(e) => setAssignments((current) => ({ ...current, [scenario.scenarioId]: e.target.value }))}>
                  <option value="">계정 선택</option>
                  {accounts.filter((account) => account.hasSecret).map((account) => <option key={account.id} value={account.id}>{account.label} · {account.role} · {account.loginId}</option>)}
                </select>
              </label>
            ))}
          </div>
        </div>
        <footer><p>비밀번호는 AI에게 전달하지 않고, 실행 중 로그인할 때만 안전하게 사용합니다.</p><div><Button variant="secondary" disabled={busy} onClick={onClose}>취소</Button><Button disabled={!ready} busy={busy} onClick={() => environment && onConfirm(environment.id, assignments)} data-testid="account-confirm-run">이 계정으로 테스트</Button></div></footer>
      </section>
    </div>
  );
}
