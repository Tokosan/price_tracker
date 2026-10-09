import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import { applyTheme, effectiveMode, saveTheme } from "./theme.js";
import Admin from "./pages/admin/Admin.jsx";
import AddWatch from "./pages/AddWatch.jsx";
import Invite from "./pages/Invite.jsx";
import Login from "./pages/Login.jsx";
import Notifications from "./pages/Notifications.jsx";
import Settings from "./pages/Settings.jsx";
import Stores from "./pages/Stores.jsx";
import WatchDetail from "./pages/WatchDetail.jsx";
import Watches from "./pages/Watches.jsx";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState(undefined); // undefined = cargando, null = sin sesión
  const reload = useCallback(async () => {
    try {
      const data = await api("/api/auth/me");
      applyTheme(data.preferences);
      setMe(data);
    } catch {
      setMe(null);
    }
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  if (me === undefined) return <div className="center muted">Cargando…</div>;

  return (
    <MeContext.Provider value={{ me, reload }}>
      <Routes>
        <Route path="/invite/:token" element={<Invite />} />
        <Route path="/login" element={me ? <Navigate to="/" /> : <Login />} />
        <Route path="/*" element={me ? <Shell /> : <Navigate to="/login" />} />
      </Routes>
    </MeContext.Provider>
  );
}

function Shell() {
  const { me, reload } = useMe();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // Admin y Productos (con su sidebar de filtros) usan todo el ancho.
  const wide = pathname.startsWith("/admin") || pathname === "/";
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    await reload();
    navigate("/login");
  };
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          <svg className="brand-logo" viewBox="0 0 32 32" width="24" height="24" aria-hidden="true">
            <rect width="32" height="32" rx="8" />
            <path d="M7 21l6-6 5 5 7-8" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Tracker
        </NavLink>
        <nav>
          <NavLink to="/" end>Productos</NavLink>
          <NavLink to="/agregar">Agregar</NavLink>
          <NavLink to="/notificaciones">Avisos</NavLink>
          <NavLink to="/tiendas">Tiendas</NavLink>
          <NavLink to="/ajustes">Ajustes</NavLink>
          {me.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="topbar-actions">
          <ThemeToggle />
          <button className="link" onClick={logout} title={`Sesión de ${me.username}`}>
            Salir
          </button>
        </div>
      </header>
      <main className={wide ? "wide" : undefined}>
        <Routes>
          <Route path="/" element={<Watches />} />
          <Route path="/agregar" element={<AddWatch />} />
          <Route path="/w/:id" element={<WatchDetail />} />
          <Route path="/notificaciones" element={<Notifications />} />
          <Route path="/tiendas" element={<Stores />} />
          <Route path="/sitios" element={<Navigate to="/tiendas" replace />} />
          <Route path="/ajustes" element={<Settings />} />
          {me.role === "admin" && <Route path="/admin/*" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </>
  );
}

// Alterna claro/oscuro (deja de seguir al sistema). La paleta se elige en Ajustes.
function ThemeToggle() {
  const { reload } = useMe();
  const dark = effectiveMode() === "dark";
  const toggle = () => saveTheme({ theme: dark ? "light" : "dark" }).then(reload).catch(() => {});
  return (
    <button className="icon-button" onClick={toggle} title={dark ? "Usar tema claro" : "Usar tema oscuro"} aria-label="Cambiar tema">
      {dark ? (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
