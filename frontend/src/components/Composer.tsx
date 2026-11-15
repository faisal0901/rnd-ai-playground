import { ArrowUp, Paperclip, Square, X } from "lucide-react";
import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { attachFile } from "../lib/api";
import { ACCEPT } from "../lib/format";
import type { Attachment } from "../lib/types";

interface Props {
  busy: boolean;
  onSend: (text: string, attachments: Attachment[]) => void;
  onStop: () => void;
  onError: (message: string) => void;
  /** Changes when the visible conversation changes, so the box resets. */
  resetKey: string;
}

/**
 * The message box. A file attached here is only read by the server: its text rides along in this conversation and
 * nothing is stored. To keep a file and make it searchable, upload it on the "File saya" page.
 */
export function Composer({ busy, onSend, onStop, onError, resetKey }: Props) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [reading, setReading] = useState(0);
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [lastKey, setLastKey] = useState(resetKey);

  if (lastKey !== resetKey) {
    // reset while rendering: the documented way to change state when a prop changes
    setLastKey(resetKey);
    setText("");
    setAttachments([]);
  }

  const grow = () => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  const read = async (files: File[]) => {
    setReading((n) => n + files.length);
    for (const file of files) {
      try {
        const attachment = await attachFile(file);
        setAttachments((list) => [...list, attachment]);
      } catch (error) {
        onError(`${file.name}: ${(error as Error).message}`);
      } finally {
        setReading((n) => n - 1);
      }
    }
  };

  const canSend = !busy && reading === 0 && (text.trim() !== "" || attachments.length > 0);
  const submit = () => {
    if (!canSend) return;
    onSend(text, attachments);
    setText("");
    setAttachments([]);
    requestAnimationFrame(grow);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };
  const onPaste = (event: ClipboardEvent) => {
    const files = [...event.clipboardData.files];
    if (files.length) {
      event.preventDefault();
      void read(files);
    }
  };

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        {(attachments.length > 0 || reading > 0) && (
          <div className="chips">
            {attachments.map((file, index) => (
              <span className="chip" key={`${file.name}-${index}`}>
                {file.name} · {file.chars.toLocaleString("id-ID")} karakter{file.truncated ? " (dipotong)" : ""}
                <button
                  type="button"
                  aria-label={`Buang ${file.name}`}
                  onClick={() => setAttachments((l) => l.filter((_, i) => i !== index))}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
            {reading > 0 && <span className="chip muted-chip">membaca file…</span>}
          </div>
        )}
        <textarea
          ref={field}
          rows={1}
          value={text}
          placeholder="Tulis pesan untuk Nara..."
          aria-label="Pesan"
          autoFocus
          onChange={(event) => {
            setText(event.target.value);
            grow();
          }}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
        <div className="composer-bar">
          <input
            ref={picker}
            type="file"
            multiple
            hidden
            accept={ACCEPT}
            onChange={(event) => {
              void read([...(event.target.files ?? [])]);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className="icon-btn"
            aria-label="Lampirkan file"
            title="Lampirkan file untuk percakapan ini saja. Tidak disimpan dan tidak masuk File saya."
            onClick={() => picker.current?.click()}
          >
            <Paperclip size={16} />
          </button>
          {busy ? (
            <button type="button" className="send" aria-label="Hentikan" onClick={onStop}>
              <Square size={12} fill="currentColor" />
            </button>
          ) : (
            <button type="submit" className="send" aria-label="Kirim" disabled={!canSend}>
              <ArrowUp size={16} />
            </button>
          )}
        </div>
      </form>
      <p className="disclaimer">Nara bisa keliru. Periksa kembali informasi yang penting.</p>
    </div>
  );
}
