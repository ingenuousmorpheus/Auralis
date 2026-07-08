import React, { useRef, useState } from "react";
import VoiceStudio from "./VoiceStudio.jsx";
import VocalRack from "./VocalRack.jsx";
import "./App.css";

const API = import.meta.env.VITE_API ?? "http://127.0.0.1:8001";
const V = "#8d70ff";
const T = "#46f6bd";
const PK = "#ff62c8";
const PANEL = "rgba(14,19,31,.78)";
const PANEL2 = "rgba(255,255,255,.055)";
const TEXT = "#edf4ff";
const MUTE = "#8f9bb4";

const ROLES = ["vocal", "drums", "bass", "harmonic", "other"];
const ROLE_COLORS = { vocal: PK, drums: "#ffbd73", bass: T, harmonic: V, other: MUTE };
const PROFILES = [
  { id: "pop-maximal", name: "Maximalist Pop Polish", lufs: -10, desc: "Forward vocal · wide image · bright top end" },
  { id: "vocal-forward-rnb", name: "Vocal-Forward R&B", lufs: -14, desc: "Silky vocal · warm low-mids · smooth density" },
  { id: "rhythmic-sparse", name: "Rhythmic Sparse Low-End", lufs: -12, desc: "Heavy sub · open space · punchy transient shape" },
  { id: "warm-soul", name: "Warm Soul", lufs: -15, desc: "Round lows · gentle highs · analog restraint" },
  { id: "neutral", name: "Neutral Transparent", lufs: -14, desc: "Faithful master with minimal character" },
];

function Mark({ size = 32 }) {
  const bars = 40;
  const ri = size * 0.26;
  const ro = size * 0.5;
  const c = size / 2;
  const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const violet = [141, 112, 255], mint = [70, 246, 189], pink = [255, 98, 200];
  return <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
    {Array.from({ length: bars }).map((_, i) => {
      const ang = (i / bars) * 2 * Math.PI - Math.PI / 2;
      const amp = 0.4 + 0.6 * Math.abs(Math.sin(i * 0.7));
      const r = ri + (ro - ri) * amp;
      const t = i / bars;
      const col = t < 0.5 ? lerp(violet, mint, t * 2) : lerp(mint, pink, (t - 0.5) * 2);
      return <line key={i}
        x1={c + ri * Math.cos(ang)} y1={c + ri * Math.sin(ang)}
        x2={c + r * Math.cos(ang)} y2={c + r * Math.sin(ang)}
        stroke={`rgb(${col})`} strokeWidth={size * 0.05} strokeLinecap="round" />;
    })}
    <circle cx={c} cy={c} r={ri * 0.58} fill="#07101a" />
    <circle cx={c} cy={c} r={size * 0.055} fill={T} />
  </svg>;
}

function SpectralConsole() {
  const lanes = [
    [22, 34, 18, 42, 28, 52, 20, 44, 58, 26, 36, 48, 30, 56, 24, 44, 62, 34, 20, 48, 38, 54],
    [16, 24, 54, 34, 26, 48, 36, 20, 42, 58, 32, 18, 50, 38, 28, 46, 60, 22, 40, 32, 52, 26],
    [30, 18, 28, 62, 44, 24, 36, 52, 22, 46, 64, 34, 26, 56, 42, 18, 30, 48, 38, 58, 24, 44],
  ];
  return <div className="console-panel">
    <div className="console-header">
      <div>
        <div className="eyebrow" style={{ margin: 0 }}>Spectral Control Room</div>
        <div className="brand-subtitle">voice · mix · master pipeline</div>
      </div>
      <span className="status-pill ok"><span className="pulse-dot" />GPU ready</span>
    </div>
    <div className="console-screen">
      <div className="spectral-grid" />
      <div className="wave-stack">
        {lanes.map((lane, index) => <div className="wave-lane" key={index}>
          <div className="wave-bars">
            {lane.map((height, i) => <i key={i} style={{ "--h": height }} />)}
          </div>
        </div>)}
      </div>
      <div className="meter-bank">
        {["72%", "88%", "61%", "79%"].map((level, i) =>
          <div className="meter" key={i}><span style={{ "--level": level }} /></div>)}
      </div>
    </div>
  </div>;
}

function WorkflowRail({ steps, step, mode, reset }) {
  return <aside className="workflow-rail">
    <div className="eyebrow" style={{ marginBottom: 10 }}>Session flow</div>
    <h3 className="inspector-title">{mode === "mix" ? "Stem mixdown" : "Stereo master"}</h3>
    <div className="step-list">
      {steps.map((s, i) => <div key={s} className={`step-item ${i <= step ? "active" : ""}`}>
        <div className="step-index">{String(i + 1).padStart(2, "0")}</div>
        <div>
          <div className="step-name">{s}</div>
          <div className="step-caption">{i < step ? "complete" : i === step ? "active module" : "queued"}</div>
        </div>
      </div>)}
    </div>
    <button className="secondary-action" style={{ marginTop: 16 }} onClick={reset}>Back to home</button>
  </aside>;
}

function InspectorPanel({ mode, profile, lufs, useRef_, stems }) {
  const heights = [42, 77, 58, 91, 64, 35, 82, 54, 70, 46, 88, 61];
  return <aside className="inspector-panel">
    <div className="eyebrow" style={{ marginBottom: 10 }}>Analysis bus</div>
    <h3 className="inspector-title">Auralis engine</h3>
    <div className="mini-spectrum">
      {heights.map((h, i) => <i key={i} style={{ "--h": `${h}%` }} />)}
    </div>
    <p className="inspector-copy">
      Local role detection, reference-aware tonal matching, stereo-safe summing,
      true peak control, and downloadable reports.
    </p>
    <div className="result-stack">
      <div className="result-row"><span className="result-label">Mode</span><span className="result-value">{mode}</span></div>
      <div className="result-row"><span className="result-label">Target</span><span className="result-value">{lufs} LUFS</span></div>
      <div className="result-row"><span className="result-label">Sound</span><span className="result-value">{profile ? "armed" : "open"}</span></div>
      {mode === "mix" && <div className="result-row"><span className="result-label">Stems</span><span className="result-value">{stems.length}</span></div>}
      <div className="result-row"><span className="result-label">Reference</span><span className="result-value">{useRef_ ? "yes" : "no"}</span></div>
    </div>
  </aside>;
}

function RolePill({ role }) {
  return <span style={{
    padding: "4px 9px", borderRadius: 999, fontSize: 11, fontWeight: 800,
    background: `${ROLE_COLORS[role] || MUTE}28`, color: ROLE_COLORS[role] || MUTE,
  }}>{role}</span>;
}

export default function App() {
  const [mode, setMode] = useState("home");
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

  const singleRef = useRef();
  const stemsRef = useRef();
  const refInputRef = useRef();

  const card = {
    background: PANEL,
    borderRadius: 24,
    padding: 18,
    border: "1px solid rgba(130,156,210,.18)",
    boxShadow: "0 18px 60px rgba(0,0,0,.28)",
    backdropFilter: "blur(18px)",
  };
  const btn = primary => ({
    width: "100%",
    padding: 15,
    borderRadius: 16,
    border: primary ? "none" : "1px solid rgba(130,156,210,.18)",
    cursor: "pointer",
    fontSize: 15,
    fontWeight: 850,
    marginTop: 12,
    background: primary ? `linear-gradient(135deg,${V},${T} 50%,${PK})` : PANEL2,
    color: primary ? "#031018" : TEXT,
  });

  async function apiJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function createJob(file) {
    const fd = new FormData();
    fd.append("file", file);
    const r = await apiJson(`${API}/upload`, { method: "POST", body: fd });
    setJobId(r.job_id);
    return r.job_id;
  }

  async function onSingleFile(e) {
    const f = e.target.files[0];
    if (!f) return;
    try {
      await createJob(f);
      setStep(1);
    } catch (error) {
      setErr(error.message);
    }
  }

  async function onStemFiles(e) {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    try {
      const r = await apiJson(`${API}/jobs`, { method: "POST" });
      const jid = r.job_id;
      setJobId(jid);
      const uploaded = [];
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const stem = await apiJson(`${API}/upload-stem/${jid}`, { method: "POST", body: fd });
        uploaded.push({ file: f, filename: stem.stem, role: null });
      }
      setStems(uploaded);
      setStep(1);
    } catch (error) {
      setErr(error.message);
    }
  }

  async function onReference(e) {
    const f = e.target.files[0];
    if (!f || !jobId) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const data = await apiJson(`${API}/upload-reference/${jobId}`, { method: "POST", body: fd });
      setRefName(data.reference);
      setUseRef(true);
    } catch (error) {
      setErr(error.message);
    }
  }

  async function startMaster() {
    setStep(2);
    setProg(0);
    setErr(null);
    try {
      await apiJson(`${API}/master`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, profile_id: profile, target_lufs: lufs, use_reference: useRef_ }),
      });
      listenWS();
    } catch (error) {
      setErr(error.message);
      setStep(1);
    }
  }

  async function startMix() {
    setStep(2);
    setProg(0);
    setErr(null);
    try {
      await apiJson(`${API}/mix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId,
          profile_id: profile,
          target_lufs: lufs,
          use_reference: useRef_,
          role_overrides: roleOverrides,
        }),
      });
      listenWS();
    } catch (error) {
      setErr(error.message);
      setStep(1);
    }
  }

  function listenWS() {
    const ws = new WebSocket(`${API.replace("http", "ws")}/ws/jobs/${jobId}`);
    ws.onmessage = message => {
      const d = JSON.parse(message.data);
      if (d.error) {
        setErr(d.error);
        return;
      }
      setStage(d.stage);
      setProg(d.pct);
      if (d.stage === "done") {
        setResult(d.result);
        setTimeout(() => setStep(3), 400);
      }
    };
  }

  function reset() {
    setMode("home");
    setStep(0);
    setJobId(null);
    setProfile(null);
    setStems([]);
    setRoleOverrides({});
    setRefName("");
    setUseRef(false);
    setResult(null);
    setErr(null);
  }

  const steps = mode === "mix" ? ["Stems", "Sound", "Process", "Master"] : ["Upload", "Sound", "Process", "Master"];
  const currentProfile = PROFILES.find(p => p.id === profile);

  return <div className="app-shell">
    <div className="auralis-shell">
      <header className="studio-topbar">
        <div className="brand-lockup">
          <Mark size={38} />
          <div>
            <div className="brand-title">AURALIS</div>
            <div className="brand-subtitle">private AI audio workstation</div>
          </div>
        </div>
        <div className="topbar-spacer" />
        <div className="status-cluster">
          <span className="status-pill ok"><span className="pulse-dot" />local offline</span>
          <span className="status-pill">voice profile safe</span>
          <span className="status-pill">v0.8 studio build</span>
        </div>
      </header>

      {err && <div className="error-banner">{err}</div>}

      {mode === "home" && <section className="home-hero">
        <div className="hero-copy">
          <div className="eyebrow"><span className="pulse-dot" />local-first studio intelligence</div>
          <h1 className="hero-title">Make stems, masters, and vocals feel <span className="gradient-text">record-ready.</span></h1>
          <p className="hero-lede">
            Auralis combines stem-aware mixing, reference mastering, private singing-voice profiles,
            automatic pitch polish, and professional vocal finish in one offline workstation.
          </p>
          <div className="hero-metrics">
            <div className="metric-tile"><div className="metric-value">0</div><div className="metric-label">cloud uploads required</div></div>
            <div className="metric-tile"><div className="metric-value">1-click</div><div className="metric-label">pitch + vocal finish chain</div></div>
            <div className="metric-tile"><div className="metric-value">GPU</div><div className="metric-label">voice profile acceleration</div></div>
          </div>
          <div className="mode-grid">
            <button className="mode-card" style={{ "--accent": T, "--accent-soft": `${T}24` }} onClick={() => { setMode("master"); setStep(0); }}>
              <div className="mode-icon">M</div>
              <h3>Master a finished mix</h3>
              <p>Upload a stereo track, optionally match a reference, and render a controlled master.</p>
            </button>
            <button className="mode-card" style={{ "--accent": V, "--accent-soft": `${V}24` }} onClick={() => { setMode("mix"); setStep(0); }}>
              <div className="mode-icon">S</div>
              <h3>Mix + master from stems</h3>
              <p>Detect vocals, drums, bass, harmony, and other tracks, then balance into a release-ready master.</p>
            </button>
            <button className="mode-card" style={{ "--accent": PK, "--accent-soft": `${PK}24` }} onClick={() => { setMode("voice"); setStep(0); }}>
              <div className="mode-icon">V</div>
              <h3>Sing in my voice</h3>
              <p>Build a private voice profile, convert guide vocals, tune notes, and finish inside the beat.</p>
            </button>
            <button className="mode-card" style={{ "--accent": "#66e8ff", "--accent-soft": "#66e8ff24" }} onClick={() => { setMode("rack"); setStep(0); }}>
              <div className="mode-icon">R</div>
              <h3>Vocal Chain rack</h3>
              <p>Drop any recorded vocal into a Nectar-style module rack: EQ, de-ess, compression, saturation, space.</p>
            </button>
          </div>
        </div>
        <SpectralConsole />
      </section>}

      {mode === "voice" && <main className="voice-stage voice-studio-shell">
        <VoiceStudio API={API} card={card} btn={btn} colors={{ V, T, PK, PANEL2, TEXT, MUTE }} onBack={reset} />
      </main>}

      {mode === "rack" && <main className="voice-stage">
        <VocalRack API={API} onBack={reset} />
      </main>}

      {mode !== "home" && mode !== "voice" && mode !== "rack" && <div className="workbench">
        <WorkflowRail steps={steps} step={step} mode={mode} reset={reset} />
        <main className="main-panel">
          {mode === "master" && step === 0 && <>
            <h2 className="panel-title">Drop your mix.</h2>
            <p className="panel-copy">Upload a finished stereo track. Auralis will analyze loudness, true peak, tone, and headroom.</p>
            <div className="upload-zone" onClick={() => singleRef.current.click()}>
              <div>
                <Mark size={64} />
                <div className="upload-big">Choose stereo mix</div>
                <div className="upload-small">WAV · FLAC · MP3</div>
              </div>
            </div>
            <input ref={singleRef} type="file" accept="audio/*" hidden onChange={onSingleFile} />
          </>}

          {mode === "mix" && step === 0 && <>
            <h2 className="panel-title">Load the session stems.</h2>
            <p className="panel-copy">Select all tracks at once. Auralis labels each stem and builds a balance before mastering.</p>
            <div className="upload-zone" onClick={() => stemsRef.current.click()}>
              <div>
                <Mark size={64} />
                <div className="upload-big">Choose stem files</div>
                <div className="upload-small">Multiple audio files · WAV · FLAC · MP3</div>
              </div>
            </div>
            <input ref={stemsRef} type="file" accept="audio/*" multiple hidden onChange={onStemFiles} />
          </>}

          {step === 1 && <>
            <h2 className="panel-title">Set the sonic target.</h2>
            <p className="panel-copy">
              {mode === "mix" ? `${stems.length} stems loaded. Confirm roles, then choose the finish.` : "Choose how the master should sit against commercial references."}
            </p>

            {mode === "mix" && stems.length > 0 && <div className="stem-list">
              {stems.map((stem, i) => {
                const detected = roleOverrides[stem.filename] || stem.role || "other";
                return <div className="stem-row" key={`${stem.filename}-${i}`}>
                  <RolePill role={detected} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="stem-title">{stem.filename}</div>
                    <div className="role-buttons">
                      {ROLES.map(r => <button key={r}
                        className="role-button"
                        style={{
                          color: detected === r ? ROLE_COLORS[r] : MUTE,
                          borderColor: detected === r ? `${ROLE_COLORS[r]}66` : undefined,
                          background: detected === r ? `${ROLE_COLORS[r]}22` : undefined,
                        }}
                        onClick={() => setRoleOverrides(prev => ({ ...prev, [stem.filename]: r }))}>
                        {r}
                      </button>)}
                    </div>
                  </div>
                </div>;
              })}
            </div>}

            <div className="profile-grid">
              {PROFILES.map(p => <div key={p.id}
                className={`sound-card ${profile === p.id ? "selected" : ""}`}
                onClick={() => { setProfile(p.id); setLufs(p.lufs); }}>
                <b>{p.name}</b>
                <div>{p.desc}</div>
              </div>)}
            </div>

            <div style={{ ...card, marginTop: 14 }}>
              <div className="data-label" style={{ color: MUTE, fontSize: 11, marginBottom: 10 }}>Delivery loudness</div>
              <div className="control-strip">
                {[{ v: -9, l: "Loud" }, { v: -14, l: "Streaming" }, { v: -16, l: "Dynamic" }].map(o =>
                  <button key={o.v} className={`choice-button ${lufs === o.v ? "active" : ""}`} onClick={() => setLufs(o.v)}>
                    {o.l}<div style={{ fontSize: 10, opacity: 0.72 }}>{o.v} LUFS</div>
                  </button>)}
              </div>
            </div>

            <div className="upload-zone" style={{ minHeight: 120, marginTop: 14 }} onClick={() => refInputRef.current.click()}>
              <div>
                <div className="upload-big">{useRef_ ? `Reference armed: ${refName}` : "Optional reference track"}</div>
                <div className="upload-small">{useRef_ ? "Click to replace" : "Use a song you love for Ozone-style tonal matching"}</div>
              </div>
            </div>
            <input ref={refInputRef} type="file" accept="audio/*" hidden onChange={onReference} />

            <button className="primary-action" style={{ marginTop: 16, opacity: profile ? 1 : 0.45 }}
              disabled={!profile} onClick={mode === "mix" ? startMix : startMaster}>
              {mode === "mix" ? "Mix + master my tracks" : "Master my track"}
            </button>
          </>}

          {step === 2 && <div className="process-stage">
            <div>
              <div style={{ filter: `drop-shadow(0 0 24px ${V})` }}><Mark size={104} /></div>
              <h2 className="panel-title" style={{ marginTop: 24 }}>{mode === "mix" ? "Mixing and mastering." : "Mastering."}</h2>
              <div className="eyebrow" style={{ justifyContent: "center", marginTop: 16 }}>{stage || "initializing"}</div>
              <div className="progress-track"><div className="progress-fill" style={{ width: `${prog}%` }} /></div>
              <div className="data-label" style={{ color: MUTE, fontSize: 11 }}>{Math.round(prog)}% · CPU/GPU local chain</div>
            </div>
          </div>}

          {step === 3 && result && <>
            <h2 className="panel-title">{mode === "mix" ? "Mix + master ready." : "Master ready."}</h2>
            <p className="panel-copy">{currentProfile?.name || "Selected profile"} complete. Export the WAV or inspect the generated report.</p>

            {mode === "mix" && result.stem_analyses && <div className="stem-list">
              {result.stem_analyses.map((a, i) => {
                const mp = result.mix_params?.[i] || {};
                return <div className="stem-row" key={i}>
                  <RolePill role={a.role} />
                  <div className="stem-title">{a.path ? a.path.split(/[/\\]/).pop() : ""}</div>
                  <div className="result-value">
                    {mp.gain_db !== undefined ? `${mp.gain_db > 0 ? "+" : ""}${mp.gain_db}dB` : ""}&nbsp;
                    {mp.pan !== undefined ? `pan ${mp.pan > 0 ? "+" : ""}${mp.pan}` : ""}
                  </div>
                </div>;
              })}
            </div>}

            <div className="result-stack">
              <div className="result-row">
                <span className="result-label">Loudness</span>
                <span className="result-value">
                  {result.master_result?.before_lufs ?? result.before_lufs} → {result.master_result?.after_lufs ?? result.after_lufs} LUFS
                </span>
              </div>
              <div className="result-row">
                <span className="result-label">True peak</span>
                <span className="result-value">{result.master_result?.after_peak_db ?? result.after_peak_db} dB</span>
              </div>
              <div className="result-row">
                <span className="result-label">Reference</span>
                <span className="result-value">{result.reference_used ? "matched" : "not used"}</span>
              </div>
            </div>

            <a href={`${API}/download/${jobId}`} className="primary-action" style={{ marginTop: 16 }}>Download WAV</a>
            {mode === "mix" && <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
              <a href={`${API}/download-report/${jobId}`} className="secondary-action">Mix report</a>
              <a href={`${API}/download-session/${jobId}`} className="secondary-action">Session JSON</a>
            </div>}
            <button className="secondary-action" style={{ marginTop: 10 }} onClick={reset}>Start over</button>
          </>}
        </main>
        <InspectorPanel mode={mode} profile={profile} lufs={lufs} useRef_={useRef_} stems={stems} />
      </div>}
    </div>
  </div>;
}
