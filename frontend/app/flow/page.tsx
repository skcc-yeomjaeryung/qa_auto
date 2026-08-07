import { redirect } from "next/navigation";

/**
 * 구 「플로우」 경로 — 메뉴가 「테스트 시나리오」(/scenarios)로 격상되어 쿼리를 보존해 넘긴다.
 * 북마크·기존 링크(setId · scenarioId · graphId · serviceId)가 깨지지 않게 한다.
 */
export default async function FlowPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string") qs.set(key, value);
    else if (Array.isArray(value) && typeof value[0] === "string") qs.set(key, value[0]);
  }
  if (qs.has("graphId") && !qs.has("view")) qs.set("view", "graph");
  const query = qs.toString();
  redirect(query ? `/scenarios?${query}` : "/scenarios");
}
