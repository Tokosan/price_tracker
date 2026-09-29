import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api.js";
import Admin from "./pages/Admin.jsx";
import AddWatch from "./pages/AddWatch.jsx";
import Invite from "./pages/Invite.jsx";
import Login from "./pages/Login.jsx";
import Notifications from "./pages/Notifications.jsx";
import Settings from "./pages/Settings.jsx";
import Sites from "./pages/Sites.jsx";
import WatchDetail from "./pages/WatchDetail.jsx";
import Watches from "./pages/Watches.jsx";

const MeContext = createContext(null);
export const useMe = () => useContext(MeContext);

export default function App() {
  const [me, setMe] = useState(undefined); // undefined = cargando, null = sin sesión
  const reload = useCallback(async () => {
    try {
      setMe(await api("/api/auth/me"));
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
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    await reload();
    navigate("/login");
  };
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width="22" height="22" /> Tracker
        </NavLink>
        <nav>
          <NavLink to="/" end>Productos</NavLink>
          <NavLink to="/agregar">Agregar</NavLink>
          <NavLink to="/notificaciones">Avisos</NavLink>
          <NavLink to="/sitios">Sitios</NavLink>
          <NavLink to="/ajustes">Ajustes</NavLink>
          {me.role === "admin" && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <button className="link" onClick={logout} title={`Sesión de ${me.username}`}>
          Salir
        </button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Watches />} />
          <Route path="/agregar" element={<AddWatch />} />
          <Route path="/w/:id" element={<WatchDetail />} />
          <Route path="/notificaciones" element={<Notifications />} />
          <Route path="/sitios" element={<Sites />} />
          <Route path="/ajustes" element={<Settings />} />
          {me.role === "admin" && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </>
  );
}
