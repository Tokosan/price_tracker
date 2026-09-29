import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useMe } from "../App.jsx";

export default function Invite() {
  const { token } = useParams();
  const { reload } = useMe();
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/api/auth/invite/${token}`).then(setInfo).catch((e) => setError(e.message));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== repeat) return setError("Las contraseñas no coinciden.");
    setBusy(true);
    setError("");
    try {
      await api(`/api/auth/invite/${token}`, { method: "POST", body: { password } });
      await reload();
      navigate("/");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <h1>Crear contraseña</h1>
        {!info && !error && <p className="muted">Revisando la invitación…</p>}
        {info && (
          <>
            <p>
              Hola, <b>{info.username}</b>. Elige una contraseña (mínimo 10 caracteres).
            </p>
            <label>Contraseña<input type="password" autoComplete="new-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <label>Repítela<input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} /></label>
            <button disabled={busy || password.length < 10}>{busy ? "Guardando…" : "Guardar y entrar"}</button>
          </>
        )}
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
