import { AlertCircle, Check, FileText, Loader2, PanelLeft, Search, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useOutletContext } from "react-router-dom";
import { Menu } from "../components/Menu";
import { deleteDocument, listDocuments, uploadDocument } from "../lib/api";
import { ACCEPT, ACCEPT_LABEL, extensionOf, formatDate, formatSize, groupOf, makeId, type FileGroup } from "../lib/format";
import type { KbDocument, KbListing } from "../lib/types";
import type { ShellContext } from "../App";

/** A file the browser is sending (or failed to send). Finished uploads disappear from here and show up in the list. */
interface Job {
  id: string;
  file: File;
  state: "uploading" | "processing" | "failed";
  sent: number; // 0..1 of the bytes sent
  error?: string;
}

const FILTERS: { key: "all" | FileGroup; label: string }[] = [
  { key: "all", label: "Semua" },
  { key: "pdf", label: "PDF" },
  { key: "text", label: "Teks" },
  { key: "data", label: "Data (CSV, JSON)" },
];

function TypeBadge({ name }: { name: string }) {
  const ext = extensionOf(name);
  return <span className={`type-badge t-${groupOf(name)}`}>{ext.slice(0, 4).toUpperCase() || <FileText size={14} />}</span>;
}

function StatusPill({ kind, children }: { kind: "ok" | "wait" | "bad"; children: React.ReactNode }) {
  return <span className={`pill pill-${kind}`}>{children}</span>;
}

export default function FilesPage() {
  const { sidebarOpen, toggleSidebar } = useOutletContext<ShellContext>();
  const [listing, setListing] = useState<KbListing | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [filter, setFilter] = useState<"all" | FileGroup>("all");
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    listDocuments()
      .then((data) => {
        setListing(data);
        setLoadError(null);
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  useEffect(refresh, [refresh]);

  // ---- uploading: one file at a time, because each is embedded before the next one starts --------------------------
  const queue = useRef<Promise<void>>(Promise.resolve());
  const patchJob = (id: string, change: Partial<Job>) =>
    setJobs((list) => list.map((j) => (j.id === id ? { ...j, ...change } : j)));

  const start = (job: Job) => {
    queue.current = queue.current.then(async () => {
      patchJob(job.id, { state: "uploading", sent: 0, error: undefined });
      try {
        await uploadDocument(
          job.file,
          (sent) => patchJob(job.id, { sent }),
          () => patchJob(job.id, { state: "processing", sent: 1 }),
        );
        setJobs((list) => list.filter((j) => j.id !== job.id));
      } catch (error) {
        patchJob(job.id, { state: "failed", error: (error as Error).message });
      }
      refresh();
    });
  };

  const add = (files: File[]) => {
    const fresh = files.map<Job>((file) => ({ id: makeId(), file, state: "uploading", sent: 0 }));
    if (!fresh.length) return;
    setJobs((list) => [...fresh, ...list]);
    fresh.forEach(start);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    add([...event.dataTransfer.files]);
  };

  const remove = async (doc: KbDocument) => {
    if (!window.confirm(`Hapus "${doc.name}" dari File saya? Nara tidak bisa lagi mencari jawaban di file ini.`)) return;
    try {
      await deleteDocument(doc.name);
      setMessage(`"${doc.name}" dihapus`);
    } catch (error) {
      setMessage((error as Error).message);
    }
    refresh();
  };

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), 3000);
    return () => window.clearTimeout(timer);
  }, [message]);

  // ---- what the table shows ----------------------------------------------------------------------------------------
  const documents = listing?.documents ?? [];
  const needle = query.trim().toLowerCase();
  const matches = (name: string) => (filter === "all" || groupOf(name) === filter) && name.toLowerCase().includes(needle);
  const shownJobs = useMemo(() => jobs.filter((j) => matches(j.file.name)), [jobs, filter, needle]); // eslint-disable-line react-hooks/exhaustive-deps
  const shownDocs = documents.filter((d) => matches(d.name));
  const total = documents.length + jobs.length;
  const countOf = (key: "all" | FileGroup) =>
    key === "all" ? total : documents.filter((d) => groupOf(d.name) === key).length + jobs.filter((j) => groupOf(j.file.name) === key).length;

  return (
    <div className="page files-page">
      <header className="topbar plain">
        {!sidebarOpen && (
          <button type="button" className="icon-btn" aria-label="Tampilkan sidebar" onClick={toggleSidebar}>
            <PanelLeft size={16} />
          </button>
        )}
        <span className="spacer" />
      </header>

      <div className="scroller">
        <div className="files">
          <div className="files-head">
            <div>
              <h1>File saya</h1>
              <p className="lead">
                Dokumen yang kamu unggah menjadi basis pengetahuan Nara. Saat kamu bertanya, Nara mencari jawabannya di file-file ini.
              </p>
            </div>
            <button type="button" className="btn btn-primary" onClick={() => picker.current?.click()}>
              <Upload size={14} /> Unggah file
            </button>
          </div>

          <input
            ref={picker}
            type="file"
            multiple
            hidden
            accept={ACCEPT}
            onChange={(event) => {
              add([...(event.target.files ?? [])]);
              event.target.value = "";
            }}
          />

          <div
            className={`dropzone${dragging ? " over" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
            }}
            onDrop={onDrop}
          >
            <span className="drop-icon">
              <Upload size={16} />
            </span>
            <strong>Tarik dan lepas file ke sini</strong>
            <span>
              atau{" "}
              <button type="button" className="link" onClick={() => picker.current?.click()}>
                pilih dari komputer
              </button>
            </span>
            <small>
              {ACCEPT_LABEL} · Maks. {listing?.max_upload_mb ?? 10} MB per file
            </small>
          </div>

          <div className="toolbar">
            <label className="search wide">
              <Search size={14} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari nama file" aria-label="Cari nama file" />
            </label>
            <div className="filters" role="group" aria-label="Filter jenis file">
              {FILTERS.map((f) => (
                <button
                  type="button"
                  key={f.key}
                  className={`filter${filter === f.key ? " active" : ""}`}
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                  {f.key === "all" && ` · ${countOf("all")}`}
                </button>
              ))}
            </div>
          </div>

          {loadError && (
            <div className="error-box" role="alert">
              Gagal memuat daftar file: {loadError}{" "}
              <button type="button" className="link" onClick={refresh}>
                Coba lagi
              </button>
            </div>
          )}

          <div className="table" role="table" aria-label="Daftar file">
            <div className="tr th" role="row">
              <span role="columnheader">Nama</span>
              <span role="columnheader">Jenis</span>
              <span role="columnheader">Diunggah</span>
              <span role="columnheader">Status</span>
              <span />
            </div>

            {shownJobs.map((job) => (
              <div className="tr" role="row" key={job.id}>
                <div className="name-cell" role="cell">
                  <TypeBadge name={job.file.name} />
                  <div>
                    <strong title={job.file.name}>{job.file.name}</strong>
                    <small className={job.state === "failed" ? "bad-text" : ""}>
                      {job.state === "failed" ? job.error : formatSize(job.file.size)}
                    </small>
                  </div>
                </div>
                <span role="cell" className="muted">{extensionOf(job.file.name).toUpperCase()}</span>
                <span role="cell" className="muted">Hari ini</span>
                <span role="cell">
                  {job.state === "failed" ? (
                    <>
                      <StatusPill kind="bad">
                        <AlertCircle size={12} /> Gagal
                      </StatusPill>{" "}
                      <button type="button" className="link" onClick={() => start(job)}>
                        Coba lagi
                      </button>
                    </>
                  ) : job.state === "uploading" ? (
                    <StatusPill kind="wait">
                      <Loader2 size={12} className="spin" /> Mengunggah {Math.round(job.sent * 100)}%
                    </StatusPill>
                  ) : (
                    <StatusPill kind="wait">
                      <Loader2 size={12} className="spin" /> Memproses
                    </StatusPill>
                  )}
                </span>
                <span role="cell">
                  {job.state === "failed" && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Buang ${job.file.name}`}
                      onClick={() => setJobs((list) => list.filter((j) => j.id !== job.id))}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </span>
              </div>
            ))}

            {shownDocs.map((doc) => (
              <div className="tr" role="row" key={`${doc.kind}-${doc.name}`}>
                <div className="name-cell" role="cell">
                  <TypeBadge name={doc.name} />
                  <div>
                    <strong title={doc.name}>
                      {doc.name}
                      {doc.kind === "sample" && <span className="tag">contoh</span>}
                    </strong>
                    <small>
                      {formatSize(doc.bytes)} · {doc.chunks} potongan
                    </small>
                  </div>
                </div>
                <span role="cell" className="muted">{extensionOf(doc.name).toUpperCase()}</span>
                <span role="cell" className="muted">{formatDate(doc.modified)}</span>
                <span role="cell">
                  {doc.chunks > 0 ? (
                    <StatusPill kind="ok">
                      <Check size={12} /> Siap dipakai
                    </StatusPill>
                  ) : (
                    <StatusPill kind="wait">Belum diindeks</StatusPill>
                  )}
                </span>
                <span role="cell">
                  {doc.kind === "upload" ? (
                    <Menu label={`Opsi untuk ${doc.name}`}>
                      {(close) => (
                        <button
                          type="button"
                          className="menu-item danger"
                          onClick={() => {
                            close();
                            void remove(doc);
                          }}
                        >
                          <Trash2 size={14} /> Hapus
                        </button>
                      )}
                    </Menu>
                  ) : null}
                </span>
              </div>
            ))}

            {!shownJobs.length && !shownDocs.length && (
              <p className="table-empty">
                {!listing && !loadError
                  ? "Memuat…"
                  : total
                    ? "Tidak ada file yang cocok."
                    : "Belum ada file. Unggah satu supaya Nara bisa mencari jawabannya di sana."}
              </p>
            )}
          </div>

          {listing && (
            <p className="foot-note">
              Embedding: {listing.embedder.startsWith("demo") ? "demo (hanya kata, tanpa Voyage)" : listing.embedder}
            </p>
          )}
        </div>
      </div>

      {message && (
        <div className="toast" role="status">
          {message}
        </div>
      )}
    </div>
  );
}
