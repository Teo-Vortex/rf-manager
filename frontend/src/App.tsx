import { FormEvent, useEffect, useMemo, useState } from "react";

type Status = { connected: boolean; host: string; port: number; topic: string; last_error: string | null };
type Frame = { code: string; bits: number | null; protocol: number | null; pulse: number | null; source_bridge: string; timestamp: string; count: number; device_id: number | null; device_name: string | null; action: string | null };
type Config = { host: string; port: number; username: string | null; password_configured: boolean; tls: boolean; client_id: string; receive_topic: string };
type LogEntry = { timestamp: string; level: string; logger: string; message: string };
type DeviceCode = { id: number; code: string; action: string; protocol: number | null; bits: number | null; pulse: number | null };
type Device = { id: number; name: string; device_type: string; area: string | null; enabled: boolean; codes: DeviceCode[] };
type DraftButton = { action: string; frame: Frame | null };

const blankConfig: Config = { host: "host.docker.internal", port: 1883, username: "", password_configured: false, tls: false, client_id: "rf-manager", receive_topic: "tele/+/RESULT" };

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
  const [page, setPage] = useState<"live" | "devices" | "diagnostics">("live");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logsPaused, setLogsPaused] = useState(false);
  const [hiddenBefore, setHiddenBefore] = useState(0);
  const [devices, setDevices] = useState<Device[]>([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [deviceArea, setDeviceArea] = useState("");
  const [draftButtons, setDraftButtons] = useState<DraftButton[]>([{ action: "Button 1", frame: null }]);
  const [learningIndex, setLearningIndex] = useState<number | null>(null);
  const [candidate, setCandidate] = useState<Frame | null>(null);
  const [wizardNotice, setWizardNotice] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([fetch("/api/status").then(r => r.json()), fetch("/api/events").then(r => r.json()), fetch("/api/settings/mqtt").then(r => r.json())]).then(([s, e, c]) => { setStatus(s); setEvents(e); setConfig(c); if (!s.connected) setSettingsOpen(true); });
    const timer = window.setInterval(() => fetch("/api/status").then(r => r.json()).then(setStatus), 3000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (paused) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${location.host}/api/ws/live`);
    ws.onmessage = message => {
      const frame = JSON.parse(message.data) as Frame;
      if (learningIndex !== null) setCandidate(frame);
      setEvents(current => [frame, ...current.filter(item => !(item.code === frame.code && item.source_bridge === frame.source_bridge))].slice(0, 200));
    };
    return () => ws.close();
  }, [paused, learningIndex]);

  useEffect(() => {
    if (page === "devices") fetch("/api/devices").then(r => r.json()).then(setDevices);
    if (page !== "diagnostics" || logsPaused) return;
    const load = () => fetch("/api/diagnostics/logs?limit=500").then(r => r.json()).then(setLogs);
    load(); const timer = window.setInterval(load, 2000); return () => window.clearInterval(timer);
  }, [page, logsPaused]);

  const visible = useMemo(() => { const q = search.trim().toLowerCase(); return q ? events.filter(item => `${item.code} ${item.source_bridge} ${item.device_name || ""} ${item.action || ""}`.toLowerCase().includes(q)) : events; }, [events, search]);
  const visibleLogs = logs.filter(entry => new Date(entry.timestamp).getTime() > hiddenBefore);

  async function saveSettings(event: FormEvent) {
    event.preventDefault(); setSaving(true); setNotice("");
    const response = await fetch("/api/settings/mqtt", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host: config.host, port: Number(config.port), username: config.username || null, password: password || null, tls: config.tls, client_id: config.client_id, receive_topic: config.receive_topic }) });
    setSaving(false); if (!response.ok) { setNotice("Could not save MQTT settings."); return; }
    setPassword(""); setNotice("Saved. Connecting to MQTT...");
  }

  function setButtonCount(count: number) {
    const safe = Math.min(Math.max(count, 1), 16);
    setDraftButtons(current => Array.from({ length: safe }, (_, index) => current[index] || { action: `Button ${index + 1}`, frame: null }));
  }

  function useCandidate() {
    if (learningIndex === null || !candidate) return;
    setDraftButtons(current => current.map((button, index) => index === learningIndex ? { ...button, frame: candidate } : button));
    setCandidate(null); setLearningIndex(null);
  }

  function openNewDevice() {
    setEditingId(null); setDeviceName(""); setDeviceArea(""); setDraftButtons([{ action: "Button 1", frame: null }]); setWizardNotice(""); setWizardOpen(true);
  }

  function openEditDevice(device: Device) {
    setEditingId(device.id); setDeviceName(device.name); setDeviceArea(device.area || "");
    setDraftButtons(device.codes.map(code => ({ action: code.action, frame: { code: code.code, protocol: code.protocol, bits: code.bits, pulse: code.pulse, source_bridge: "saved", timestamp: new Date().toISOString(), count: 1, device_id: device.id, device_name: device.name, action: code.action } })));
    setWizardNotice(""); setLearningIndex(null); setCandidate(null); setWizardOpen(true);
  }

  async function submitDevice(allowDuplicates: boolean) {
    const payload = { name: deviceName, area: deviceArea || null, device_type: "remote_control", allow_duplicates: allowDuplicates, codes: draftButtons.map(button => ({ action: button.action, code: button.frame!.code, protocol: button.frame!.protocol, bits: button.frame!.bits, pulse: button.frame!.pulse })) };
    return fetch(editingId ? `/api/devices/${editingId}` : "/api/devices", { method: editingId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  }

  async function saveDevice(event: FormEvent) {
    event.preventDefault(); setWizardNotice("");
    if (draftButtons.some(button => !button.frame)) { setWizardNotice("Learn a code for every button first."); return; }
    let response = await submitDevice(false);
    if (response.status === 409) {
      const body = await response.json(); const conflicts = body.detail.conflicts as Array<{code:string;device_name:string;action:string}>;
      const summary = conflicts.map(item => `${item.code}: ${item.device_name} → ${item.action}`).join("\n");
      if (!confirm(`These RF codes are already assigned:\n\n${summary}\n\nAllow duplicate assignment?`)) { setWizardNotice("Duplicate assignment cancelled."); return; }
      response = await submitDevice(true);
    }
    if (!response.ok) { setWizardNotice("Could not save device."); return; }
    const saved = await response.json(); setDevices(current => editingId ? current.map(item => item.id === editingId ? saved : item) : [...current, saved]); setWizardOpen(false); setEditingId(null); setDeviceName(""); setDeviceArea(""); setDraftButtons([{ action: "Button 1", frame: null }]);
  }

  return <div className="shell"><aside>
    <div className="brand"><span className="signal">⌁</span><div><strong>RF Manager</strong><small>433 MHz control</small></div></div>
    <nav><button className={page === "live" ? "active" : ""} onClick={() => setPage("live")}>Live RF</button><button className={page === "devices" ? "active" : ""} onClick={() => setPage("devices")}>Devices</button><button className={page === "diagnostics" ? "active" : ""} onClick={() => setPage("diagnostics")}>Diagnostics</button></nav>
    <button className="settings-link" onClick={() => { setPage("live"); setSettingsOpen(true); }}>⚙ MQTT settings</button>
    <div className={`broker ${status?.connected ? "online" : "offline"}`}><i /><div><strong>{status?.connected ? "MQTT connected" : "MQTT disconnected"}</strong><small>{status ? `${status.host}:${status.port}` : "Loading..."}</small></div></div>
  </aside><main>
    {page === "live" && <><header><div><p className="eyebrow">REAL-TIME MONITOR</p><h1>Live RF activity</h1><p>Signals received from your Tasmota RF Bridge.</p></div><button className="secondary" onClick={() => setSettingsOpen(!settingsOpen)}>Configure MQTT</button></header>
      {settingsOpen && <section className="settings-card"><div><p className="eyebrow">CONNECTION</p><h2>MQTT broker</h2><p>On ZimaOS use <code>host.docker.internal</code>.</p></div><form onSubmit={saveSettings}>
        <label className="wide">Broker host<input value={config.host} onChange={e => setConfig({...config, host:e.target.value})} required /></label><label>Port<input type="number" value={config.port} onChange={e => setConfig({...config, port:Number(e.target.value)})} required /></label><label>Username<input value={config.username || ""} onChange={e => setConfig({...config, username:e.target.value})} /></label><label>Password<input type="password" value={password} placeholder={config.password_configured ? "Saved - leave blank to keep" : "Optional"} onChange={e => setPassword(e.target.value)} /></label><label>Client ID<input value={config.client_id} onChange={e => setConfig({...config, client_id:e.target.value})} /></label><label className="wide">Tasmota receive topic<input value={config.receive_topic} onChange={e => setConfig({...config, receive_topic:e.target.value})} /></label><label className="check"><input type="checkbox" checked={config.tls} onChange={e => setConfig({...config, tls:e.target.checked})} /> Use TLS</label><div className="form-actions"><span>{notice}</span><button disabled={saving}>{saving ? "Saving..." : "Save & connect"}</button></div>
      </form></section>}
      <section className="toolbar"><input placeholder="Search code, device or bridge..." value={search} onChange={e => setSearch(e.target.value)} /><div><button className="ghost" onClick={() => setPaused(!paused)}>{paused ? "Resume" : "Pause"}</button><button className="ghost" onClick={() => setEvents([])}>Clear view</button></div></section>
      <section className="table-card"><table><thead><tr><th>Time</th><th>RF code</th><th>Status</th><th>Protocol</th><th>Bits</th><th>Pulse</th><th>Count</th><th>Bridge</th></tr></thead><tbody>{visible.map((frame,index) => <tr key={`${frame.timestamp}-${index}`}><td>{new Date(frame.timestamp).toLocaleTimeString()}</td><td><code className="rf-code">{frame.code}</code></td><td>{frame.device_name ? <span className="known">{frame.device_name} → {frame.action}</span> : <span className="unknown">Unknown</span>}</td><td>{frame.protocol ?? "—"}</td><td>{frame.bits ?? "—"}</td><td>{frame.pulse ?? "—"}</td><td>{frame.count}</td><td>{frame.source_bridge}</td></tr>)}</tbody></table>{!visible.length && <div className="empty"><span>⌁</span><h3>Waiting for RF signals</h3><p>Press a button on a 433 MHz remote.</p></div>}</section>
    </>}
    {page === "devices" && <><header><div><p className="eyebrow">RF DEVICES</p><h1>Devices</h1><p>Name physical remotes and map their buttons to RF codes.</p></div><button className="primary" onClick={openNewDevice}>+ Add remote</button></header>
      {wizardOpen && <section className="wizard-card"><div className="wizard-head"><div><p className="eyebrow">{editingId ? "EDIT DEVICE" : "NEW DEVICE"}</p><h2>Remote Control</h2></div><button className="ghost" onClick={() => { setWizardOpen(false); setLearningIndex(null); }}>Cancel</button></div><form onSubmit={saveDevice}>
        <div className="wizard-grid"><label>Name<input value={deviceName} onChange={e => setDeviceName(e.target.value)} placeholder="Garage Remote" required /></label><label>Area<input value={deviceArea} onChange={e => setDeviceArea(e.target.value)} placeholder="Garage" /></label><label>Buttons<input type="number" min="1" max="16" value={draftButtons.length} onChange={e => setButtonCount(Number(e.target.value))} /></label></div>
        <div className="button-learn-list">{draftButtons.map((button,index) => <div className="learn-row" key={index}><span>{index+1}</span><input value={button.action} onChange={e => setDraftButtons(current => current.map((item,i) => i === index ? {...item, action:e.target.value} : item))} required /><code>{button.frame?.code || "No code learned"}</code><button type="button" className={button.frame ? "ghost learned" : "secondary"} onClick={() => { setLearningIndex(index); setCandidate(null); }}>{button.frame ? "Learn again" : "Learn"}</button></div>)}</div>
        {learningIndex !== null && <div className="learning-panel"><i /><div><strong>Waiting for {draftButtons[learningIndex].action}</strong>{candidate ? <p>Received <code>{candidate.code}</code> · {candidate.bits ?? "?"} bits · protocol {candidate.protocol ?? "?"}</p> : <p>Press the physical button now...</p>}</div>{candidate && <><button type="button" className="primary" onClick={useCandidate}>Use this code</button><button type="button" className="ghost" onClick={() => setCandidate(null)}>Wait for another</button></>}</div>}
        <div className="wizard-actions"><span>{wizardNotice}</span><button className="primary" disabled={!deviceName || draftButtons.some(button => !button.frame)}>{editingId ? "Save changes" : "Save remote"}</button></div>
      </form></section>}
      <section className="device-grid">{devices.map(device => <article className="device-card" key={device.id}><div><span className="device-icon">⌁</span><small>Remote control</small><h3>{device.name}</h3><p>{device.area || "No area"} · {device.codes.length} button{device.codes.length === 1 ? "" : "s"}</p></div><ul>{device.codes.map(code => <li key={code.id}><span>{code.action}</span><code>{code.code}</code></li>)}</ul><div className="device-actions"><button className="ghost" onClick={() => openEditDevice(device)}>Edit / Learn again</button><button className="danger-link" onClick={async () => { if (confirm(`Delete ${device.name}?`)) { await fetch(`/api/devices/${device.id}`, {method:"DELETE"}); setDevices(current => current.filter(item => item.id !== device.id)); } }}>Delete</button></div></article>)}</section>
      {!devices.length && !wizardOpen && <section className="table-card empty"><span>⌁</span><h3>No RF devices yet</h3><p>Add a remote and learn its physical buttons.</p></section>}
    </>}
    {page === "diagnostics" && <><header><div><p className="eyebrow">SYSTEM DIAGNOSTICS</p><h1>Console & logs</h1><p>Connection details. Passwords are never logged.</p></div></header><section className="diagnostic-summary"><div><small>MQTT STATUS</small><strong className={status?.connected ? "good" : "bad"}>{status?.connected ? "Connected" : "Disconnected"}</strong></div><div><small>BROKER</small><strong>{status ? `${status.host}:${status.port}` : "—"}</strong></div><div><small>TOPIC</small><strong>{status?.topic || "—"}</strong></div><div><small>LAST ERROR</small><strong className="bad">{status?.last_error || "None"}</strong></div></section><section className="console-card"><div className="console-toolbar"><span>{visibleLogs.length} log entries</span><div><button className="ghost" onClick={() => setLogsPaused(!logsPaused)}>{logsPaused ? "Resume" : "Pause"}</button><button className="ghost" onClick={() => navigator.clipboard.writeText(visibleLogs.map(e => `${e.timestamp} ${e.level} ${e.logger}: ${e.message}`).join("\n"))}>Copy logs</button><button className="ghost" onClick={() => setHiddenBefore(Date.now())}>Clear view</button></div></div><div className="console">{visibleLogs.map((entry,index) => <div className={`log-line ${entry.level.toLowerCase()}`} key={`${entry.timestamp}-${index}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><b>{entry.level}</b><span>{entry.logger}</span><code>{entry.message}</code></div>)}</div></section></>}
  </main></div>;
}
