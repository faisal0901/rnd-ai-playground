// Shapes shared by the API client, the conversation store and the components.

export interface ToolResult {
  ok: boolean;
  error?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  timed_out?: boolean;
  results?: { score: number; source: string; chunk: number; text: string }[];
}

export type Reaction = "up" | "down";

export type ChatItem =
  | { id: string; kind: "user"; text: string; content: string; attachments: string[] }
  | { id: string; kind: "assistant"; text: string; reaction?: Reaction }
  | { id: string; kind: "tool"; name: string; input: string; result?: ToolResult }
  | { id: string; kind: "error"; message: string };

/** A message in the format the server wants back on every request (the server remembers nothing). */
export interface ModelMessage {
  role: string;
  content: unknown;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  items: ChatItem[];
  /** The transcript the server returned when the last turn finished. */
  transcript: ModelMessage[];
}

export interface Attachment {
  name: string;
  text: string;
  chars: number;
  truncated: boolean;
}

/** One line of the server's event stream (see app/agent.py). */
export type ServerEvent =
  | { kind: "text"; text: string }
  | { kind: "tool_call"; name: string; input: Record<string, unknown> }
  | { kind: "tool_result"; name: string; result: ToolResult }
  | { kind: "done"; messages: ModelMessage[] }
  | { kind: "error"; message: string };

export interface KbDocument {
  name: string;
  kind: "upload" | "sample";
  chunks: number;
  bytes: number;
  /** Seconds since the epoch. */
  modified: number;
}

export interface KbListing {
  embedder: string;
  reranker: boolean;
  max_upload_mb: number;
  documents: KbDocument[];
}
