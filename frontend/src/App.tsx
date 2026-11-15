import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const FilesPage = lazy(() => import("./pages/FilesPage"));

export interface ShellContext {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

const NARROW = "(max-width: 860px)";

function Shell() {
  const [sidebarOpen, setSidebarOpen] = useState(() => !window.matchMedia(NARROW).matches);
  const location = useLocation();

  // On a narrow screen the sidebar is a drawer: close it after moving to another page.
  useEffect(() => {
    if (window.matchMedia(NARROW).matches) setSidebarOpen(false);
  }, [location.pathname]);

  const context: ShellContext = { sidebarOpen, toggleSidebar: () => setSidebarOpen((open) => !open) };

  return (
    <div className={`shell${sidebarOpen ? "" : " collapsed"}`}>
      <Sidebar onToggle={context.toggleSidebar} onNavigate={() => window.matchMedia(NARROW).matches && setSidebarOpen(false)} />
      <button type="button" className="scrim" aria-label="Tutup sidebar" onClick={context.toggleSidebar} />
      <main className="main">
        <Suspense fallback={null}>
          <Outlet context={context} />
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<ChatPage />} />
        <Route path="chat/:id" element={<ChatPage />} />
        <Route path="files" element={<FilesPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
