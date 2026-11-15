import { ChevronRight, Database, Terminal } from "lucide-react";
import type { ToolResult } from "../lib/types";

const LABELS: Record<string, string> = { run_python: "Menjalankan kode Python", search_docs: "Mencari di file kamu" };

function outcome(result: ToolResult): { label: string; ok: boolean; body: string } {
  const hits = result.results;
  const label = result.error ? "error" : hits ? `${hits.length} hasil` : result.timed_out ? "timeout" : `exit ${result.exit_code}`;
  const body =
    result.error ||
    (hits
      ? hits.map((h) => `${h.score.toFixed(3)}  ${h.source} #${h.chunk}\n${h.text}`).join("\n\n")
      : [result.stdout, result.stderr].filter(Boolean).join("\n"));
  return { label, ok: result.ok, body };
}

export function ToolCard({ name, input, result }: { name: string; input: string; result?: ToolResult }) {
  const done = result ? outcome(result) : null;
  const Icon = name === "search_docs" ? Database : Terminal;
  return (
    <details className="tool" open>
      <summary>
        <ChevronRight size={14} className="chevron" />
        <Icon size={14} />
        <span>{LABELS[name] ?? name}</span>
        <span className={`tool-status${done ? (done.ok ? " ok" : " bad") : ""}`}>{done ? done.label : "berjalan…"}</span>
      </summary>
      <pre>{input}</pre>
      {done?.body && <pre className="tool-out">{done.body}</pre>}
    </details>
  );
}
