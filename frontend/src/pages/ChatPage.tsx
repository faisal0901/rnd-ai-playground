import { Copy, MessageSquare, PanelLeft, RefreshCw, Share2, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Composer } from "../components/Composer";
import { Markdown, copyText } from "../components/Markdown";
import { ToolCard } from "../components/ToolCard";
import { getHealth } from "../lib/api";
import type { ChatItem, Conversation } from "../lib/types";
import { react, regenerate, sendMessage, stop, useStore } from "../state/store";
import type { ShellContext } from "../App";

const SUGGESTIONS = [
  "Hitung jumlah 1 sampai 100 pakai python",
  "Cari di file saya: kopi saya terasa pahit",
  "Jelaskan perbedaan HTTP polling dan WebSocket, singkat saja.",
];

function transcriptText(conversation: Conversation): string {
  return conversation.items
    .flatMap((item) => (item.kind === "user" ? [`Kamu: ${item.text}`] : item.kind === "assistant" ? [`Nara: ${item.text}`] : []))
    .join("\n\n");
}

function AssistantAvatar() {
  return (
    <span className="bot" aria-hidden>
      <MessageSquare size={12} fill="currentColor" />
    </span>
  );
}

function AssistantActions({
  conversationId,
  item,
  canRegenerate,
  notify,
}: {
  conversationId: string;
  item: Extract<ChatItem, { kind: "assistant" }>;
  canRegenerate: boolean;
  notify: (message: string) => void;
}) {
  return (
    <div className="actions">
      <button
        type="button"
        className="icon-btn"
        aria-label="Salin jawaban"
        onClick={async () => notify((await copyText(item.text)) ? "Jawaban disalin" : "Tidak bisa menyalin")}
      >
        <Copy size={14} />
      </button>
      {canRegenerate && (
        <button type="button" className="icon-btn" aria-label="Buat ulang jawaban" onClick={() => regenerate(conversationId)}>
          <RefreshCw size={14} />
        </button>
      )}
      <button
        type="button"
        className={`icon-btn${item.reaction === "up" ? " on" : ""}`}
        aria-label="Jawaban bagus"
        aria-pressed={item.reaction === "up"}
        onClick={() => react(conversationId, item.id, item.reaction === "up" ? undefined : "up")}
      >
        <ThumbsUp size={14} />
      </button>
      <button
        type="button"
        className={`icon-btn${item.reaction === "down" ? " on" : ""}`}
        aria-label="Jawaban kurang bagus"
        aria-pressed={item.reaction === "down"}
        onClick={() => react(conversationId, item.id, item.reaction === "down" ? undefined : "down")}
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}

export default function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { conversations, busy } = useStore();
  const { sidebarOpen, toggleSidebar } = useOutletContext<ShellContext>();
  const conversation = conversations.find((c) => c.id === id);
  const working = conversation ? !!busy[conversation.id] : false;

  const [mode, setMode] = useState<"demo" | "model" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true); // stay at the bottom while a reply is written, unless the reader scrolled up

  useEffect(() => {
    getHealth()
      .then((h) => setMode(h.mode))
      .catch(() => setMode(null));
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useLayoutEffect(() => {
    pinned.current = true;
  }, [id]);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [conversation?.items, id]);

  if (id && !conversation) return <Navigate to="/" replace />;

  const items = conversation?.items ?? [];
  const last = items[items.length - 1];
  const lastAssistant = items.map((i) => i.kind).lastIndexOf("assistant");
  const waiting = working && (last?.kind === "user" || (last?.kind === "tool" && !!last.result));

  const send = (text: string, attachments: Parameters<typeof sendMessage>[2]) => {
    pinned.current = true;
    const next = sendMessage(id ?? null, text, attachments);
    if (!id) navigate(`/chat/${next}`);
  };

  const share = async () => {
    if (!conversation) return;
    setNotice((await copyText(transcriptText(conversation))) ? "Percakapan disalin ke clipboard" : "Tidak bisa menyalin");
  };

  return (
    <div className="page chat-page">
      <header className="topbar">
        {!sidebarOpen && (
          <button type="button" className="icon-btn" aria-label="Tampilkan sidebar" onClick={toggleSidebar}>
            <PanelLeft size={16} />
          </button>
        )}
        <strong className="model">Nara Pintar</strong>
        {mode === "demo" && <span className="badge" title="Belum ada ANTHROPIC_API_KEY: jawaban berasal dari model palsu">mode demo</span>}
        {conversation && (
          <>
            <span className="crumb-sep">/</span>
            <span className="crumb">{conversation.title}</span>
          </>
        )}
        <span className="spacer" />
        {conversation && (
          <button type="button" className="btn btn-ghost" onClick={share}>
            <Share2 size={14} /> Bagikan
          </button>
        )}
      </header>

      <div
        className="scroller"
        ref={scroller}
        onScroll={(event) => {
          const el = event.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {conversation ? (
          <div className="thread" role="log" aria-live="polite">
            {items.map((item, index) => {
              switch (item.kind) {
                case "user":
                  return (
                    <div className="row-user" key={item.id}>
                      <div className="bubble-user">{item.text}</div>
                      {item.attachments.length > 0 && <small className="attached">Lampiran: {item.attachments.join(", ")}</small>}
                    </div>
                  );
                case "assistant":
                  return (
                    <div className="row-bot" key={item.id}>
                      <AssistantAvatar />
                      <div className="bot-body">
                        <Markdown text={item.text} />
                        {!(working && index === items.length - 1) && (
                          <AssistantActions
                            conversationId={conversation.id}
                            item={item}
                            canRegenerate={index === lastAssistant && !working}
                            notify={setNotice}
                          />
                        )}
                      </div>
                    </div>
                  );
                case "tool":
                  return (
                    <div className="row-bot" key={item.id}>
                      <span className="bot-gap" />
                      <div className="bot-body">
                        <ToolCard name={item.name} input={item.input} result={item.result} />
                      </div>
                    </div>
                  );
                case "error":
                  return (
                    <div className="row-bot" key={item.id}>
                      <span className="bot-gap" />
                      <div className="bot-body">
                        <div className="error-box" role="alert">
                          {item.message}
                        </div>
                      </div>
                    </div>
                  );
              }
            })}
            {waiting && (
              <div className="row-bot">
                <AssistantAvatar />
                <div className="bot-body">
                  <span className="typing" aria-label="Nara sedang menulis">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-chat">
            <span className="logo-mark big">
              <MessageSquare size={22} fill="currentColor" />
            </span>
            <h1>Mau bahas apa hari ini?</h1>
            <p>Tanya apa saja, minta Nara menghitung dengan Python, atau cari jawaban di file yang kamu unggah.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button type="button" key={text} className="suggestion" onClick={() => send(text, [])}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {notice && (
        <div className="toast" role="status">
          {notice}
        </div>
      )}
      <Composer
        resetKey={id ?? "new"}
        busy={working}
        onSend={send}
        onStop={() => conversation && stop(conversation.id)}
        onError={setNotice}
      />
    </div>
  );
}
