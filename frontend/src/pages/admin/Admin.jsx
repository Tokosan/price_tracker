import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Products from "./Products.jsx";
import Stores from "./Stores.jsx";
import Summary from "./Summary.jsx";
import Users from "./Users.jsx";

const SECTIONS = [
  { to: "/admin", label: "Resumen", icon: "M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z" },
  { to: "/admin/usuarios", label: "Usuarios", icon: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m13 10v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" },
  { to: "/admin/productos", label: "Productos", icon: "M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8" },
  { to: "/admin/tiendas", label: "Tiendas", icon: "M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9h18M9 20v-6h6v6" },
];

// Panel admin: sidebar con las secciones (en móvil, pestañas arriba).
export default function Admin() {
  return (
    <div className="admin">
      <aside className="admin-nav">
        <div className="admin-nav-title">Admin</div>
        <nav>
          {SECTIONS.map((s) => (
            <NavLink key={s.to} to={s.to} end={s.to === "/admin"}>
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={s.icon} />
              </svg>
              {s.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="admin-content">
        <Routes>
          <Route index element={<Summary />} />
          <Route path="usuarios" element={<Users />} />
          <Route path="productos" element={<Products />} />
          <Route path="tiendas" element={<Stores />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </div>
    </div>
  );
}
