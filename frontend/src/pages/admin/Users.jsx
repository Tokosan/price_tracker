import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api.js";
import { formatDate } from "../../format.js";
import { useAdminData } from "./useAdmin.js";

export default function Users() {
  const { data, error, run } = useAdminData(["/api/admin/users"]);
  const [newUser, setNewUser] = useState("");
  const [invite, setInvite] = useState(null);

  const createUser = (e) => {
    e.preventDefault();
    run(async () => {
      const r = await api("/api/admin/users", { method: "POST", body: { username: newUser } });
      setInvite({ username: r.user.username, url: r.invite_url });
      setNewUser("");
    });
  };
  const reinvite = (u) => run(async () => {
    const r = await api(`/api/admin/users/${u.id}/invite`, { method: "POST" });
    setInvite({ username: u.username, url: r.invite_url });
  });
  const patchUser = (u, body) => run(() => api(`/api/admin/users/${u.id}`, { method: "PATCH", body }));
  const setQuota = (u) => {
    const q = prompt(`Cuota de productos para ${u.username}`, u.watch_quota);
    if (q !== null && q !== "") patchUser(u, { watch_quota: Number(q) });
  };

  const users = data?.[0] ?? [];
  return (
    <>
      <h1>Usuarios</h1>
      {error && <p className="error">{error}</p>}
      <section className="card">
        <h2>Invitar</h2>
        <form className="url-form" onSubmit={createUser}>
          <input placeholder="nuevo usuario" value={newUser} onChange={(e) => setNewUser(e.target.value)} />
          <button disabled={!newUser}>Crear e invitar</button>
        </form>
        {invite && (
          <div className="invite-box">
            <p>Link de invitación para <b>{invite.username}</b> (un solo uso, 48 h):</p>
            <code>{invite.url}</code>
            <button className="secondary" onClick={() => navigator.clipboard?.writeText(invite.url)}>Copiar</button>
          </div>
        )}
      </section>

      <section className="card table-card">
        {!data ? <p className="muted pad">Cargando…</p> : (
          <table>
            <thead>
              <tr><th>Usuario</th><th>Rol</th><th className="num">Productos</th><th className="num">Avisos 7 d</th><th>Estado</th><th /></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={u.active ? "" : "muted"}>
                  <td className="strong">{u.username}</td>
                  <td>{u.role}</td>
                  <td className="num nowrap">
                    <Link to={`/admin/productos?usuario=${u.id}`} title="Ver sus productos">{u.watch_count}</Link>
                    {" / "}
                    <button className="link" onClick={() => setQuota(u)} title="Cambiar cuota">{u.watch_quota}</button>
                  </td>
                  <td className="num">{u.notifications_7d}</td>
                  <td className="small">
                    {u.active ? "activo" : "desactivado"}
                    {!u.has_password && " · sin contraseña"}
                    {u.pending_invite_expires_at && ` · invitación hasta ${formatDate(u.pending_invite_expires_at)}`}
                  </td>
                  <td className="nowrap num">
                    <button className="link" onClick={() => reinvite(u)}>{u.has_password ? "Reset" : "Nuevo link"}</button>
                    {u.role !== "admin" && (
                      <button className="link" onClick={() => patchUser(u, { active: !u.active })}>{u.active ? "Desactivar" : "Activar"}</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
