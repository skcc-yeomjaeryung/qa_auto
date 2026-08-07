export type CsvRow = Record<string, string>;

export function parseCsv(text: string): CsvRow[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell.trim());
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell.trim());
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell.trim());
  if (row.some((value) => value !== "")) rows.push(row);
  if (rows.length < 2) return [];
  const headers = rows[0].map((header) => header.replace(/^\uFEFF/, "").trim());
  return rows.slice(1).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

export function stringifyCsv(headers: string[], rows: Array<Array<string | number | null | undefined>>): string {
  const escape = (value: string | number | null | undefined) => {
    const text = value == null ? "" : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [headers, ...rows].map((row) => row.map(escape).join(",")).join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const anchor = document.createElement("a");
  anchor.href = csvDataHref(csv);
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function csvDataHref(csv: string): string {
  return `data:text/csv;charset=utf-8,%EF%BB%BF${encodeURIComponent(csv)}`;
}

export function nearestTableCsv(source: HTMLElement): { count: number; csv: string } {
  const scope = source.closest(".page-shell-center") ?? source.closest(".page-shell-card") ?? document;
  const table = scope.querySelector("table");
  if (!table) return { count: 0, csv: "" };
  const columns = Array.from(table.querySelectorAll("thead th"))
    .map((cell, index) => ({ index, header: cell.textContent?.trim() || "" }))
    .filter((column) => column.header && column.header !== "프로세스");
  const headers = columns.map((column) => column.header);
  const body = Array.from(table.querySelectorAll("tbody tr"))
    .filter((tr) => !tr.querySelector(".table-state-row"))
    .map((tr) =>
      columns.map(({ index }) => {
        const cell = tr.querySelectorAll("td")[index];
        return cell?.textContent?.replace(/\s+/g, " ").trim() || "";
      }),
    );
  return { count: body.length, csv: stringifyCsv(headers, body) };
}

export function exportNearestTable(source: HTMLElement, filename: string): number {
  const exported = nearestTableCsv(source);
  if (exported.count > 0) downloadCsv(filename, exported.csv);
  return exported.count;
}
