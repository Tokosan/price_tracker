import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useMe } from "../App.jsx";

export default function Login() {
  const { reload } = useMe();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/login", { method: "POST", body: { username, password } });
      await reload();
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <form className="card" onSubmit={submit}>
        <h1>Tracker de precios</h1>
        <label>Usuario<input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label>Contraseña<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <button disabled={busy || !username || !password}>{busy ? "Entrando…" : "Entrar"}</button>
        <p className="muted small">¿No tienes cuenta? Pídele un link de invitación al admin.</p>
      </form>
    </div>
  );
}
