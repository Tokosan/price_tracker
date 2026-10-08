import { useState } from "react";
import { api } from "../api.js";
import { useMe } from "../App.jsx";
import RulesEditor, { defaultsFromEditor, editorFromDefaults } from "../components/RulesEditor.jsx";
import { saveTheme } from "../theme.js";

export default function Settings() {
  const { me, reload } = useMe();
  const tg = me.telegram;
  const dc = me.discord;
  const [link, setLink] = useState(null);
  const [hook, setHook] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [pw, setPw] = useState({ current: "", next: "" });

  const run = async (fn) => {
    setError("");
    setMsg("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
  };

  const connect = () => run(async () => setLink(await api("/api/channels/telegram/link", { method: "POST" })));
  const toggle = () => run(async () => {
    await api(`/api/channels/${tg.channel_id}`, { method: "PATCH", body: { enabled: !tg.enabled } });
    await reload();
  });
  const unlink = () => run(async () => {
    if (!confirm("¿Desvincular Telegram?")) return;
    await api(`/api/channels/${tg.channel_id}`, { method: "DELETE" });
    await reload();
  });
  const test = (channelId) => run(async () => {
    await api(`/api/channels/${channelId}/test`, { method: "POST" });
    setMsg("Mensaje de prueba enviado.");
  });
  const connectDiscord = (e) => {
    e.preventDefault();
    run(async () => {
      await api("/api/channels/discord", { method: "POST", body: { webhook_url: hook } });
      setHook("");
      await reload();
      setMsg("Discord conectado: te mandamos un mensaje de prueba.");
    });
  };
  const toggleDc = () => run(async () => {
    await api(`/api/channels/${dc.channel_id}`, { method: "PATCH", body: { enabled: !dc.enabled } });
    await reload();
  });
  const unlinkDc = () => run(async () => {
    if (!confirm("¿Desconectar Discord?")) return;
    await api(`/api/channels/${dc.channel_id}`, { method: "DELETE" });
    await reload();
  });
  const changePw = (e) => {
    e.preventDefault();
    run(async () => {
      await api("/api/auth/password", { method: "POST", body: { current_password: pw.current, new_password: pw.next } });
      setPw({ current: "", next: "" });
      setMsg("Contraseña cambiada. Se cerraron tus otras sesiones.");
    });
  };

  return (
    <>
      <h1>Ajustes</h1>
      <Appearance />
      <DefaultRules />
      <section className="card">
        <h2>Telegram</h2>
        {!tg.configured ? (
          <p className="muted">Telegram no configurado en el servidor. Los avisos siguen quedando en la pestaña Avisos.</p>
        ) : tg.linked ? (
          <>
            <p>
              Vinculado{tg.chat_username ? <> como <b>@{tg.chat_username}</b></> : ""} · {tg.enabled ? "activo" : "en pausa"}
            </p>
            <div className="actions">
              <button onClick={() => test(tg.channel_id)}>Enviar prueba</button>
              <button className="secondary" onClick={toggle}>{tg.enabled ? "Pausar" : "Reactivar"}</button>
              <button className="danger" onClick={unlink}>Desvincular</button>
            </div>
          </>
        ) : (
          <>
            <p>Recibe los avisos en tu Telegram a través de @{tg.bot_username || "el bot"}.</p>
            {link ? (
              <>
                <p>
                  <a className="button" href={link.url} target="_blank" rel="noreferrer">Abrir Telegram y pulsar «Iniciar»</a>
                </p>
                <p className="muted small">El link sirve una vez y dura {link.expires_in_minutes} minutos. Después vuelve aquí y recarga.</p>
                <button className="secondary" onClick={reload}>Ya lo hice</button>
              </>
            ) : (
              <button onClick={connect}>Conectar Telegram</button>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2>Discord</h2>
        {dc.linked ? (
          <>
            <p>
              Conectado ({dc.label}) · {dc.enabled ? "activo" : "en pausa"}
            </p>
            <div className="actions">
              <button onClick={() => test(dc.channel_id)}>Enviar prueba</button>
              <button className="secondary" onClick={toggleDc}>{dc.enabled ? "Pausar" : "Reactivar"}</button>
              <button className="danger" onClick={unlinkDc}>Desconectar</button>
            </div>
          </>
        ) : (
          <form className="stack" onSubmit={connectDiscord}>
            <p className="muted small">
              En Discord: Ajustes del canal → Integraciones → Webhooks → Nuevo webhook → Copiar URL.
            </p>
            <label>URL del webhook<input value={hook} onChange={(e) => setHook(e.target.value)} placeholder="https://discord.com/api/webhooks/…" /></label>
            <button disabled={!hook}>Conectar Discord</button>
          </form>
        )}
      </section>

      <section className="card">
        <h2>Cuenta</h2>
        <p className="muted small">
          Usuario <b>{me.username}</b> · {me.watch_count} productos
        </p>
        <form onSubmit={changePw} className="stack">
          <label>Contraseña actual<input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
          <label>Contraseña nueva (mín. 10)<input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
          <button disabled={!pw.current || pw.next.length < 10}>Cambiar contraseña</button>
        </form>
      </section>
      {msg && <p className="ok-msg">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </>
  );
}

// Avisos que vienen marcados al seguir un producto nuevo.
function DefaultRules() {
  const { me, reload } = useMe();
  const [editor, setEditor] = useState(() => editorFromDefaults(me.default_rules));
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const save = (rules) => {
    setError("");
    setMsg("");
    api("/api/auth/default-rules", { method: "PUT", body: { rules } })
      .then(({ default_rules }) => {
        setEditor(editorFromDefaults(default_rules));
        setMsg("Guardado: se usarán al seguir un producto nuevo.");
        return reload();
      })
      .catch((e) => setError(e.message));
  };
  const submit = () => {
    try {
      save(defaultsFromEditor(editor));
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <section className="card">
      <h2>Avisos por defecto</h2>
      <p className="muted small">
        Vienen marcados al seguir un producto (los puedes cambiar ahí mismo). Los productos que ya sigues no cambian.
        El precio objetivo depende de cada producto, así que se elige al agregarlo.
      </p>
      <RulesEditor value={editor} onChange={setEditor} forDefaults />
      <div className="actions">
        <button onClick={submit}>Guardar</button>
        {me.default_rules && (
          <button className="secondary" onClick={() => save(null)}>Restablecer los de la app</button>
        )}
      </div>
      {msg && <p className="ok-msg">{msg}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

const THEMES = [
  { value: "system", label: "Sistema" },
  { value: "light", label: "Claro" },
  { value: "dark", label: "Oscuro" },
];
const PALETTES = [
  { value: "green", label: "Verde" },
  { value: "blue", label: "Azul" },
];

// Tema y paleta: se guardan en la cuenta, así te siguen en cualquier dispositivo.
function Appearance() {
  const { me, reload } = useMe();
  const [error, setError] = useState("");
  const set = (patch) => {
    setError("");
    saveTheme(patch).then(reload).catch((e) => setError(e.message));
  };
  const prefs = me.preferences;
  return (
    <section className="card">
      <h2>Apariencia</h2>
      <div className="field-row">
        <span className="field-label">Tema</span>
        <div className="segmented" role="radiogroup" aria-label="Tema">
          {THEMES.map((t) => (
            <button key={t.value} role="radio" aria-checked={prefs.theme === t.value} className={prefs.theme === t.value ? "on" : ""} onClick={() => set({ theme: t.value })}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="field-row">
        <span className="field-label">Color</span>
        <div className="segmented" role="radiogroup" aria-label="Color">
          {PALETTES.map((p) => (
            <button key={p.value} role="radio" aria-checked={prefs.palette === p.value} className={prefs.palette === p.value ? "on" : ""} onClick={() => set({ palette: p.value })}>
              <span className={`swatch ${p.value}`} aria-hidden="true" />
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
