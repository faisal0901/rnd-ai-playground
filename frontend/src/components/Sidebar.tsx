import { FolderOpen, MessageSquare, PanelLeft, Plus, Search, Settings, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { NavLink, useMatch, useNavigate } from "react-router-dom";
import { PROFILE } from "../lib/profile";
import type { Conversation } from "../lib/types";
import { deleteConversation, useStore } from "../state/store";
import { Menu } from "./Menu";

const DAY = 24 * 60 * 60 * 1000;

function groupConversations(conversations: Conversation[]) {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups: { label: string; items: Conversation[] }[] = [
    { label: "Hari ini", items: [] },
    { label: "7 hari terakhir", items: [] },
    { label: "Lebih lama", items: [] },
  ];
  for (const c of conversations) {
    if (c.updatedAt >= startOfToday) groups[0].items.push(c);
    else if (c.updatedAt >= startOfToday - 6 * DAY) groups[1].items.push(c);
    else groups[2].items.push(c);
  }
  return groups.filter((g) => g.items.length);
}

export function Sidebar({ onToggle, onNavigate }: { onToggle: () => void; onNavigate: () => void }) {
  const { conversations } = useStore();
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const activeId = useMatch("/chat/:id")?.params.id;

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const found = needle ? conversations.filter((c) => c.title.toLowerCase().includes(needle)) : conversations;
    return groupConversations(found);
  }, [conversations, query]);

  const remove = (id: string) => {
    if (!window.confirm("Hapus percakapan ini?")) return;
    deleteConversation(id);
    if (id === activeId) navigate("/");
  };

  return (
    <aside className="sidebar" aria-label="Navigasi">
      <div className="sidebar-head">
        <div className="logo">
          <span className="logo-mark">
            <MessageSquare size={14} fill="currentColor" />
          </span>
          Nara
        </div>
        <button type="button" className="icon-btn" aria-label="Sembunyikan sidebar" onClick={onToggle}>
          <PanelLeft size={16} />
        </button>
      </div>

      <button
        type="button"
        className="btn btn-primary new-chat"
        onClick={() => {
          navigate("/");
          onNavigate();
        }}
      >
        <Plus size={16} /> Chat baru
      </button>

      <NavLink to="/files" className={({ isActive }) => `nav-item${isActive ? " active" : ""}`} onClick={onNavigate}>
        <FolderOpen size={16} /> File saya
      </NavLink>

      <label className="search">
        <Search size={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Cari percakapan"
          aria-label="Cari percakapan"
        />
      </label>

      <nav className="history">
        {groups.map((group) => (
          <section key={group.label}>
            <h2>{group.label}</h2>
            {group.items.map((c) => (
              <div key={c.id} className={`history-row${c.id === activeId ? " active" : ""}`}>
                <NavLink to={`/chat/${c.id}`} className="history-link" onClick={onNavigate} title={c.title}>
                  {c.title}
                </NavLink>
                <Menu label={`Opsi untuk ${c.title}`}>
                  {(close) => (
                    <button
                      type="button"
                      className="menu-item danger"
                      onClick={() => {
                        close();
                        remove(c.id);
                      }}
                    >
                      <Trash2 size={14} /> Hapus
                    </button>
                  )}
                </Menu>
              </div>
            ))}
          </section>
        ))}
        {!groups.length && <p className="history-empty">{query ? "Tidak ada yang cocok." : "Belum ada percakapan."}</p>}
      </nav>

      <div className="profile">
        <span className="avatar" aria-hidden>
          {PROFILE.name[0]}
        </span>
        <span className="profile-text">
          <strong>{PROFILE.name}</strong>
          <small>{PROFILE.plan}</small>
        </span>
        <Settings size={16} className="muted" aria-hidden />
      </div>
    </aside>
  );
}
