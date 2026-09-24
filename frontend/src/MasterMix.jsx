import React, { useEffect, useRef, useState } from "react";
import SaveToProject from "./SaveToProject.jsx";
import { Icon, apiJson } from "./ui.jsx";

/* Master a stereo mix, or mix + master from stems. Same backend flow as
   before (/upload or /jobs + /upload-stem → /master or /mix → download),
   restyled for the console shell. */

const ROLES = ["vocal", "drums", "bass", "harmonic", "other"];
const ROLE_COLORS = { vocal: "#8fe9ff", drums: "#d4af5f", bass: "#b8862f", harmonic: "#6fd0e0", other: "#9aa1ad" };
const PROFILES = [
  { id: "vocal-forward-rnb", name: "Vocal-Forward R&B", lufs: -14, desc: "Silky vocal · warm low-mids · smooth density" },
  { id: "warm-soul", name: "Warm Soul", lufs: -15, desc: "Round lows · gentle highs · analog restraint" },
  { id: "pop-maximal", name: "Maximalist Pop Polish", lufs: -10, desc: "Forward vocal · wide image · bright top end" },
  { id: "rhythmic-sparse", name: "Rhythmic Sparse Low-End", lufs: -12, desc: "Heavy sub · open space · punchy transients" },
  { id: "neutral", name: "Neutral Transparent", lufs: -14, desc: "Faithful master with minimal character" },
];
const LOUDNESS = [{ v: -9, l: "Loud" }, { v: -14, l: "Streaming" }, { v: -16, l: "Dynamic" }];

function RolePill({ role }) {
  return <span style={{
    padding: "4px 9px", borderRadius: 999, fontSize: 11, fontWeight: 800,
    background: `${ROLE_COLORS[role] || "#9aa1ad"}22`, color: ROLE_COLORS[role] || "#9aa1ad",
  }}>{role}</span>;
}

export default function MasterMix({ API, mode }) {
  const isMix = mode === "mix";
  const [step, setStep] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [stems, setStems] = useState([]);
  const [roleOverrides, setRoleOverrides] = useState({});
  const [refName, setRefName] = useState("");
  const [useRef_, setUseRef] = useState(false);
  const [prog, setProg] = useState(0);
  const [stage, setStage] = useState("");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [lufs, setLufs] = useState(-14);
  const fileInput = useRef();
  const refInput = useRef();
  const socket = useRef(null);

  useEffect(() => reset(), [mode]);
  useEffect(() => () => socket.current?.close(), []);

  function reset() {
    setStep(0); setJobId(null); setProfile(null); setStems([]); setRoleOverrides({});
    setRefName(""); setUseRef(false); setResult(null); setErr(null); setProg(0); setStage("");
  }

  async function onFiles(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    setErr(null);
    try {
      if (isMix) {
        const { job_id } = await apiJson(`${API}/jobs`, { method: "POST" });
        setJobId(job_id);
        const uploaded = [];
        for (const f of files) {
          const fd = new FormData();
          fd.append("file", f);
          const stem = await apiJson(`${API}/upload-stem/${job_id}`, { method: "POST", body: fd });
          uploaded.push({ filename: stem.stem, role: null });
        }
        setStems(uploaded);
      } else {
        const fd = new FormData();
        fd.append("file", files[0]);
        const r = await apiJson(`${API}/upload`, { method: "POST", body: fd });
        setJobId(r.job_id);
      }
      setStep(1);
    } catch (error) { setErr(error.message); }
  }

  async function onReference(e) {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f || !jobId) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const data = await apiJson(`${API}/upload-reference/${jobId}`, { method: "POST", body: fd });
      setRefName(data.reference); setUseRef(true);
    } catch (error) { setErr(error.message); }
  }

  async function start() {
    setStep(2); setProg(0); setErr(null);
    try {
      await apiJson(`${API}/${isMix ? "mix" : "master"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId, profile_id: profile, target_lufs: lufs, use_reference: useRef_,
          ...(isMix ? { role_overrides: roleOverrides } : {}),
        }),
      });
      socket.current?.close();
      const ws = new WebSocket(`${API.replace("http", "ws")}/ws/jobs/${jobId}`);
      socket.current = ws;
      ws.onmessage = message => {
        const d = JSON.parse(message.data);
        if (d.error) { setErr(d.error); setStep(1); return; }
        setStage(d.stage); setProg(d.pct);
        if (d.stage === "done") { setResult(d.result); setStep(3); }
      };
    } catch (error) { setErr(error.message); setStep(1); }
  }

  const steps = [isMix ? "Stems" : "Upload", "Sound", "Process", "Master"];
  const master = result?.master_result ?? result;

  return <div className="au-page-scroll" style={{ maxWidth: 1100 }}>
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div>
        <h1 className="au-title au-shine">{isMix ? "Mix from stems" : "Master a mix"}</h1>
        <p className="au-sub">{isMix ? "Auralis labels each stem, balances the mix, then masters it." : "Loudness, true peak, tone and width, rendered locally."}</p>
      </div>
      <ol aria-label="Progress" style={{ display: "flex", gap: 6, listStyle: "none", margin: 0, padding: 0 }}>
        {steps.map((s, i) => <li key={s} className="au-mono" aria-current={i === step ? "step" : undefined} style={{
          fontSize: 12, padding: "6px 10px", borderRadius: 8,
          background: i === step ? "#1a1509" : "var(--panel)", color: i <= step ? "var(--gold-light)" : "var(--steel)",
          border: `1px solid ${i === step ? "rgba(212,175,95,0.5)" : "var(--edge)"}`,
        }}>{String(i + 1).padStart(2, "0")} {s}</li>)}
      </ol>
    </div>

    {err && <div role="alert" className="au-card" style={{ marginTop: 16, borderColor: "rgba(255,154,122,0.5)", color: "var(--warn)" }}>{err}</div>}

    {step === 0 && <button className="au-card au-console" onClick={() => fileInput.current.click()} style={{
      marginTop: 20, width: "100%", minHeight: 260, cursor: "pointer", color: "inherit", font: "inherit",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12,
    }}>
      <Icon name="wave" size={54} stroke="#d4af5f" />
      <span style={{ fontSize: 20, fontWeight: 800 }}>{isMix ? "Choose stem files" : "Choose a stereo mix"}</span>
      <span style={{ color: "var(--steel)", fontSize: 13 }}>{isMix ? "Select every track at once · WAV · FLAC · MP3" : "WAV · FLAC · MP3"}</span>
    </button>}
    <input ref={fileInput} type="file" accept="audio/*" multiple={isMix} hidden onChange={onFiles} />

    {step === 1 && <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 20 }}>
      {isMix && stems.length > 0 && <div className="au-card au-console">
        <div className="au-label" style={{ marginBottom: 10 }}>{stems.length} stems · confirm roles</div>
        {stems.map((stem, i) => {
          const role = roleOverrides[stem.filename] || stem.role || "other";
          return <div key={`${stem.filename}-${i}`} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderTop: i ? "1px solid var(--hairline)" : "none", flexWrap: "wrap" }}>
            <RolePill role={role} />
            <span style={{ flex: "1 1 200px", fontWeight: 700, overflowWrap: "anywhere" }}>{stem.filename}</span>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {ROLES.map(r => <button key={r} className="au-pill" aria-pressed={role === r} style={{ height: 30 }}
                onClick={() => setRoleOverrides(prev => ({ ...prev, [stem.filename]: r }))}>{r}</button>)}
            </div>
          </div>;
        })}
      </div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
        {PROFILES.map(p => <button key={p.id} onClick={() => { setProfile(p.id); setLufs(p.lufs); }} aria-pressed={profile === p.id}
          className="au-card" style={{
            textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit",
            borderColor: profile === p.id ? "var(--gold)" : "var(--edge)", background: profile === p.id ? "#1a1509" : "var(--panel)",
          }}>
          <div style={{ fontWeight: 800 }}>{p.name}</div>
          <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>{p.desc}</div>
          <div className="au-mono" style={{ fontSize: 11, color: "var(--gold-light)", marginTop: 8 }}>{p.lufs} LUFS</div>
        </button>)}
      </div>

      <div className="au-card" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="au-label">Delivery loudness</span>
        <div className="au-segment" role="tablist" aria-label="Delivery loudness">
          {LOUDNESS.map(o => <button key={o.v} role="tab" aria-selected={lufs === o.v} onClick={() => setLufs(o.v)}>{o.l} · {o.v}</button>)}
        </div>
      </div>

      <button className="au-card" onClick={() => refInput.current.click()} style={{ cursor: "pointer", color: "inherit", font: "inherit", textAlign: "left", borderStyle: "dashed" }}>
        <div className="au-label">{useRef_ ? `Reference armed: ${refName}` : "Optional reference track"}</div>
        <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>{useRef_ ? "Click to replace" : "A song you love, for tonal matching. It is analysed, never copied into the output."}</div>
      </button>
      <input ref={refInput} type="file" accept="audio/*" hidden onChange={onReference} />

      <div style={{ display: "flex", gap: 10 }}>
        <button className="au-btn" onClick={reset}>Start over</button>
        <button className="au-btn gold big" style={{ flexGrow: 1 }} disabled={!profile} onClick={start}>
          {isMix ? "Mix + master my tracks" : "Master my track"}</button>
      </div>
    </div>}

    {step === 2 && <div className="au-card au-console" style={{ marginTop: 20, padding: 40, textAlign: "center" }}>
      <Icon name="wave" size={64} stroke="#d4af5f" />
      <h2 className="au-title au-shine" style={{ fontSize: 22, marginTop: 16 }}>{isMix ? "Mixing and mastering" : "Mastering"}</h2>
      <div className="au-mono" style={{ color: "var(--steel)", fontSize: 12, margin: "12px 0" }}>{stage || "initializing"} · {Math.round(prog)}%</div>
      <div className="au-progress" style={{ maxWidth: 520, margin: "0 auto" }}><div style={{ width: `${prog}%` }} /></div>
    </div>}

    {step === 3 && result && <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 20 }}>
      <div className="au-card au-console" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 14 }}>
        <div><div className="au-caption">Loudness</div><div className="au-mono" style={{ fontSize: 20, marginTop: 4 }}>{master?.before_lufs} → {master?.after_lufs} LUFS</div></div>
        <div><div className="au-caption">True peak</div><div className="au-mono" style={{ fontSize: 20, marginTop: 4 }}>{master?.after_peak_db} dBTP</div></div>
        <div><div className="au-caption">Mode</div><div className="au-mono" style={{ fontSize: 20, marginTop: 4 }}>{master?.mode}</div></div>
      </div>
      {isMix && result.stem_analyses && <div className="au-card">
        {result.stem_analyses.map((a, i) => {
          const mp = result.mix_params?.[i] || {};
          return <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 0", borderTop: i ? "1px solid var(--hairline)" : "none" }}>
            <RolePill role={a.role} />
            <span style={{ flexGrow: 1, fontWeight: 700, overflowWrap: "anywhere" }}>{a.path ? a.path.split(/[/\\]/).pop() : ""}</span>
            <span className="au-mono" style={{ fontSize: 12, color: "var(--steel)" }}>
              {mp.gain_db !== undefined ? `${mp.gain_db > 0 ? "+" : ""}${mp.gain_db} dB` : ""} {mp.pan !== undefined ? `pan ${mp.pan}` : ""}</span>
          </div>;
        })}
      </div>}
      <audio controls src={`${API}/download/${jobId}`} style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <a className="au-btn gold" href={`${API}/download/${jobId}`}>Download WAV</a>
        {isMix && <a className="au-btn" href={`${API}/download-report/${jobId}`}>Mix report</a>}
        {isMix && <a className="au-btn" href={`${API}/download-session/${jobId}`}>Session JSON</a>}
        <button className="au-btn" onClick={reset}>Start over</button>
      </div>
      <SaveToProject API={API} jobId={jobId} label={isMix ? "Save stems, mix and master to a project" : "Save mix and master to a project"} />
    </div>}
  </div>;
}
