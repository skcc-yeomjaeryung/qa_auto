export async function POST(request: Request) {
  const formData = await request.formData();
  const csv = String(formData.get("csv") ?? "");
  const requestedName = String(formData.get("filename") ?? "export.csv");
  const filename = requestedName.replace(/[^0-9A-Za-z._\-가-힣]/g, "-").slice(0, 120) || "export.csv";

  return new Response(`\uFEFF${csv}`, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
      "Cache-Control": "no-store",
    },
  });
}
