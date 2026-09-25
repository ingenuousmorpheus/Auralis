import React, { useEffect, useMemo, useRef, useState } from "react";
import "./VoicePage.css";
import VoiceCapture, { Wave } from "./VoiceCapture.jsx";
import { apiJson, coverColor } from "./ui.jsx";

/* My Voice (Kits-style layout inside the Auralis console).
   Hero with the selected voice → tabs: Convert (input | output), My voices
   (saved voice cards), New voice (record a friend on the mic), History.
   The classic studio tools (dataset uploads, paired calibration, pitch polish)
   stay reachable from My voices. */

const NOTE = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const note = m => m == null ? "?" : `${NOTE[Math.round(m) % 12]}${Math.floor(Math.round(m) / 12) - 1}`;
const KIND = { "instant": "Instant voice", "studio-dataset": "Studio dataset", "studio-trained": "Studio trained" };
const MAX_FILES = 5;

function load(key, fallback) { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } }
function keep(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } }
function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

function VoiceTile({ voice, size = 120 }) {
  const initials = (voice?.name || "?").split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  return <div className="vp-tile" style={{ width: size, height: size, background: coverColor(voice?.id || "") }} aria-hidden="true">
    <span style={{ fontSize: size * 0.3 }}>{initials}</span>
    {voice?.created_via === "microphone" && <i title="Recorded on the mic">mic</i>}
  </div>;
}

function Hero({ API, voice, voices, onSelect, onNew, engine }) {
  const [open, setOpen] = useState(false);
  return <div className="vp-hero">
    <VoiceTile voice={voice} />
    <div style={{ minWidth: 0, flexGrow: 1 }}>
      <div className="au-caption">{voice ? "Selected voice" : "No voice yet"}</div>
      <h1 className="au-title au-shine" style={{ fontSize: 26, margin: "4px 0" }}>{voice ? voice.name : "Select a voice"}</h1>
      {voice ? <div className="vp-meta">
        <span className="au-chip holo">{KIND[voice.kind] || voice.kind}</span>
        {voice.pitch_low_midi != null && <span className="au-chip mono">{note(voice.pitch_low_midi)}–{note(voice.pitch_high_midi)}</span>}
        <span className="au-chip mono">readiness {voice.readiness_score}%</span>
        {voice.singer_name && <span className="au-chip">sung by {voice.singer_name}</span>}
        {voice.paired_calibration_count > 0 && <span className="au-chip">{voice.paired_calibration_count} paired</span>}
      </div> : <div style={{ fontSize: 14, color: "var(--steel)" }}>Record a voice on the mic, or pick one you saved.</div>}
      <div style={{ fontSize: 12, color: engine?.installed ? "var(--signal)" : "var(--gold-light)", marginTop: 8 }}>
        {engine == null ? "Checking the voice engine…" : engine.installed ? "Voice engine ready (local)" : "Voice engine not installed: install it from Convert"}</div>
    </div>
    <div className="vp-hero-actions">
      {voice && <audio controls preload="none" src={`${API}/voice/profiles/${voice.id}/reference`} aria-label={`Sample of ${voice.name}`} />}
      <div style={{ display: "flex", gap: 8, position: "relative" }}>
        <button className="au-btn" onClick={() => setOpen(v => !v)} aria-expanded={open} disabled={!voices.length}>Switch voice</button>
        <button className="au-btn gold" onClick={onNew}>+ New voice</button>
        {open && <div className="vp-switch" role="listbox" aria-label="Voices">
          {voices.map(v => <button key={v.id} role="option" aria-selected={v.id === voice?.id}
            onClick={() => { onSelect(v.id); setOpen(false); }}>
            <VoiceTile voice={v} size={34} /><span><b>{v.name}</b><br /><small>{KIND[v.kind] || v.kind}</small></span></button>)}
        </div>}
      </div>
    </div>
  </div>;
}

/* ── Output rows (conversion history) ─────────────────────────────────── */

function TakeRow({ API, item, projects, onChange, showVoice }) {
  const [peaks, setPeaks] = useState(null);
  const [which, setWhich] = useState("output");
  const [target, setTarget] = useState("");
  const [msg, setMsg] = useState("");
  const base = `${API}/voice/history/${item.profile_id}/${item.id}`;
  useEffect(() => { apiJson(`${base}/peaks`).then(setPeaks).catch(() => setPeaks([])); }, [base]);
  const rate = async r => onChange(await apiJson(base, { method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating: item.rating === r ? 0 : r }) }));
  const toProject = async () => {
    if (!target) return;
    try {
      await apiJson(`${base}/to-project`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: target }) });
      setMsg("Saved to project");
    } catch (e) { setMsg(e.message); }
  };
  const remove = async () => {
    if (!window.confirm("Delete this take? The converted audio is removed from this computer.")) return;
    await apiJson(base, { method: "DELETE" });
    onChange(null);
  };
  const s = item.settings || {};
  return <div className="vp-row">
    <div className="vp-row-head">
      <span className="vp-row-title">{item.input_name || "vocal"} → {showVoice ? item.profile_name : "converted"}</span>
      <span style={{ fontSize: 12, color: "var(--steel)" }}>{ago(item.created_at)}</span>
    </div>
    <Wave peaks={peaks} height={38} />
    <div className="vp-row-tools">
      <audio controls preload="none" src={`${base}/audio?which=${which}`} key={which} aria-label={`Play ${which}`} />
      {item.has_input && <div className="au-segment" role="tablist" aria-label="A/B">
        <button role="tab" aria-selected={which === "output"} onClick={() => setWhich("output")}>Voice</button>
        <button role="tab" aria-selected={which === "input"} onClick={() => setWhich("input")}>Original</button>
      </div>}
      <a className="bp-icon" href={`${base}/audio`} download title="Download">⤓</a>
      <button className="bp-icon" aria-pressed={item.rating === 1} onClick={() => rate(1)} title="Sounds good">👍</button>
      <button className="bp-icon" aria-pressed={item.rating === -1} onClick={() => rate(-1)} title="Not right">👎</button>
      <button className="bp-icon" onClick={remove} title="Delete take">✕</button>
    </div>
    <div className="vp-row-foot">
      <span>{[s.quality, s.semitone_shift ? `${s.semitone_shift > 0 ? "+" : ""}${s.semitone_shift} st` : null, item.duration_seconds && `${item.duration_seconds}s`].filter(Boolean).join(" · ")}</span>
      {projects.length > 0 && <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <select className="au-input" style={{ height: 30 }} value={target} onChange={e => setTarget(e.target.value)} aria-label="Project">
          <option value="">Save to project…</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button className="bp-icon" disabled={!target} onClick={toProject}>Save</button>
        {msg && <small>{msg}</small>}
      </span>}
    </div>
  </div>;
}

function useProjects(API) {
  const [projects, setProjects] = useState([]);
  useEffect(() => { apiJson(`${API}/projects`).then(l => setProjects(l.filter(p => p.status === "open"))).catch(() => {}); }, [API]);
  return projects;
}

function HistoryList({ API, profileId, refresh, showVoice }) {
  const [items, setItems] = useState(null);
  const projects = useProjects(API);
  useEffect(() => {
    const q = profileId ? `?profile_id=${profileId}` : "";
    apiJson(`${API}/voice/history${q}`).then(setItems).catch(() => setItems([]));
  }, [API, profileId, refresh]);
  if (items == null) return <div className="vp-empty">Loading…</div>;
  if (!items.length) return <div className="vp-empty">Converted vocals appear here and stay after you close Auralis.</div>;
  return <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    {items.map(it => <TakeRow key={it.id} API={API} item={it} projects={projects} showVoice={showVoice}
      onChange={next => setItems(list => next ? list.map(x => x.id === it.id ? { ...x, ...next } : x) : list.filter(x => x.id !== it.id))} />)}
  </div>;
}

/* ── Convert ──────────────────────────────────────────────────────────── */

function Convert({ API, voice, engine, onEngine }) {
  const [files, setFiles] = useState([]);
  const [quality, setQuality] = useState("studio");
  const [shift, setShift] = useState(0);
  const [queue, setQueue] = useState([]);           // {name, state, pct, error}
  const [refresh, setRefresh] = useState(0);
  const [drag, setDrag] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [source, setSource] = useState("files");          // files | library (V4)
  const [guides, setGuides] = useState(null);
  const [guide, setGuide] = useState("");
  const input = useRef(null);
  const cancelled = useRef(new Set());
  useEffect(() => {
    if (source === "library" && guides == null)
      apiJson(`${API}/voice/library-guides`).then(g => { setGuides(g); if (g[0]) setGuide(g[0].song_id); }).catch(() => setGuides([]));
  }, [source]);
  const running = queue.some(q => q.state === "queued" || q.state === "running");

  const add = list => setFiles(prev => [...prev, ...Array.from(list)].slice(0, MAX_FILES));
  const wait = async (jobId, i) => {
    for (;;) {
      const st = await apiJson(`${API}/jobs/${jobId}`);
      setQueue(q => q.map((x, k) => k === i ? { ...x, state: "running", stage: st.stage, pct: st.pct } : x));
      if (st.stage === "done") return;
      if (st.stage === "error") throw new Error(st.error || "Conversion failed.");
      await new Promise(r => setTimeout(r, 900));
    }
  };
  const convert = async () => {
    const batch = files;
    setFiles([]);
    setQueue(batch.map(f => ({ name: f.name, state: "queued", pct: 0 })));
    cancelled.current = new Set();
    for (let i = 0; i < batch.length; i++) {          // one at a time: the engine never runs twice
      if (cancelled.current.has(i)) continue;          // removed from the queue before its turn
      try {
        const form = new FormData();
        form.append("profile_id", voice.id);
        form.append("quality", quality);
        form.append("semitone_shift", String(shift));
        form.append("file", batch[i]);
        const { job_id } = await apiJson(`${API}/voice/convert`, { method: "POST", body: form });
        await wait(job_id, i);
        setQueue(q => q.map((x, k) => k === i ? { ...x, state: "done", pct: 100 } : x));
        setRefresh(r => r + 1);
      } catch (e) {
        setQueue(q => q.map((x, k) => k === i ? { ...x, state: "error", error: e.message } : x));
      }
    }
  };
  const convertLibrary = async () => {
    const g = guides.find(x => x.song_id === guide);
    setQueue([{ name: `${g.title} (lead vocal)`, state: "queued", pct: 0 }]);
    try {
      const { job_id } = await apiJson(`${API}/voice/convert-from-library`, { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: voice.id, song_id: guide, quality, semitone_shift: shift }) });
      await wait(job_id, 0);
      setQueue(q => q.map(x => ({ ...x, state: "done", pct: 100 })));
      setRefresh(r => r + 1);
    } catch (e) { setQueue(q => q.map(x => ({ ...x, state: "error", error: e.message }))); }
  };
  const install = async () => {
    setInstalling(true);
    try { await apiJson(`${API}/voice/provider/install`, { method: "POST" }); onEngine(); }
    catch (e) { alert(e.message); }
    finally { setInstalling(false); }
  };

  return <div className="vp-split">
    <section className="vp-panel">
      <h2 className="vp-h2">Input</h2>
      {engine && !engine.installed && <div className="vp-alert note">
        The local voice engine (Seed-VC) isn't installed. It runs in its own folder and downloads about 3 GB once.
        <div><button className="au-btn" style={{ marginTop: 8 }} onClick={install} disabled={installing}>{installing ? "Installing… (this can take a long time)" : "Install voice engine"}</button></div></div>}
      <div className="au-segment" role="tablist" aria-label="Input" style={{ marginBottom: 12 }}>
        <button role="tab" aria-selected={source === "files"} onClick={() => setSource("files")}>Audio input</button>
        <button role="tab" aria-selected={source === "library"} onClick={() => setSource("library")}>From My Music</button>
      </div>
      {source === "library" && <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: 12, color: "var(--steel)" }}>Songs in My Music with a separated lead-vocal stem. The stem is only read; your catalog is never changed.</div>
        {guides == null ? <div className="vp-empty">Loading…</div> : !guides.length ? <div className="vp-empty">No song in My Music has a separated lead vocal.</div>
          : <select className="au-input" value={guide} onChange={e => setGuide(e.target.value)} aria-label="Song">
            {guides.map(g => <option key={g.song_id} value={g.song_id}>{g.title}{g.key ? ` · ${g.key}` : ""}{g.vocal_range ? ` · ${g.vocal_range}` : ""}</option>)}
          </select>}
      </div>}
      {source === "files" && <><div className={`vp-drop ${drag ? "drag" : ""}`} onClick={() => input.current?.click()} role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
        aria-label={`Add or drop up to ${MAX_FILES} dry vocal files`}>
        <div style={{ fontSize: 28, color: "var(--gold)" }} aria-hidden="true">⇪</div>
        <b>Add or drop up to {MAX_FILES} vocals</b>
        <span>Dry solo vocals work best: no beat, reverb or harmonies.</span>
        <input ref={input} type="file" multiple accept=".wav,.flac,.mp3,.aif,.aiff,.ogg" hidden onChange={e => { add(e.target.files); e.target.value = ""; }} />
      </div>
      {files.length > 0 && <ul className="vp-files">{files.map((f, i) => <li key={i}>
        <span>{f.name}</span><button className="bp-icon" onClick={() => setFiles(l => l.filter((_, k) => k !== i))} aria-label={`Remove ${f.name}`}>✕</button></li>)}</ul>}</>}
      <div className="au-caption" style={{ marginTop: 14 }}>Quality</div>
      <div className="au-segment" role="tablist" aria-label="Quality" style={{ marginTop: 6 }}>
        {[["fast", "Fast"], ["studio", "Studio"], ["ultra", "Ultra"]].map(([q, l]) =>
          <button key={q} role="tab" aria-selected={quality === q} onClick={() => setQuality(q)}>{l}</button>)}
      </div>
      <label className="vp-field" style={{ marginTop: 14 }}>
        <span className="au-caption">Pitch shift · {shift > 0 ? "+" : ""}{shift} semitones</span>
        <input type="range" min={-12} max={12} value={shift} onChange={e => setShift(+e.target.value)} style={{ accentColor: "var(--gold)" }} />
      </label>
      <button className="au-btn gold big" style={{ width: "100%", marginTop: 14 }}
        disabled={!voice || running || !engine?.installed || (source === "files" ? !files.length : !guide)}
        onClick={source === "files" ? convert : convertLibrary}>
        {running ? "Converting…" : source === "library" ? `Convert this lead vocal to ${voice?.name || "a voice"}`
          : !files.length ? "Add vocals to convert"
          : `Convert ${files.length} ${files.length === 1 ? "file" : "files"} to ${voice?.name || "a voice"}`}</button>
      {queue.length > 0 && <ul className="vp-queue" aria-label="Conversion queue">{queue.map((q, i) =>
        <li key={i} data-state={q.state}><span>{q.name}</span>
          <small style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {q.state === "queued" ? "waiting" : q.state === "running" ? `${q.stage || "working"} · ${Math.round(q.pct || 0)}%`
              : q.state === "done" ? "done" : q.state === "cancelled" ? "cancelled" : q.error}
            {q.state === "queued" && <button className="bp-icon" style={{ height: 24, minWidth: 24 }} aria-label={`Cancel ${q.name}`}
              onClick={() => { cancelled.current.add(i); setQueue(list => list.map((x, k) => k === i ? { ...x, state: "cancelled" } : x)); }}>✕</button>}
          </small></li>)}</ul>}
    </section>
    <section className="vp-panel">
      <h2 className="vp-h2">Output</h2>
      {voice ? <HistoryList API={API} profileId={voice.id} refresh={refresh} /> : <div className="vp-empty">Select or record a voice first.</div>}
    </section>
  </div>;
}

/* ── My voices ────────────────────────────────────────────────────────── */

function VoiceCard({ API, voice, selected, engine, onSelect, onChanged, onRecordMore }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(voice.name);
  const [train, setTrain] = useState(null);
  const minutes = (voice.dataset_duration_seconds || 0) / 60;
  const canTrain = engine?.installed && minutes >= 10 && voice.training_status !== "training";
  const rename = async () => {
    setRenaming(false);
    if (name.trim() && name !== voice.name) onChanged(await apiJson(`${API}/voice/profiles/${voice.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() }) }));
  };
  const remove = async () => {
    const typed = window.prompt(`Delete “${voice.name}” for good? Its sample, takes, dataset and any trained model are removed from this computer.\n\nType the voice name to confirm:`);
    if (typed !== voice.name) return;
    await apiJson(`${API}/voice/profiles/${voice.id}`, { method: "DELETE" });
    onChanged(null);
  };
  const startTraining = async () => {
    try {
      const r = await apiJson(`${API}/voice/train`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: voice.id, depth: "studio" }) });
      setTrain({ id: r.job_id, stage: "queued", pct: 0 });
    } catch (e) { setTrain({ error: e.message }); }
  };
  useEffect(() => {
    if (!train?.id || train.stage === "done" || train.stage === "error") return;
    const t = setTimeout(async () => {
      const st = await apiJson(`${API}/jobs/${train.id}`).catch(() => null);
      if (st) setTrain({ id: train.id, stage: st.stage, pct: st.pct, error: st.error });
      if (st?.stage === "done") onChanged(await apiJson(`${API}/voice/profiles`).then(l => l.find(v => v.id === voice.id)));
    }, 2000);
    return () => clearTimeout(t);
  }, [train]);

  return <div className="vp-card" data-selected={selected}>
    <div style={{ display: "flex", gap: 12 }}>
      <VoiceTile voice={voice} size={64} />
      <div style={{ minWidth: 0, flexGrow: 1 }}>
        {renaming ? <input className="au-input" value={name} autoFocus onChange={e => setName(e.target.value)} onBlur={rename}
          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { setName(voice.name); setRenaming(false); } }} aria-label="Voice name" />
          : <div className="vp-card-name">{voice.name}</div>}
        <div style={{ fontSize: 12, color: "var(--steel)" }}>
          {KIND[voice.kind] || voice.kind}{voice.singer_name ? ` · ${voice.singer_name}` : ""} · {voice.created_via === "microphone" ? "mic" : "upload"}
          {voice.created_at ? ` · ${new Date(voice.created_at).toLocaleDateString()}` : ""}</div>
      </div>
    </div>
    <div className="vp-card-stats">
      <div><span className="au-caption">Range</span><b>{voice.pitch_low_midi != null ? `${note(voice.pitch_low_midi)}–${note(voice.pitch_high_midi)}` : "—"}</b></div>
      <div><span className="au-caption">Singing</span><b>{minutes >= 1 ? `${minutes.toFixed(1)} min` : `${Math.round(voice.dataset_duration_seconds || 0)} s`}</b></div>
      <div><span className="au-caption">Readiness</span><b>{voice.readiness_score}%</b></div>
    </div>
    <div className="vp-bar" aria-hidden="true"><div style={{ width: `${Math.min(100, minutes / 10 * 100)}%` }} /></div>
    <div style={{ fontSize: 11, color: "var(--steel)" }}>
      {voice.training_status === "trained" ? `Studio model trained (${voice.training_steps} steps).`
        : minutes >= 10 ? "Enough singing to train a studio model."
          : `Works now as an instant voice. ${Math.max(0, 10 - minutes).toFixed(1)} more minutes of singing unlocks studio training.`}</div>
    {voice.consent_at && <div style={{ fontSize: 11, color: "var(--steel-dim)" }}>Consent recorded {new Date(voice.consent_at).toLocaleString()}{voice.consent_clip ? " · spoken clip kept" : ""}</div>}
    {train && <div style={{ fontSize: 12, color: train.error ? "var(--warn)" : "var(--steel)" }}>{train.error || `Training: ${train.stage} · ${Math.round(train.pct || 0)}%`}</div>}
    <audio controls preload="none" src={`${API}/voice/profiles/${voice.id}/reference`} aria-label={`Sample of ${voice.name}`} style={{ width: "100%" }} />
    <div className="vp-card-actions">
      <button className="au-btn gold" onClick={onSelect} disabled={selected}>{selected ? "Selected" : "Use this voice"}</button>
      <button className="au-btn" onClick={onRecordMore}>Record more</button>
      {canTrain && <button className="au-btn" onClick={startTraining} disabled={!!train && !train.error && train.stage !== "done"}>Train studio model</button>}
      <button className="bp-icon" onClick={() => setRenaming(true)} title="Rename">Rename</button>
      <button className="bp-icon" onClick={remove} title="Delete voice">Delete</button>
    </div>
  </div>;
}

/* ── Page ─────────────────────────────────────────────────────────────── */

export default function VoicePage({ API, classic }) {
  const [voices, setVoices] = useState([]);
  const [selected, setSelected] = useState(() => load("auralis.voice", ""));
  const [tab, setTab] = useState("convert");
  const [engine, setEngine] = useState(null);
  const [recordMore, setRecordMore] = useState(null);
  const [saved, setSaved] = useState(null);
  const [showClassic, setShowClassic] = useState(false);

  const refresh = () => apiJson(`${API}/voice/profiles`).then(setVoices).catch(() => setVoices([]));
  const refreshEngine = () => apiJson(`${API}/voice/provider`).then(setEngine).catch(() => setEngine({ installed: false }));
  useEffect(() => { refresh(); refreshEngine(); }, [API]);

  const voice = useMemo(() => voices.find(v => v.id === selected)
    || voices.find(v => v.training_status === "trained") || voices[0] || null, [voices, selected]);
  const select = id => { setSelected(id); keep("auralis.voice", id); };

  const onSaved = (profile, take) => {
    setSaved({ profile, take, added: !!recordMore });
    setRecordMore(null);
    refresh();
    select(profile.id);
    setTab("voices");
  };

  return <div className="vp">
    <Hero API={API} voice={voice} voices={voices} onSelect={select} onNew={() => { setRecordMore(null); setTab("new"); }} engine={engine} />
    <div className="vp-tabs" role="tablist" aria-label="My Voice">
      {[["convert", "Convert"], ["voices", `My voices${voices.length ? ` · ${voices.length}` : ""}`], ["new", "New voice"], ["history", "History"]].map(([id, label]) =>
        <button key={id} role="tab" aria-selected={tab === id} onClick={() => { setTab(id); if (id !== "new") setRecordMore(null); }}>{label}</button>)}
      <button role="tab" aria-selected={false} disabled title="Coming with vocal production (AU-09)">Harmonies · soon</button>
    </div>

    {tab === "convert" && <Convert API={API} voice={voice} engine={engine} onEngine={refreshEngine} />}

    {tab === "voices" && <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {saved && <div className="vp-alert ok" role="status">
        {saved.added ? `Added the take to ${saved.profile.name}.` : `Saved “${saved.profile.name}”.`} Range {note(saved.profile.pitch_low_midi)}–{note(saved.profile.pitch_high_midi)},
        {" "}{Math.round(saved.profile.dataset_duration_seconds)} s of singing, readiness {saved.profile.readiness_score}%. It's selected and ready in Convert.
        <button className="bp-icon" style={{ marginLeft: 8 }} onClick={() => setSaved(null)} aria-label="Dismiss">✕</button></div>}
      {!voices.length && <div className="vp-empty">No voices yet. <button className="au-btn gold" onClick={() => setTab("new")}>Record a voice</button></div>}
      <div className="vp-cards">
        {voices.map(v => <VoiceCard key={v.id} API={API} voice={v} selected={v.id === voice?.id} engine={engine}
          onSelect={() => select(v.id)} onRecordMore={() => { setRecordMore(v); setTab("new"); }}
          onChanged={next => { if (next) setVoices(l => l.map(x => x.id === v.id ? next : x)); else refresh(); }} />)}
        <button className="vp-card vp-card-new" onClick={() => { setRecordMore(null); setTab("new"); }}>
          <span aria-hidden="true">+</span>Record a new voice</button>
      </div>
      {classic && <div className="vp-panel">
        <button className="vp-details-btn" aria-expanded={showClassic} onClick={() => setShowClassic(v => !v)}>
          {showClassic ? "−" : "+"} Studio tools: upload datasets, paired calibration, deep training, pitch polish</button>
        {showClassic && <div style={{ marginTop: 12 }}>{classic}</div>}
      </div>}
    </div>}

    {tab === "new" && <VoiceCapture API={API} addTo={recordMore} onSaved={onSaved}
      onCancel={() => { setRecordMore(null); setTab(voices.length ? "voices" : "convert"); }} />}

    {tab === "history" && <div className="vp-panel"><h2 className="vp-h2">All conversions</h2><HistoryList API={API} showVoice /></div>}
  </div>;
}
