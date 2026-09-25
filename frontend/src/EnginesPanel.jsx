import React, { useEffect, useState } from "react";
import { apiJson } from "./ui.jsx";

/* Engines (advanced, in Studio): which engine does each job, how the GPU is shared,
   and a button to free it. Create never shows any of this. */

const KIND_NAMES = { voice_converter: "My Voice conversion", guide_singer: "Guide singer", section_generator: "Generated sections" };
const POLICY_TEXT = {
  balanced: "Balanced: load an engine for a job, free the GPU right after (default)",
  keep_warm: "Keep warm: keep the last engine loaded until another needs the GPU (faster repeats)",
  low_memory: "Low memory: like Balanced, and only start when there is room for the engine's full estimate",
};

export default function EnginesPanel({ API }) {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const load = () => apiJson(`${API}/models`).then(setSt).catch(e => setError(e.message));
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [API]);
  const post = async (path, body) => {
    try { setSt(await apiJson(`${API}/models/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })); setError(""); }
    catch (e) { setError(e.message); }
  };
  if (!st) return <div className="au-card" style={{ marginTop: 22 }}>{error || "Loading engines…"}</div>;
  const byId = Object.fromEntries(st.models.map(m => [m.id, m]));

  return <section className="au-card au-console" style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 12 }} aria-label="Engines">
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <div>
        <div className="au-label">Engines</div>
        <div style={{ fontSize: 12, color: "var(--steel)" }}>
          One heavy engine uses the GPU at a time. {st.busy ? `Busy: ${byId[st.busy]?.name || st.busy}${st.busy_with ? ` (${st.busy_with})` : ""}.` : "Idle."}
          {st.free_commit_gb != null && ` ${st.free_commit_gb} GB memory free.`}</div>
      </div>
      <button className="au-btn" onClick={() => post("release")} disabled={!st.loaded.length}
        title="Unload every engine that is holding GPU memory">{st.loaded.length ? `Free the GPU (${st.loaded.join(", ")})` : "GPU is free"}</button>
    </div>
    {error && <div role="alert" style={{ color: "var(--warn)", fontSize: 13 }}>{error}</div>}
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span className="au-caption">GPU sharing</span>
      <select className="au-input" value={st.policy} onChange={e => post("policy", { policy: e.target.value })}>
        {st.policies.map(p => <option key={p} value={p}>{POLICY_TEXT[p] || p}</option>)}
      </select>
    </label>
    {Object.entries(st.kinds).map(([kind, k]) => <div key={kind} style={{ borderTop: "1px solid var(--hairline)", paddingTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
        <b style={{ fontSize: 14 }}>{KIND_NAMES[kind] || kind}</b>
        <span style={{ fontSize: 12, color: "var(--steel)" }}>{k.why}</span>
      </div>
      <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
        {k.options.map(id => {
          const m = byId[id];
          return <div key={id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 8, alignItems: "center", fontSize: 12 }}>
            <span><b style={{ color: k.active === id ? "var(--gold-light)" : "var(--ivory)" }}>{m.name}</b>
              <span style={{ color: m.installed ? "var(--signal)" : "var(--steel-dim)" }}> · {m.installed ? (m.loaded ? "loaded" : "installed") : "not installed"}</span>
              <span style={{ color: "var(--steel)" }}> · {m.licence}{m.vram_gb ? ` · ~${m.vram_gb} GB VRAM` : ""}</span>
              {m.notes && <span style={{ display: "block", color: "var(--steel-dim)" }}>{m.notes}</span>}</span>
            {m.installed && k.active !== id && <button className="bp-icon" onClick={() => post("select", { kind, model_id: id })}>Use</button>}
          </div>;
        })}
        {kind === "section_generator" && k.active && <button className="bp-icon" style={{ justifySelf: "start" }}
          onClick={() => post("select", { kind, model_id: null })}>Use the built-in synth only</button>}
      </div>
    </div>)}
    <div style={{ fontSize: 11, color: "var(--steel-dim)" }}>Engines that aren't installed are planned plug-ins; see docs/MODEL_OPTIONS.md. Nothing is downloaded from here.</div>
  </section>;
}
