// The conversation store. The server keeps nothing between requests, so the browser keeps the conversations
// (in localStorage) and sends the whole transcript every turn. A module-level store, not React state, so a reply
// keeps streaming while you look at another page.

import { useSyncExternalStore } from "react";
import { streamChat } from "../lib/api";
import { makeId } from "../lib/format";
import type { Attachment, ChatItem, Conversation, ModelMessage, Reaction, ServerEvent } from "../lib/types";

const STORAGE_KEY = "nara.conversations.v1";

interface State {
  conversations: Conversation[]; // newest first
  busy: Record<string, true>; // conversation ids that are waiting for a reply
}

function load(): Conversation[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

let state: State = { conversations: load(), busy: {} };
const listeners = new Set<() => void>();
const controllers = new Map<string, AbortController>();

let saveTimer: number | undefined;
function save() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.conversations));
    } catch {
      /* storage full or blocked: the chat still works, it just will not survive a reload */
    }
  }, 300);
}

function set(next: State) {
  state = next;
  listeners.forEach((notify) => notify());
  save();
}

function patch(id: string, change: (conversation: Conversation) => Conversation) {
  set({ ...state, conversations: state.conversations.map((c) => (c.id === id ? change(c) : c)) });
}

function setBusy(id: string, busy: boolean) {
  const next = { ...state.busy };
  if (busy) next[id] = true;
  else delete next[id];
  set({ ...state, busy: next });
}

export function useStore(): State {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
  );
}

// ---- applying one server event to a conversation ---------------------------------------------------------------------
function applyEvent(id: string, event: ServerEvent) {
  patch(id, (c) => {
    const items = [...c.items];
    const last = items[items.length - 1];
    switch (event.kind) {
      case "text":
        if (last?.kind === "assistant") items[items.length - 1] = { ...last, text: last.text + event.text };
        else items.push({ id: makeId(), kind: "assistant", text: event.text });
        return { ...c, items };
      case "tool_call": {
        const input = event.input.code ?? event.input.query ?? JSON.stringify(event.input, null, 2);
        items.push({ id: makeId(), kind: "tool", name: event.name, input: String(input) });
        return { ...c, items };
      }
      case "tool_result": {
        for (let i = items.length - 1; i >= 0; i--) {
          const item = items[i];
          if (item.kind === "tool" && !item.result && item.name === event.name) {
            items[i] = { ...item, result: event.result };
            break;
          }
        }
        return { ...c, items };
      }
      case "done":
        return { ...c, transcript: event.messages, updatedAt: Date.now() };
      case "error":
        items.push({ id: makeId(), kind: "error", message: event.message });
        return { ...c, items };
    }
  });
}

async function run(id: string, transcript: ModelMessage[]) {
  const controller = new AbortController();
  controllers.set(id, controller);
  setBusy(id, true);
  try {
    await streamChat(transcript, controller.signal, (event) => applyEvent(id, event));
  } catch (error) {
    if (!controller.signal.aborted) {
      applyEvent(id, { kind: "error", message: `Gagal menghubungi server: ${(error as Error).message}` });
    }
  } finally {
    controllers.delete(id);
    setBusy(id, false);
  }
}

// ---- actions ---------------------------------------------------------------------------------------------------------
const titleOf = (text: string) => (text.length > 40 ? `${text.slice(0, 40).trimEnd()}…` : text);

/** Send a message. With no id, a new conversation is started. Returns the conversation's id. */
export function sendMessage(id: string | null, text: string, attachments: Attachment[]): string {
  text = text.trim() || "Tolong baca lampiran ini.";
  // What the model receives: the text, then each file wrapped in a tag so it can tell them apart.
  const content = text + attachments.map((f) => `\n\n<attachment name="${f.name}">\n${f.text}\n</attachment>`).join("");
  const item: ChatItem = { id: makeId(), kind: "user", text, content, attachments: attachments.map((f) => f.name) };
  const now = Date.now();

  let existing = id ? state.conversations.find((c) => c.id === id) : undefined;
  if (!existing || state.busy[existing.id]) {
    if (existing) return existing.id; // one reply at a time per conversation
    existing = { id: makeId(), title: titleOf(text), createdAt: now, updatedAt: now, items: [], transcript: [] };
    set({ ...state, conversations: [existing, ...state.conversations] });
  }
  const conversation = existing;
  patch(conversation.id, (c) => ({ ...c, items: [...c.items, item], updatedAt: now }));
  void run(conversation.id, [...conversation.transcript, { role: "user", content }]);
  return conversation.id;
}

/** Ask again for the last answer: drop everything after the last question and send that question once more. */
export function regenerate(id: string) {
  const conversation = state.conversations.find((c) => c.id === id);
  if (!conversation || state.busy[id]) return;
  const at = conversation.items.map((i) => i.kind).lastIndexOf("user");
  const question = conversation.items[at];
  if (question?.kind !== "user") return;

  // If that turn finished, the saved transcript ends with it: cut it off. If it failed, it never got saved.
  let transcript = conversation.transcript;
  for (let i = transcript.length - 1; i >= 0; i--) {
    if (transcript[i].role === "user" && typeof transcript[i].content === "string") {
      if (transcript[i].content === question.content) transcript = transcript.slice(0, i);
      break;
    }
  }
  patch(id, (c) => ({ ...c, items: c.items.slice(0, at + 1), transcript }));
  void run(id, [...transcript, { role: "user", content: question.content }]);
}

export function stop(id: string) {
  controllers.get(id)?.abort();
}

export function deleteConversation(id: string) {
  stop(id);
  set({ ...state, conversations: state.conversations.filter((c) => c.id !== id) });
}

export function react(id: string, itemId: string, reaction: Reaction | undefined) {
  patch(id, (c) => ({
    ...c,
    items: c.items.map((i) => (i.id === itemId && i.kind === "assistant" ? { ...i, reaction } : i)),
  }));
}
