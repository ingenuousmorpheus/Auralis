import React, { useEffect, useRef, useState } from "react";
import Knob from "./Knob.jsx";

/* Nectar-style vocal chain rack.
   Module ids + parameter names mirror auralis.voice.finish.MODULE_PARAMS —
   ranges are fetched from /voice/rack-modules so GUI and DSP cannot drift. */

const MODULES = [
  { id: "eq", name: "EQ", glyph: "≈", accent: "#66e8ff", params: [
    { key: "highpass_hz", label: "Low Cut", unit: " Hz", decimals: 0, def: 65 },
    { key: "mud_cut_db", label: "Mud", unit: " dB", decimals: 1, bipolar: true, def: 0 },
    { key: "presence_db", label: "Presence", unit: " dB", decimals: 1, bipolar: true, def: 0 },
    { key: "air_db", label: "Air", unit: " dB", decimals: 1, bipolar: true, def: 0 },
  ]},
  { id: "deess", name: "De-ess", glyph: "S", accent: "#46f6bd", params: [
    { key: "deess_db", label: "Amount", unit: " dB", decimals: 1, bipolar: true, def: 0 },
  ]},
  { id: "compressor", name: "Comp", glyph: "◊", accent: "#ffbd73", params: [
    { key: "leveling_threshold_db", label: "Lvl Thresh", unit: " dB", decimals: 1, def: -20 },
    { key: "leveling_ratio", label: "Lvl Ratio", unit: ":1", decimals: 2, def: 1.8 },
    { key: "peak_threshold_db", label: "Pk Thresh", unit: " dB", decimals: 1, def: -14 },
    { key: "peak_ratio", label: "Pk Ratio", unit: ":1", decimals: 2, def: 3 },
  ]},
  { id: "saturation", name: "Saturate", glyph: "∿", accent: "#ff62c8", params: [
    { key: "saturation_drive_db", label: "Drive", unit: " dB", decimals: 2, def: 0.6 },
  ]},
  { id: "dimension", name: "Dimension", glyph: "‖", accent: "#8d70ff", params: [
    { key: "double_mix", label: "Double", unit: "", decimals: 2, def: 0.08 },
  ]},
  { id: "space", name: "Space", glyph: "◠", accent: "#66e8ff", params: [
    { key: "ambience_mix", label: "Ambience", unit: "", decimals: 2, def: 0.1 },
  ]},
  { id: "output", name: "Output", glyph: "▸", accent: "#46f6bd", params: [
    { key: "output_gain_db", label: "Gain", unit: " dB", decimals: 1, bipolar: true, def: 0 },
  ]},
];

const PRESETS = [
  ["natural", "Natural"], ["polished-pop", "Polished Pop"], ["smooth-rnb", "Smooth R&B"],
  ["intimate", "Intimate"], ["forward", "Forward"],
];

// Visual EQ response for the display (log axis), matching the DSP's band centers.
function eqCurveDb(freq, values) {
  const bump = (center, width, gain) => {
    const d = Math.log2(freq / center) / width;
    return gain * Math.exp(-d * d);
  };
  let db = 0;
  const hp = values.highpass_hz ?? 65;
  if (freq < hp * 2) db -= 24 * Math.max(0, Math.log2((hp * 2) / Math.max(freq, 10))) ** 1.4 * 0.35;
  db += bump(280, 0.9, values.mud_cut_db ?? 0);
  db += bump(3200, 0.85, values.presence_db ?? 0);
  db += (values.air_db ?? 0) / (1 + Math.exp(-(Math.log2(freq / 9000)) * 3));
  return db;
}

export default function VocalRack({ API, sourceJobId = null, sourceName = "", onBack = null }) {
  const [ranges, setRanges] = useState(null);
  const [enabled, setEnabled] = useState(Object.fromEntries(MODULES.map(m => [m.id, true])));
  const [values, setValues] = useState({});
  const [touched, setTouched] = useState(false);
  const [selected, setSelected] = useState("eq");
  const [preset, setPreset] = useState("polished-pop");
  const [intensity, setIntensity] = useState(0.75);
  const [vocalFile, setVocalFile] = useState(null);
  const [instrumental, setInstrumental] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [pct, setPct] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [result, setResult] = useState(null);
  const [monitor, setMonitor] = useState("out");
  const [showReasons, setShowReasons] = useState(false);
  const [error, setError] = useState("");

  const vocalInput = useRef();
  const instrumentalInput = useRef();
  const audioRef = useRef();
  const canvasRef = useRef();
  const audioGraph = useRef(null);   // { ctx, analyser } — one per <audio> lifetime
  const rafRef = useRef(0);

  useEffect(() => {
    fetch(`${API}/voice/rack-modules`).then(r => r.json()).then(setRanges).catch(() => {});
  }, [API]);

  const hasSource = Boolean(vocalFile || sourceJobId);

  function setValue(key, v) {
    setTouched(true);
    setValues(prev => ({ ...prev, [key]: v }));
  }

  function togglePower(id) {
    setTouched(true);
    setEnabled(prev => ({ ...prev, [id]: !prev[id] }));
  }

  function moduleState() {
    if (!touched) return null;          // pure assistant render
    const state = {};
    for (const m of MODULES) {
      state[m.id] = { enabled: enabled[m.id] };
      for (const p of m.params) {
        if (values[p.key] !== undefined) state[m.id][p.key] = values[p.key];
      }
    }
    return state;
  }

  async function render() {
    if (!hasSource || busy) return;
    setError(""); setBusy(true); setStage("uploading"); setPct(0); setResult(null);
    stopAnalyser();
    try {
      const form = new FormData();
      form.append("preset", preset);
      form.append("intensity", String(intensity));
      if (vocalFile) form.append("file", vocalFile);
      else form.append("source_job_id", sourceJobId);
      if (instrumental) form.append("instrumental", instrumental);
      const state = moduleState();
      if (state) form.append("modules", JSON.stringify(state));
      const response = await fetch(`${API}/voice/finish`, { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `Render failed (${response.status})`);
      setJobId(data.job_id);
      const ws = new WebSocket(`${API.replace("http", "ws")}/ws/jobs/${data.job_id}`);
      ws.onmessage = event => {
        const d = JSON.parse(event.data);
        setStage(d.stage || ""); setPct(d.pct || 0);
        if (d.stage === "error") { setError(d.error || "Render failed."); setBusy(false); }
        if (d.stage === "done") {
          setBusy(false);
          setResult(d.result);
          // Assistant handoff: knobs snap to what the engine actually rendered.
          if (d.result?.decision) {
            const dec = d.result.decision;
            setValues(prev => {
              const next = { ...prev };
              for (const m of MODULES) for (const p of m.params) {
                if (dec[p.key] !== undefined && dec[p.key] !== null) next[p.key] = dec[p.key];
              }
              return next;
            });
          }
          setMonitor("out");
        }
      };
      ws.onerror = () => { setError("Lost connection to the render worker."); setBusy(false); };
    } catch (e) { setError(e.message); setBusy(false); }
  }

  function reAssist() {
    setTouched(false);
    setValues({});
    setEnabled(Object.fromEntries(MODULES.map(m => [m.id, true])));
  }

  // ── Live spectrum + EQ curve ────────────────────────────────────────────
  function ensureAnalyser() {
    const el = audioRef.current;
    if (!el || audioGraph.current?.el === el) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = ctx.createMediaElementSource(el);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 4096;
      analyser.smoothingTimeConstant = 0.82;
      src.connect(analyser);
      analyser.connect(ctx.destination);
      audioGraph.current = { ctx, analyser, el };
    } catch { /* analyser is decorative; playback still works */ }
  }

  function stopAnalyser() {
    cancelAnimationFrame(rafRef.current);
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const draw = () => {
      rafRef.current = requestAnimationFrame(draw);
      const g = canvas.getContext("2d");
      const { width: W, height: H } = canvas;
      g.clearRect(0, 0, W, H);
      // grid
      g.strokeStyle = "rgba(130,156,210,0.10)";
      g.lineWidth = 1;
      [100, 1000, 10000].forEach(f => {
        const x = ((Math.log10(f) - Math.log10(30)) / (Math.log10(18000) - Math.log10(30))) * W;
        g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
      });
      // live spectrum
      const graph = audioGraph.current;
      if (graph && !audioRef.current?.paused) {
        const bins = new Uint8Array(graph.analyser.frequencyBinCount);
        graph.analyser.getByteFrequencyData(bins);
        const sr = graph.ctx.sampleRate;
        g.beginPath();
        g.moveTo(0, H);
        const N = 96;
        for (let i = 0; i <= N; i++) {
          const f = 30 * Math.pow(18000 / 30, i / N);
          const bin = Math.min(bins.length - 1, Math.round((f / (sr / 2)) * bins.length));
          const x = (i / N) * W;
          const y = H - (bins[bin] / 255) * H * 0.92;
          g.lineTo(x, y);
        }
        g.lineTo(W, H); g.closePath();
        const fill = g.createLinearGradient(0, 0, 0, H);
        fill.addColorStop(0, "rgba(102,232,255,0.45)");
        fill.addColorStop(1, "rgba(141,112,255,0.06)");
        g.fillStyle = fill;
        g.fill();
      }
      // EQ response curve from current knob state
      const eqOn = enabled.eq !== false;
      g.beginPath();
      const N = 128;
      for (let i = 0; i <= N; i++) {
        const f = 30 * Math.pow(18000 / 30, i / N);
        const db = eqOn ? eqCurveDb(f, values) : 0;
        const x = (i / N) * W;
        const y = H / 2 - (db / 12) * (H / 2) * 0.9;
        if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
      }
      g.strokeStyle = eqOn ? "#66e8ff" : "rgba(143,155,180,0.45)";
      g.lineWidth = 2;
      g.stroke();
    };
    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [values, enabled]);

  const monitorSrc = !jobId || !result ? null
    : monitor === "in" ? `${API}/voice/finish/${jobId}/source`
    : monitor === "mix" ? `${API}/voice/finish/${jobId}/preview`
    : `${API}/voice/finish/${jobId}/download`;

  const activeModule = MODULES.find(m => m.id === selected);
  const range = key => {
    for (const m of MODULES) for (const p of m.params) {
      if (p.key === key) {
        const remote = ranges?.[m.id]?.[key];
        return remote ? [remote.min, remote.max] : null;
      }
    }
    return null;
  };
  const fallbackRanges = {
    highpass_hz: [20, 250], mud_cut_db: [-8, 0], presence_db: [-4, 6], air_db: [-4, 6],
    deess_db: [-10, 0], leveling_threshold_db: [-32, -6], leveling_ratio: [1, 6],
    peak_threshold_db: [-26, -2], peak_ratio: [1, 10], saturation_drive_db: [0, 6],
    double_mix: [0, 0.4], ambience_mix: [0, 0.4], output_gain_db: [-8, 8],
  };

  return <div className="rack">
    <div className="rack-chrome">
      <div className="rack-brand">
        {onBack && <button className="rack-back" onClick={onBack}>←</button>}
        <span className="rack-logo">AURALIS</span>
        <span className="rack-product">VOCAL CHAIN</span>
      </div>
      <div className="rack-presets">
        {PRESETS.map(([id, name]) =>
          <button key={id} className={`rack-preset ${preset === id ? "on" : ""}`}
            onClick={() => setPreset(id)}>{name}</button>)}
      </div>
      <div className="rack-intensity">
        <Knob label="Assist" value={intensity} min={0} max={1} defaultValue={0.75}
          decimals={2} size={50} accent="#ff62c8" onChange={setIntensity} />
      </div>
    </div>

    {error && <div className="rack-error">{error}</div>}

    <div className="rack-display">
      <canvas ref={canvasRef} width={860} height={190} className="rack-canvas" />
      <div className="rack-display-legend">
        <span>30</span><span>100</span><span>1k</span><span>10k</span><span>Hz</span>
      </div>
      {busy && <div className="rack-render-veil">
        <div className="rack-render-stage">{stage || "rendering"}</div>
        <div className="rack-render-track"><div style={{ width: `${pct}%` }} /></div>
      </div>}
    </div>

    <div className="rack-strip">
      {MODULES.map(m => <div key={m.id}
        className={`rack-module ${selected === m.id ? "selected" : ""} ${enabled[m.id] ? "" : "off"}`}
        style={{ "--maccent": m.accent }}
        onClick={() => setSelected(m.id)}>
        <button className="rack-power" title={enabled[m.id] ? "Bypass module" : "Enable module"}
          onClick={event => { event.stopPropagation(); togglePower(m.id); }}>
          <span className="rack-led" />
        </button>
        <div className="rack-module-glyph">{m.glyph}</div>
        <div className="rack-module-name">{m.name}</div>
      </div>)}
    </div>

    <div className="rack-detail" style={{ "--maccent": activeModule.accent }}>
      <div className="rack-detail-head">
        <b>{activeModule.name}</b>
        <span>{enabled[activeModule.id] ? "active" : "bypassed"}</span>
      </div>
      <div className="rack-knobs">
        {activeModule.params.map(p => {
          const [lo, hi] = range(p.key) || fallbackRanges[p.key];
          return <Knob key={p.key} label={p.label} unit={p.unit} decimals={p.decimals}
            bipolar={p.bipolar} min={lo} max={hi} defaultValue={p.def}
            value={values[p.key] ?? p.def} accent={activeModule.accent}
            disabled={!enabled[activeModule.id]}
            onChange={v => setValue(p.key, v)} />;
        })}
      </div>
      <div className="rack-detail-hint">
        {touched
          ? "Manual mode — your knob settings override the assistant on the next render."
          : "Assistant mode — the engine analyzes the vocal and sets every module for you."}
        {touched && <button className="rack-reassist" onClick={reAssist}>Re-run Assistant</button>}
      </div>
    </div>

    <div className="rack-io">
      <div className="rack-io-slot" onClick={() => vocalInput.current.click()}>
        <div className="rack-io-label">Vocal in</div>
        <div className={`rack-io-value ${vocalFile || sourceJobId ? "set" : ""}`}>
          {vocalFile ? vocalFile.name : sourceJobId ? (sourceName || "converted vocal") : "drop / choose a vocal"}
        </div>
      </div>
      <input ref={vocalInput} type="file" accept="audio/*" hidden
        onChange={e => setVocalFile(e.target.files[0] || null)} />
      <div className="rack-io-slot" onClick={() => instrumentalInput.current.click()}>
        <div className="rack-io-label">Instrumental (sidechain)</div>
        <div className={`rack-io-value ${instrumental ? "set" : ""}`}>
          {instrumental ? instrumental.name : "optional — enables Mix monitor + placement"}
        </div>
      </div>
      <input ref={instrumentalInput} type="file" accept="audio/*" hidden
        onChange={e => setInstrumental(e.target.files[0] || null)} />
      <button className="rack-render" disabled={!hasSource || busy} onClick={render}>
        {busy ? "Rendering…" : result ? "Re-Render" : "Analyze + Render"}
      </button>
    </div>

    {result && <div className="rack-transport">
      <div className="rack-ab">
        {[["in", "IN"], ["out", "OUT"], ...(result.preview_path ? [["mix", "MIX"]] : [])].map(([id, name]) =>
          <button key={id} className={`rack-ab-button ${monitor === id ? "on" : ""}`}
            onClick={() => setMonitor(id)}>{name}</button>)}
      </div>
      <audio ref={audioRef} controls crossOrigin="anonymous" src={monitorSrc}
        onPlay={() => { ensureAnalyser(); audioGraph.current?.ctx.resume(); }}
        className="rack-audio" />
      <a className="rack-download" href={`${API}/voice/finish/${jobId}/download`}>⬇ WAV</a>
      <a className="rack-download alt" href={`${API}/voice/finish/${jobId}/report`}>report</a>
    </div>}

    {result?.decision?.reasons?.length > 0 && <div className="rack-reasons">
      <button className="rack-reasons-toggle" onClick={() => setShowReasons(v => !v)}>
        {showReasons ? "Hide" : "Show"} engine decisions ({result.decision.reasons.length})
      </button>
      {showReasons && result.decision.reasons.map(reason =>
        <div key={reason} className="rack-reason">• {reason}</div>)}
    </div>}
  </div>;
}
