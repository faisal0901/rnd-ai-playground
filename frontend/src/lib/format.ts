export const ACCEPT = ".md,.txt,.csv,.json,.log,.pdf";
export const ACCEPT_LABEL = "PDF, Teks (TXT, MD, LOG), CSV, JSON";

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

const dateFormat = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" });
export const formatDate = (seconds: number) => dateFormat.format(new Date(seconds * 1000));

export const extensionOf = (name: string) => (name.includes(".") ? name.split(".").pop()!.toLowerCase() : "");

export type FileGroup = "pdf" | "text" | "data";

export function groupOf(name: string): FileGroup {
  const ext = extensionOf(name);
  if (ext === "pdf") return "pdf";
  if (ext === "csv" || ext === "json") return "data";
  return "text";
}

export function makeId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}
