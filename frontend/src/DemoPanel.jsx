import React, { useEffect, useRef, useState } from "react";
import { startRecording } from "./recorder.js";
import { apiJson } from "./ui.jsx";

/* Demo → song (AU-13): hum, sing or play the idea (or choose a voice memo);
   Auralis finds its tempo, key and melody, harmonizes it, and builds the song
   around it, keeping your melody note for note as the chorus (or a verse). */

export default function DemoPanel({ API, prompt, lyrics, useDna, useVoice, era, onBlueprint, onClose }) {
  const [rec, setRec] = useState(null);
  const [secs, setSecs] = useState(0);
  const [take, setTake] = useState(null);
  const [file, setFile] = useState(null);
  const [role, setRole] = useState("chorus");
  const [tempo, setTempo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = useRef(null);
  useEffect(() => () => { rec?.cancel(); if (url.current) URL.revokeObjectURL(url.current); }, [rec]);

  const record = async () => {
    setError(""); setTake(null); setFile(null);
    try { setRec(await startRecording({ onLevel: l => setSecs(l.seconds) })); }
    catch (e) { setError(e.name === "NotAllowedError" ? "Microphone access was blocked for this page." : e.message); }
  };
  const stop = async () => {
    const r = rec; setRec(null);
    const t = await r.stop();
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = URL.createObjectURL(t.blob);
    setTake({ ...t, url: url.current });
  };
  const build = async () => {
    setBusy(true); setError("");
    try {
      const form = new FormData();
      form.append("file", take ? take.blob : file, take ? "demo.wav" : file.name);
      form.append("prompt", prompt || ""); form.append("lyrics", lyrics || "");
      form.append("role", role); form.append("use_dna", String(useDna)); form.append("use_voice", String(useVoice));
      if (tempo) form.append("tempo", tempo);
      if (era) form.append("era", era);
      onBlueprint(await apiJson(`${API}/composer/demo`, { method: "POST", body: form }));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return <div className="au-card au-console" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div className="au-label">Build from my demo</div>
      <button className="bp-icon" onClick={onClose} aria-label="Close demo panel">✕</button>
    </div>
    <div style={{ fontSize: 12, color: "var(--steel)", lineHeight: 1.5 }}>
      Sing or hum the idea (a hook works best), or choose a voice memo. Auralis keeps your melody and builds the song around it.</div>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      {!rec && <button className="au-btn" onClick={record}><span className="vp-rec-dot small" aria-hidden="true" />{take ? "Record again" : "Record"}</button>}
      {rec && <><button className="au-btn light" onClick={stop}>Stop</button>
        <span className="au-mono" style={{ fontSize: 14 }}>{Math.floor(secs / 60)}:{String(Math.floor(secs % 60)).padStart(2, "0")}</span></>}
      <label style={{ fontSize: 12, color: "var(--steel)" }}>or <input type="file" accept=".wav,.flac,.ogg,.mp3"
        onChange={e => { setFile(e.target.files?.[0] || null); setTake(null); }} aria-label="Choose a demo file" /></label>
    </div>
    {take && <audio controls src={take.url} style={{ width: "100%" }} aria-label="Your demo" />}
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <span className="au-caption">It's the</span>
      <div className="au-segment" role="tablist" aria-label="Demo becomes">
        {[["chorus", "Chorus"], ["verse", "Verse"], ["bridge", "Bridge"]].map(([r, l]) =>
          <button key={r} role="tab" aria-selected={role === r} onClick={() => setRole(r)}>{l}</button>)}
      </div>
      <input className="au-input" style={{ width: 110, height: 34 }} placeholder="BPM (auto)" inputMode="numeric"
        value={tempo} onChange={e => setTempo(e.target.value.replace(/[^0-9.]/g, ""))} aria-label="Tempo (optional)" />
    </div>
    {error && <div role="alert" className="bp-alert warn">{error}</div>}
    <button className="au-btn gold" onClick={build} disabled={busy || !(take || file)}>{busy ? "Listening to your demo…" : "Build the song around it"}</button>
  </div>;
}
