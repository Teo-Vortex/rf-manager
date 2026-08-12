import { FormEvent, useEffect, useMemo, useState } from "react";

type Status = { connected: boolean; host: string; port: number; topic: string; last_error: string | null };
type Frame = {
  code: string; bits: number | null; protocol: number | null; pulse: number | null;
  source_bridge: string; timestamp: string; count: number;
};
type Config = {
  host: string; port: number; username: string | null; password_configured: boolean;
  tls: boolean; client_id: string; receive_topic: string;
};

const blankConfig: Config = {
  host: "host.docker.internal", port: 1883, username: "", password_configured: false,
  tls: false, client_id: "rf-manager", receive_topic: "tele/+/RESULT",
};

export function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<Frame[]>([]);
  const [config, setConfig] = useState<Config>(blankConfig);
  const [password, setPassword] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [paused, setPaused] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/api/status").then((r) => r.json()),
      fetch("/api/events").then((r) => r.json()),
      fetch("/api/settings/mqtt").then((r) => r.json()),
    ]).then(([nextStatus, nextEvents, nextConfig]) => {
      setStatus(nextStatus); setEvents(nextEvents); setConfig(nextConfig);
      if (!nextStatus.connected) setSettingsOpen(true);
    });
    const statusTimer = window.setInterval(() => fetch("/api/status").then((r) => r.json()).then(setStatus), 3000);
    return () => window.clearInterval(statusTimer);
  }, []);

  useEffect(() => {
    if (paused) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${location.host}/api/ws/live`);
    ws.onmessage = (message) => {
      const frame = JSON.parse(message.data) as Frame;
      setEvents((current) => [frame, ...current.filter((item) => !(item.code === frame.code && item.source_bridge === frame.source_bridge))].slice(0, 200));
    };
    return () => ws.close();
  }, [paused]);

  const visible = useMemo(() => {
    const value = search.trim().toLowerCase();
    return value ? events.filter((item) => `${item.code} ${item.source_bridge}`.toLowerCase().includes(value)) : events;
  }, [events, search]);

  async function saveSettings(event: FormEvent) {
    event.preventDefault(); setSaving(true); setNotice("");
    const response = await fetch("/api/settings/mqtt", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        host: config.host, port: Number(config.port), username: config.username || null,
        password: password || null, tls: config.tls, client_id: config.client_id,
        receive_topic: config.receive_topic,
      }),
    });
    setSaving(false);
    if (!response.ok) { setNotice("Could not save MQTT settings."); return; }
    setPassword(""); setNotice("Saved. Connecting to MQTT…");
    window.setTimeout(() => fetch("/api/status").then((r) => r.json()).then(setStatus), 1200);
  }

  return <div className="shell">
    <aside>
      <div className="brand"><span className="signal">⌁</span><div><strong>RF Manager</strong><small>433 MHz control</small></div></div>
      <nav><button className="active">Live RF</button><button disabled>Devices <em>Soon</em></button><button disabled>Events <em>Soon</em></button></nav>
      <button className="settings-link" onClick={() => setSettingsOpen(!settingsOpen)}>⚙ MQTT settings</button>
      <div className={`broker ${status?.connected ? "online" : "offline"}`}><i />
        <div><strong>{status?.connected ? "MQTT connected" : "MQTT disconnected"}</strong><small>{status ? `${status.host}:${status.port}` : "Loading…"}</small></div>
      </div>
    </aside>
    <main>
      <header><div><p className="eyebrow">REAL-TIME MONITOR</p><h1>Live RF activity</h1><p>Signals received from your Tasmota RF Bridge.</p></div><button className="secondary" onClick={() => setSettingsOpen(!settingsOpen)}>Configure MQTT</button></header>
      {settingsOpen && <section className="settings-card">
        <div><p className="eyebrow">CONNECTION</p><h2>MQTT broker</h2><p>For a broker running on this computer, keep <code>host.docker.internal</code>.</p></div>
        <form onSubmit={saveSettings}>
          <label className="wide">Broker host<input value={config.host} onChange={(e) => setConfig({...config, host: e.target.value})} required /></label>
          <label>Port<input type="number" value={config.port} onChange={(e) => setConfig({...config, port: Number(e.target.value)})} required /></label>
          <label>Username<input value={config.username || ""} onChange={(e) => setConfig({...config, username: e.target.value})} /></label>
          <label>Password<input type="password" value={password} placeholder={config.password_configured ? "Saved — leave blank to keep" : "Optional"} onChange={(e) => setPassword(e.target.value)} /></label>
          <label>Client ID<input value={config.client_id} onChange={(e) => setConfig({...config, client_id: e.target.value})} /></label>
          <label className="wide">Tasmota receive topic<input value={config.receive_topic} onChange={(e) => setConfig({...config, receive_topic: e.target.value})} /></label>
          <label className="check"><input type="checkbox" checked={config.tls} onChange={(e) => setConfig({...config, tls: e.target.checked})} /> Use TLS</label>
          <div className="form-actions"><span>{notice}</span><button disabled={saving}>{saving ? "Saving…" : "Save & connect"}</button></div>
        </form>
      </section>}
      <section className="toolbar"><input placeholder="Search code or bridge…" value={search} onChange={(e) => setSearch(e.target.value)} /><div><button className="ghost" onClick={() => setPaused(!paused)}>{paused ? "Resume" : "Pause"}</button><button className="ghost" onClick={() => setEvents([])}>Clear view</button></div></section>
      <section className="table-card">
        <table><thead><tr><th>Time</th><th>RF code</th><th>Status</th><th>Protocol</th><th>Bits</th><th>Pulse</th><th>Count</th><th>Bridge</th></tr></thead>
          <tbody>{visible.map((frame, index) => <tr key={`${frame.timestamp}-${frame.code}-${index}`}><td>{new Date(frame.timestamp).toLocaleTimeString()}</td><td><code className="rf-code">{frame.code}</code></td><td><span className="unknown">Unknown</span></td><td>{frame.protocol ?? "—"}</td><td>{frame.bits ?? "—"}</td><td>{frame.pulse ?? "—"}</td><td>{frame.count}</td><td>{frame.source_bridge}</td></tr>)}</tbody>
        </table>
        {!visible.length && <div className="empty"><span>⌁</span><h3>Waiting for RF signals</h3><p>Press a button on a 433 MHz remote. Incoming Tasmota messages will appear here.</p></div>}
      </section>
    </main>
  </div>;
}
