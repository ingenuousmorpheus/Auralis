import React, { useEffect, useRef, useState } from "react";
import { listMics, startRecording } from "./recorder.js";
import { apiJson } from "./ui.jsx";

/* "New voice": a friend sings into the mic and Auralis saves their voice.
   1 Who's singing (name + consent, optional spoken consent clip)
   2 Record one take, following the prompts, with a live level meter
   3 Check the take (level, room noise, singing time) and save the voice.
   Also used as "Record more" for an existing voice (addTo = profile). */

const PROMPTS = [
  { title: "Warm up", text: "Hum or sing a few easy notes in the middle of your voice.", secs: 10 },
  { title: "Hold notes", text: "Hold an open “ahh” on a low, a middle and a high note, about 3 seconds each.", secs: 15 },
  { title: "Slide", text: "Slide slowly from your lowest comfortable note to your highest and back.", secs: 10 },
  { title: "Sing a song", text: "Sing a verse and a chorus: your own lyrics, a freestyle, or something you love. Sing it like you mean it.", secs: 45 },
  { title: "Soft and strong", text: "Sing a line softly, then the same line with power.", secs: 15 },
  { title: "Your style", text: "Runs, falsetto, ad-libs: whatever makes your voice yours.", secs: 20 },
];
const TOTAL = PROMPTS.reduce((n, p) => n + p.secs, 0);
const QUALITY = { great: ["Great take", "var(--signal)"], good: ["Good take", "var(--signal)"],
  usable: ["Usable take", "var(--gold-light)"], retake: ["Record again", "var(--warn)"] };

function fmt(s) { return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; }

function Meter({ level }) {
  const db = level ? 20 * Math.log10(Math.max(level.peak, 1e-6)) : -60;
  const pct = Math.max(0, Math.min(100, (db + 60) / 60 * 100));
  const color = db > -1 ? "var(--warn)" : db > -12 ? "var(--gold)" : "var(--signal)";
  return <div aria-label={`Input level ${Math.round(db)} dB`} role="meter" aria-valuemin={-60} aria-valuemax={0} aria-valuenow={Math.round(db)}>
    <div style={{ height: 10, borderRadius: 5, background: "var(--edge)", overflow: "hidden" }}>
      <div style={{ width: `${pct}%`, height: "100%", background: color, transition: "width 60ms linear" }} /></div>
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--steel)", marginTop: 4 }}>
      <span>{level ? `${Math.round(db)} dB` : "—"}</span>
      <span>{db > -1 ? "Too loud: back off or lower the gain" : db < -40 && level ? "Quiet: move closer" : "Aim for the gold zone on loud notes"}</span>
    </div>
  </div>;
}

function Wave({ peaks, height = 44 }) {
  if (!peaks?.length) return null;
  const w = peaks.length;
  return <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height }} aria-hidden="true">
    {peaks.map((p, i) => <rect key={i} x={i} y={(height - Math.max(1, p * height)) / 2} width={0.8} height={Math.max(1, p * height)} fill="var(--gold)" opacity={0.8} />)}
  </svg>;
}

/* One recorder with meter, timer, prompts and playback. */
function TakeRecorder({ deviceId, prompts = true, minSeconds = 15, onTake, label = "Record" }) {
  const [rec, setRec] = useState(null);
  const [level, setLevel] = useState(null);
  const [take, setTake] = useState(null);
  const [error, setError] = useState("");
  const url = useRef(null);
  useEffect(() => () => { rec?.cancel(); if (url.current) URL.revokeObjectURL(url.current); }, [rec]);

  const start = async () => {
    setError(""); setTake(null); onTake(null);
    try {
      setRec(await startRecording({ deviceId, onLevel: setLevel }));
    } catch (e) {
      setError(e.name === "NotAllowedError" ? "Microphone access was blocked. Allow the microphone for this page and try again."
        : e.message || "Could not open the microphone.");
    }
  };
  const stop = async () => {
    const r = rec; setRec(null);
    const t = await r.stop();
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = URL.createObjectURL(t.blob);
    const max = Math.max(...t.peaks, 1e-6);
    const full = { ...t, url: url.current, peaks: t.peaks.filter((_, i) => i % Math.ceil(t.peaks.length / 400 || 1) === 0).map(p => p / max) };
    setTake(full); onTake(full); setLevel(null);
  };
  const secs = level?.seconds ?? 0;
  let at = 0, current = 0;
  PROMPTS.forEach((p, i) => { if (secs >= at) current = i; at += p.secs; });

  return <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
    {error && <div role="alert" className="vp-alert warn">{error}</div>}
    {rec && <>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span className="vp-rec-dot" aria-hidden="true" />
        <span className="au-mono" style={{ fontSize: 28 }}>{fmt(secs)}</span>
        {prompts && <span style={{ fontSize: 12, color: "var(--steel)" }}>{secs < minSeconds ? `keep going: at least ${minSeconds} s` : secs < TOTAL ? `about ${fmt(TOTAL)} makes a strong voice` : "great length"}</span>}
      </div>
      <Meter level={level} />
      {level?.clipped && <div className="vp-alert warn">Clipping detected. Lower the mic gain or step back, then record again.</div>}
    </>}
    {prompts && rec && <ol className="vp-prompts">
      {PROMPTS.map((p, i) => <li key={p.title} data-state={i < current ? "done" : i === current ? "now" : "next"}>
        <b>{p.title}</b> <span>{p.text}</span></li>)}
    </ol>}
    {take && !rec && <div className="vp-take">
      <Wave peaks={take.peaks} />
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <audio controls src={take.url} style={{ flexGrow: 1, minWidth: 200 }} aria-label="Play the take" />
        <span className="au-mono" style={{ fontSize: 12, color: "var(--steel)" }}>{fmt(take.seconds)} · {Math.round(take.sampleRate / 1000)} kHz</span>
      </div>
    </div>}
    <div style={{ display: "flex", gap: 8 }}>
      {!rec && <button className="au-btn gold" onClick={start}><span className="vp-rec-dot small" aria-hidden="true" />{take ? "Record again" : label}</button>}
      {rec && <button className="au-btn light" onClick={stop} disabled={secs < 1}>Stop</button>}
      {rec && <button className="au-btn" onClick={() => { rec.cancel(); setRec(null); setLevel(null); }}>Cancel</button>}
    </div>
  </div>;
}

function TakeCheck({ report }) {
  if (!report) return null;
  const [label, color] = QUALITY[report.quality] || QUALITY.usable;
  return <div className="vp-panel" style={{ borderColor: color }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <b style={{ color }}>{label}</b>
      <span className="au-chip mono">{report.singing_seconds}s singing</span>
      <span className="au-chip mono">level {report.singing_level_dbfs} dB</span>
      <span className="au-chip mono">room {report.snr_db} dB below</span>
      {report.clipping_percent > 0 && <span className="au-chip mono" style={{ color: "var(--warn)" }}>clipping {report.clipping_percent}%</span>}
    </div>
    {report.issues.map((t, i) => <div key={i} style={{ fontSize: 13, color: "var(--warn)", marginTop: 6 }}>{t}</div>)}
    {report.tips.map((t, i) => <div key={i} style={{ fontSize: 13, color: "var(--steel)", marginTop: 4 }}>{t}</div>)}
    {report.usable && <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 6 }}>
      The voice's sample will come from {report.reference_start.toFixed(1)}–{report.reference_end.toFixed(1)} s, the steadiest stretch of singing.</div>}
  </div>;
}

export default function VoiceCapture({ API, addTo = null, onSaved, onCancel }) {
  const [mics, setMics] = useState([]);
  const [mic, setMic] = useState("");
  const [name, setName] = useState("");
  const [singer, setSinger] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentClip, setConsentClip] = useState(null);
  const [take, setTake] = useState(null);
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { listMics().then(setMics).catch(() => {}); }, []);
  useEffect(() => { setReport(null); }, [take, file]);

  const audioBlob = () => take ? take.blob : file;
  const check = async () => {
    setBusy("checking"); setError("");
    try {
      const form = new FormData();
      form.append("file", audioBlob(), take ? "take.wav" : file.name);
      setReport(await apiJson(`${API}/voice/takes/check`, { method: "POST", body: form }));
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("saving"); setError("");
    try {
      const form = new FormData();
      form.append("file", audioBlob(), take ? "take.wav" : file.name);
      let out;
      if (addTo) {
        out = await apiJson(`${API}/voice/profiles/${addTo.id}/takes`, { method: "POST", body: form });
      } else {
        form.append("name", name.trim());
        form.append("singer_name", singer.trim());
        form.append("consent_confirmed", String(consent));
        if (consentClip) form.append("consent_clip", consentClip.blob, "consent.wav");
        out = await apiJson(`${API}/voice/profiles/from-take`, { method: "POST", body: form });
      }
      onSaved?.(out.profile, out.take);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const who = singer.trim() || "the singer";
  const ready = addTo || (name.trim() && consent);
  const hasAudio = !!(take || file);

  return <div className="vp-capture">
    {!addTo && <section className="vp-panel">
      <div className="vp-step"><span>1</span>Who's singing?</div>
      <div className="vp-grid2">
        <label className="vp-field"><span className="au-caption">Voice name</span>
          <input className="au-input" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Jay's voice" maxLength={64} /></label>
        <label className="vp-field"><span className="au-caption">Singer</span>
          <input className="au-input" value={singer} onChange={e => setSinger(e.target.value)} placeholder="Who is singing" maxLength={64} /></label>
      </div>
      <label className="vp-consent">
        <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
        <span>{singer.trim() ? `${singer.trim()} is here, ` : "The singer is here, "}agrees to Auralis saving a private copy of their voice, and knows it stays on this computer and can be deleted any time.</span>
      </label>
      <details className="vp-details">
        <summary>Optional: record {who} saying they agree</summary>
        <p style={{ fontSize: 13, color: "var(--steel)" }}>Have them say: <i>“I'm {singer.trim() || "(name)"}, and I agree to Auralis making a private voice from my singing.”</i> The clip is kept with the voice as a record and is never used to train it.</p>
        <TakeRecorder deviceId={mic} prompts={false} minSeconds={2} onTake={setConsentClip} label="Record consent" />
      </details>
    </section>}

    <section className="vp-panel" aria-disabled={!ready}>
      <div className="vp-step"><span>{addTo ? 1 : 2}</span>{addTo ? `Record more singing for ${addTo.name}` : "Sing into the mic"}</div>
      <p style={{ fontSize: 13, color: "var(--steel)", margin: "0 0 10px" }}>
        One take, dry: no beat, no reverb, one voice. Headphones on if music is playing. A minute works; three minutes or more is better.</p>
      {mics.length > 1 && <label className="vp-field" style={{ maxWidth: 360, marginBottom: 10 }}><span className="au-caption">Microphone</span>
        <select className="au-input" value={mic} onChange={e => setMic(e.target.value)}>
          <option value="">Default microphone</option>
          {mics.map(m => <option key={m.deviceId} value={m.deviceId}>{m.label || "Microphone"}</option>)}
        </select></label>}
      {ready ? <TakeRecorder deviceId={mic} onTake={t => { setTake(t); if (t) setFile(null); }} label="Start recording" />
        : <div style={{ fontSize: 13, color: "var(--steel)" }}>Name the voice and confirm consent first.</div>}
      <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 10 }}>
        Or use a recording: <input type="file" accept=".wav,.flac,.aif,.aiff,.ogg,.mp3" disabled={!ready}
          onChange={e => { const f = e.target.files?.[0]; setFile(f || null); if (f) setTake(null); }} aria-label="Choose a recording" />
      </div>
    </section>

    <section className="vp-panel">
      <div className="vp-step"><span>{addTo ? 2 : 3}</span>Check and save</div>
      <TakeCheck report={report} />
      {error && <div role="alert" className="vp-alert warn" style={{ marginTop: 10 }}>{error}</div>}
      <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        <button className="au-btn" onClick={check} disabled={!hasAudio || !!busy}>{busy === "checking" ? "Checking…" : "Check the take"}</button>
        <button className="au-btn gold" onClick={save} disabled={!hasAudio || !ready || !!busy || (report && !report.usable)}>
          {busy === "saving" ? "Analysing and saving…" : addTo ? "Add to this voice" : "Save voice"}</button>
        {onCancel && <button className="au-btn" onClick={onCancel} disabled={!!busy}>Cancel</button>}
      </div>
      {busy === "saving" && <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 8 }}>
        Finding the best sample, splitting phrases and measuring the range. This takes a few seconds per minute of singing.</div>}
    </section>
  </div>;
}

export { Wave };
