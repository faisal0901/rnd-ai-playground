import type { Attachment, KbListing, ModelMessage, ServerEvent } from "./types";

export class ApiError extends Error {}

/** The server reports problems as {"detail": "..."}; turn any failed response into an Error with that text. */
async function parse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
  }
  return data as T;
}

export const getHealth = () => fetch("/api/health").then((r) => parse<{ mode: "demo" | "model" }>(r));

export const listDocuments = () => fetch("/api/kb").then((r) => parse<KbListing>(r));

export const deleteDocument = (name: string) =>
  fetch(`/api/kb/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => parse<unknown>(r));

/** A chat attachment: the server reads the file and hands the text back. Nothing is stored or embedded. */
export function attachFile(file: File): Promise<Attachment> {
  const body = new FormData();
  body.append("file", file);
  return fetch("/api/attach", { method: "POST", body }).then((r) => parse<Attachment>(r));
}

/**
 * Upload a file into the knowledge base (it is saved, split and embedded before the request returns).
 * XHR rather than fetch, because only XHR reports how much of the upload has been sent.
 */
export function uploadDocument(
  file: File,
  onProgress: (sent: number) => void,
  onSent: () => void,
): Promise<{ name: string; chunks: number; status: "indexed" | "unchanged" }> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/kb");
    request.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    request.upload.onload = onSent;
    request.onerror = () => reject(new ApiError("Tidak bisa menghubungi server."));
    request.onload = () => {
      let data: { detail?: unknown } = {};
      try {
        data = JSON.parse(request.responseText);
      } catch {
        /* not JSON: fall through to the status text */
      }
      if (request.status >= 200 && request.status < 300) resolve(data as never);
      else reject(new ApiError(typeof data.detail === "string" ? data.detail : `${request.status} ${request.statusText}`));
    };
    const body = new FormData();
    body.append("file", file);
    request.send(body);
  });
}

/** POST the conversation and call `onEvent` for every server-sent event as it arrives. */
export async function streamChat(messages: ModelMessage[], signal: AbortSignal, onEvent: (event: ServerEvent) => void) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!response.ok || !response.body) throw new ApiError(`${response.status} ${response.statusText}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      // one complete event: a "data: {json}" line
      const line = buffer.slice(0, end).replace(/^data: /, "");
      buffer = buffer.slice(end + 2);
      if (line) onEvent(JSON.parse(line) as ServerEvent);
    }
  }
}
