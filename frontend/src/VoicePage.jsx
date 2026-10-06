import React, { useEffect, useMemo, useRef, useState } from "react";
import "./VoicePage.css";
import VoiceCapture, { TakeRecorder } from "./VoiceCapture.jsx";
import { Badge, Menu, Progress, Segment, Stat, StatusItem, Tabs, ToolCard, WavePlayer, decodePeaks } from "./Lux.jsx";
import { Icon, apiJson, fmtTime } from "./ui.jsx";

/* My Voice, in the approved luxury direction (docs/AURALIS_LUXURY_UI_DESIGN.md):
   selected-voice hero → input/output workbench → voice tools → local status.
   Every action calls the same endpoints as before; this file is the view.
   The classic studio tools (dataset uploads, paired calibration, deep
   training, pitch polish) stay reachable from My voices. */

const NOTE = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const note = m => m == null ? "?" : `${NOTE[Math.round(m) % 12]}${Math.floor(Math.round(m) / 12) - 1}`;
const KIND = { "instant": "Instant voice", "studio-dataset": "Studio dataset", "studio-trained": "Studio trained" };
const MAX_FILES = 5;
const STUDIO_MINUTES = 10;

function load(key, fallback) { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } }
function keep(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } }
function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}
const minutesOf = v => (v?.dataset_duration_seconds || 0) / 60;
const recorded = v => { const m = minutesOf(v); return m >= 1 ? `${m.toFixed(m >= 10 ? 0 : 1)} min` : `${Math.round(v?.dataset_duration_seconds || 0)} s`; };
const range = v => v?.pitch_low_midi != null ? `${note(v.pitch_low_midi)}–${note(v.pitch_high_midi)}` : "—";
const stripExt = name => (name || "vocal").replace(/\.[a-z0-9]+$/i, "");
const capital = s => s ? s[0].toUpperCase() + s.slice(1) : s;

/* ── Voice art and state ──────────────────────────────────────────────── */

const ART = [["#3b2470", "#a03c8f"], ["#24306e", "#5d3aa8"], ["#3a1c4f", "#1e5c78"],
  ["#4a2259", "#6c4fd6"], ["#1f2a5a", "#8a3f9c"], ["#2d1f4f", "#2f6f8a"]];
function artFor(id = "") {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return ART[h % ART.length];
}

function VoiceArt({ voice, size = 120 }) {
  const [a, b] = artFor(voice?.id);
  const initials = (voice?.name || "?").split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  return <div className="vp-art" aria-hidden="true"
    style={{ width: size, height: size, borderRadius: size * 0.22, background: `radial-gradient(120% 120% at 20% 10%, ${b}, ${a} 60%, #0d0b13)` }}>
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="vp-art-wave">
      <path d="M0 20 Q8 4 16 20 T32 20 T48 20 T64 20 T80 20 T100 20" />
      <path d="M0 20 Q10 32 20 20 T40 20 T60 20 T80 20 T100 20" />
    </svg>
    <span style={{ fontSize: size * 0.28 }}>{initials}</span>
    {voice?.created_via === "microphone" && <i>mic</i>}
  </div>;
}

function voiceState(voice, engine) {
  if (!voice) return ["", "No voice yet"];
  if (voice.training_status === "training") return ["busy", "Training"];
  if (engine == null) return ["busy", "Checking"];
  if (!engine.installed) return ["warn", "Engine not installed"];
  return ["ready", "Ready"];
}

function modelLabel(voice) {
  if (!voice) return "";
  if (voice.training_status === "trained") return `Studio model · ${(voice.training_steps || 0).toLocaleString()} steps`;
  return KIND[voice.kind] || voice.kind;
}

/* ── Hero ─────────────────────────────────────────────────────────────── */

function Hero({ API, voice, voices, engine, onSelect, onNew, onImprove, onManage }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = e => { if (!box.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!voice) return <section className="vp-hero lx-glass vp-hero-empty">
    <VoiceArt voice={null} size={128} />
    <div>
      <span className="lx-eyebrow">My Voice</span>
      <h1 className="vp-name">Make your first voice</h1>
      <p className="vp-desc">Sing into the mic for a minute and Auralis saves a private copy of your voice, on this computer only.
        Then any dry vocal can be sung back in it.</p>
      <button className="lx-btn primary big" onClick={onNew}><Icon name="voice" size={18} />Record a voice</button>
    </div>
  </section>;

  const [tone, state] = voiceState(voice, engine);
  const desc = [
    `${KIND[voice.kind] || "Voice"}${voice.singer_name ? ` sung by ${voice.singer_name}` : ""}`,
    voice.created_via === "microphone" ? "recorded on the mic" : "made from uploaded singing",
    voice.dataset_clip_count ? `${voice.dataset_clip_count} phrases learned` : null,
  ].filter(Boolean).join(" · ");
  const tip = voice.readiness_notes?.[0];

  return <section className="vp-hero lx-glass">
    <div className="vp-hero-id">
      <VoiceArt voice={voice} size={148} />
      <div className="vp-hero-copy">
        <div className="vp-hero-badges">
          <span className="lx-eyebrow">Selected voice</span>
          <Badge tone={tone}>{state}</Badge>
        </div>
        <h1 className="vp-name">{voice.name}</h1>
        <div className="vp-hero-badges"><Badge tone="violet" plain>{modelLabel(voice)}</Badge></div>
        <p className="vp-desc">{desc}</p>
        <div className="vp-tags">
          {voice.pitch_low_midi != null && <span className="lx-tag mono">{range(voice)}</span>}
          {voice.paired_calibration_count > 0 && <span className="lx-tag">{voice.paired_calibration_count} paired calibration</span>}
          {voice.take_count > 0 && <span className="lx-tag">{voice.take_count} {voice.take_count === 1 ? "take" : "takes"}</span>}
          {voice.consent_confirmed && <span className="lx-tag">Consent recorded</span>}
        </div>
        <div className="vp-hero-actions" ref={box}>
          <button className="lx-btn" onClick={() => setOpen(v => !v)} aria-expanded={open} aria-haspopup="listbox">
            <Icon name="convert" size={16} />Switch voice</button>
          <button className="lx-btn" onClick={onImprove}><Icon name="sparkle" size={16} />Train / improve</button>
          <button className="lx-btn quiet" onClick={onManage}>Manage voice</button>
          <button className="lx-btn quiet" onClick={onNew}><Icon name="plus" size={16} />New voice</button>
          {open && <div className="lx-menu vp-switch" role="listbox" aria-label="Voices">
            {voices.map(v => <button key={v.id} role="option" aria-selected={v.id === voice.id}
              onClick={() => { onSelect(v.id); setOpen(false); }}>
              <VoiceArt voice={v} size={34} /><span><b>{v.name}</b><small>{modelLabel(v)}</small></span>
              {v.id === voice.id && <Icon name="check" size={16} />}</button>)}
            <hr /><button onClick={() => { setOpen(false); onNew(); }}><Icon name="plus" size={16} />Record a new voice</button>
          </div>}
        </div>
      </div>
    </div>
    <div className="vp-hero-sound">
      <span className="lx-eyebrow">What it sounds like</span>
      <WavePlayer src={`${API}/voice/profiles/${voice.id}/reference`} decode size="large" height={78} bars={150}
        duration={voice.duration_seconds} label={`the sample of ${voice.name}`} />
      <div className="vp-hero-stats">
        <Stat label="Singing learned" value={recorded(voice)} />
        <Stat label="Range" value={range(voice)} />
        <Stat label="Readiness" value={`${voice.readiness_score ?? 0}%`} />
        <Stat label="Sample" value={voice.sample_rate ? `${(voice.sample_rate / 1000).toFixed(1)} kHz` : "—"} />
      </div>
      {tip && <div className="vp-next"><Icon name="sparkle" size={15} /><span><b>Next step · </b>{tip}</span></div>}
    </div>
  </section>;
}

/* ── Output: converted vocals as result cards ─────────────────────────── */

function ResultCard({ API, item, projects, onChange }) {
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
  const [a, b] = artFor(item.profile_id);
  return <article className="vp-result">
    <div className="vp-result-head">
      <div className="vp-result-art" style={{ background: `linear-gradient(140deg, ${b}, ${a})` }} aria-hidden="true"><Icon name="voice" size={18} /></div>
      <div className="vp-result-title">
        <b title={item.input_name}>{stripExt(item.input_name)}</b>
        <span>{[item.profile_name || s.profile_name, KIND[s.model_mode] || s.model_mode, s.quality && `${capital(s.quality)} quality`].filter(Boolean).join(" · ")}</span>
      </div>
      <span className="vp-result-when">{ago(item.created_at)}</span>
    </div>
    <WavePlayer src={`${base}/audio?which=${which}`} peaks={peaks?.length ? peaks : null} duration={item.duration_seconds}
      label={`${which === "input" ? "the original of" : ""} ${stripExt(item.input_name)}`} />
    <div className="vp-result-tools">
      {item.has_input && <Segment label="A/B" value={which} onChange={setWhich} items={[["output", "Converted"], ["input", "Original"]]} />}
      {item.duration_seconds ? <span className="lx-tag mono">{fmtTime(item.duration_seconds)}</span> : null}
      {s.semitone_shift ? <span className="lx-tag mono">{s.semitone_shift > 0 ? "+" : ""}{s.semitone_shift} st</span> : null}
      <span style={{ flexGrow: 1 }} />
      <button className="lx-icon-btn" aria-pressed={item.rating === 1} onClick={() => rate(1)}
        aria-label={item.rating === 1 ? "Remove from favourites" : "Favourite"} title="Favourite"><Icon name="heart" size={18} /></button>
      <a className="lx-icon-btn" href={`${base}/audio`} download aria-label="Download" title="Download"><Icon name="download" size={18} /></a>
      <Menu label="More actions">
        <button data-close onClick={() => rate(-1)}><Icon name="thumbDown" size={16} />{item.rating === -1 ? "Clear “not right”" : "Mark as not right"}</button>
        {projects.length > 0 && <><hr /><div className="vp-menu-project">
          <select className="lx-select" value={target} onChange={e => setTarget(e.target.value)} aria-label="Project">
            <option value="">Save to project…</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button className="lx-btn small" disabled={!target} onClick={toProject}>Save</button>
        </div></>}
        <hr />
        <button className="danger" data-close onClick={remove}><Icon name="trash" size={16} />Delete take</button>
      </Menu>
    </div>
    {item.rating === -1 && <small className="vp-result-note">Marked as not right</small>}
    {msg && <small className="vp-result-note" role="status">{msg}</small>}
  </article>;
}

function useProjects(API) {
  const [projects, setProjects] = useState([]);
  useEffect(() => { apiJson(`${API}/projects`).then(l => setProjects(l.filter(p => p.status === "open"))).catch(() => {}); }, [API]);
  return projects;
}

function HistoryList({ API, profileId, refresh, onCount }) {
  const [items, setItems] = useState(null);
  const projects = useProjects(API);
  useEffect(() => {
    const q = profileId ? `?profile_id=${profileId}` : "";
    apiJson(`${API}/voice/history${q}`).then(setItems).catch(() => setItems([]));
  }, [API, profileId, refresh]);
  useEffect(() => { if (items) onCount?.(items.length); }, [items]);
  if (items == null) return <div className="lx-empty">Loading your takes…</div>;
  if (!items.length) return <div className="lx-empty vp-output-empty">
    <Icon name="wave" size={34} /><b>No converted vocals yet</b>
    Converted vocals appear here, with their original for A/B, and stay after you close Auralis.</div>;
  return <div className="vp-results">
    {items.map(it => <ResultCard key={it.id} API={API} item={it} projects={projects}
      onChange={next => setItems(list => next ? list.map(x => x.id === it.id ? { ...x, ...next } : x) : list.filter(x => x.id !== it.id))} />)}
  </div>;
}

/* ── Input: files waiting to convert ──────────────────────────────────── */

function InputRow({ file, onRemove }) {
  const [info, setInfo] = useState(null);
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  useEffect(() => { let live = true; decodePeaks(file, 90).then(r => { if (live) setInfo(r || {}); }); return () => { live = false; }; }, [file]);
  return <li className="vp-input">
    <WavePlayer src={url} peaks={info?.peaks} duration={info?.duration} height={30} bars={70} label={file.name} />
    <div className="vp-input-meta">
      <b title={file.name}>{stripExt(file.name)}</b>
      <span>{info?.duration ? fmtTime(info.duration) : info ? "length unknown" : "reading…"} · {(file.size / 1048576).toFixed(1)} MB</span>
    </div>
    <button className="lx-icon-btn" onClick={onRemove} aria-label={`Remove ${file.name}`}><Icon name="x" size={16} /></button>
  </li>;
}

const QUEUE_LABEL = { queued: ["", "Queued"], done: ["ready", "Complete"], error: ["fail", "Failed"], cancelled: ["", "Cancelled"] };

/* ── Workbench (Convert) ──────────────────────────────────────────────── */

function Convert({ API, voice, engine, onEngine, go }) {
  const [files, setFiles] = useState([]);
  const [quality, setQuality] = useState("studio");
  const [shift, setShift] = useState(0);
  const [queue, setQueue] = useState([]);           // {name, state, pct, error}
  const [refresh, setRefresh] = useState(0);
  const [drag, setDrag] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [source, setSource] = useState("files");          // files | record | library (V4)
  const [guides, setGuides] = useState(null);
  const [guide, setGuide] = useState("");
  const [micTake, setMicTake] = useState(null);
  const [output, setOutput] = useState("mine");
  const [counts, setCounts] = useState({});
  const input = useRef(null);
  const cancelled = useRef(new Set());
  useEffect(() => {
    if (source === "library" && guides == null)
      apiJson(`${API}/voice/library-guides`).then(g => { setGuides(g); if (g[0]) setGuide(g[0].song_id); }).catch(() => setGuides([]));
  }, [source]);
  const running = queue.some(q => q.state === "queued" || q.state === "running");

  const add = list => {
    const picked = Array.from(list);                   // copy now: the input clears its live FileList right after
    setFiles(prev => [...prev, ...picked].slice(0, MAX_FILES));
  };
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
  const useMicTake = () => {
    const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }).replace(":", ".");
    add([new File([micTake.blob], `Mic take ${stamp}.wav`, { type: "audio/wav" })]);
    setMicTake(null);
    setSource("files");
  };
  const fromLibrary = source === "library";
  const canConvert = voice && !running && engine?.installed && (fromLibrary ? !!guide : files.length > 0);
  const who = voice?.name || "a voice";

  return <div className="vp-bench" id="vp-bench">
    <section className="lx-glass vp-pane" aria-labelledby="vp-input-h">
      <header className="vp-pane-head">
        <h2 className="lx-h2" id="vp-input-h">Input</h2>
        <Tabs label="Input source" value={source} onChange={setSource}
          items={[["files", "Audio files", files.length || null], ["record", "Record"], ["library", "My Music"]]} />
      </header>
      {engine && !engine.installed && <div className="vp-alert note">
        The local voice engine (Seed-VC) isn't installed. It runs in its own folder and downloads about 3 GB once.
        <div><button className="lx-btn small" style={{ marginTop: 8 }} onClick={install} disabled={installing}>{installing ? "Installing… (this can take a long time)" : "Install voice engine"}</button></div></div>}

      {source === "files" && <>
        <div className={`vp-drop ${drag ? "drag" : ""}`} onClick={() => input.current?.click()} role="button" tabIndex={0}
          onKeyDown={e => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
          onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
          aria-label={`Add or drop up to ${MAX_FILES} dry vocal files`}>
          <span className="vp-drop-icon" aria-hidden="true"><Icon name="upload" size={26} /></span>
          <b>Add or drop audio files here</b>
          <span>Up to {MAX_FILES} dry solo vocals · WAV, FLAC, MP3, AIFF, OGG</span>
          <span className="vp-drop-hint">No beat, reverb or harmonies works best</span>
          <input ref={input} type="file" multiple accept=".wav,.flac,.mp3,.aif,.aiff,.ogg" hidden onChange={e => { add(e.target.files); e.target.value = ""; }} />
        </div>
        {files.length > 0 && <>
          <div className="vp-subhead"><span className="lx-eyebrow">Ready to convert · {files.length}/{MAX_FILES}</span>
            <button className="lx-btn quiet small" onClick={() => setFiles([])}>Clear</button></div>
          <ul className="vp-inputs">{files.map((f, i) => <InputRow key={`${f.name}-${f.size}-${i}`} file={f}
            onRemove={() => setFiles(l => l.filter((_, k) => k !== i))} />)}</ul>
        </>}
      </>}

      {source === "record" && <div className="vp-record">
        <p className="lx-muted">Sing or rap a guide line into the mic. It's added to your inputs and converted to {who}.
          Headphones on if music is playing.</p>
        <TakeRecorder prompts={false} minSeconds={1} onTake={setMicTake} label="Record a guide vocal" />
        {micTake && <button className="lx-btn primary" onClick={useMicTake} disabled={files.length >= MAX_FILES}>
          <Icon name="plus" size={16} />Add this take to the inputs</button>}
      </div>}

      {fromLibrary && <div className="vp-library">
        <p className="lx-muted">Songs in My Music with a separated lead-vocal stem. The stem is only read; your catalog is never changed.</p>
        {guides == null ? <div className="lx-empty">Loading…</div> : !guides.length ? <div className="lx-empty">No song in My Music has a separated lead vocal.</div>
          : <select className="lx-select" value={guide} onChange={e => setGuide(e.target.value)} aria-label="Song">
            {guides.map(g => <option key={g.song_id} value={g.song_id}>{g.title}{g.key ? ` · ${g.key}` : ""}{g.vocal_range ? ` · ${g.vocal_range}` : ""}</option>)}
          </select>}
        {guides?.length > 0 && <span className="lx-muted vp-small">{guides.length} songs with a lead-vocal stem</span>}
      </div>}

      <div className="vp-settings">
        <div className="vp-setting">
          <span className="lx-eyebrow">Quality</span>
          <Segment label="Quality" value={quality} onChange={setQuality} items={[["fast", "Fast"], ["studio", "Studio"], ["ultra", "Ultra"]]} />
        </div>
        <label className="vp-setting">
          <span className="lx-eyebrow">Pitch shift · <b className="vp-shift">{shift > 0 ? "+" : ""}{shift} st</b></span>
          <input className="lx-range" type="range" min={-12} max={12} value={shift} onChange={e => setShift(+e.target.value)} />
        </label>
      </div>

      <button className="lx-btn primary big vp-convert" disabled={!canConvert}
        onClick={fromLibrary ? convertLibrary : convert}>
        <Icon name="convert" size={18} />
        {running ? "Converting…" : fromLibrary ? `Convert this lead vocal to ${who}`
          : source === "record" && !files.length ? "Record a take, then add it"
          : !files.length ? "Add vocals to convert"
          : `Convert ${files.length} ${files.length === 1 ? "file" : "files"} to ${who}`}</button>

      {queue.length > 0 && <ul className="vp-queue" aria-label="Conversion queue">{queue.map((q, i) => {
        const [tone, label] = q.state === "running" ? ["busy", capital(q.stage) || "Working"] : QUEUE_LABEL[q.state] || ["", q.state];
        return <li key={i} data-state={q.state}>
          <div className="vp-queue-row">
            <span className="vp-queue-name" title={q.name}>{stripExt(q.name)}</span>
            <Badge tone={tone}>{label}{q.state === "running" ? ` · ${Math.round(q.pct || 0)}%` : ""}</Badge>
            {q.state === "queued" && <button className="lx-icon-btn" aria-label={`Cancel ${q.name}`}
              onClick={() => { cancelled.current.add(i); setQueue(list => list.map((x, k) => k === i ? { ...x, state: "cancelled" } : x)); }}>
              <Icon name="x" size={14} /></button>}
          </div>
          {(q.state === "running" || q.state === "done" || q.state === "error") &&
            <Progress pct={q.state === "running" ? q.pct || 0 : 100} state={q.state === "done" ? "done" : q.state === "error" ? "fail" : ""} />}
          {q.state === "error" && <small className="vp-queue-error">{q.error}</small>}
        </li>;
      })}</ul>}
    </section>

    <section className="lx-glass vp-pane" aria-labelledby="vp-output-h">
      <header className="vp-pane-head">
        <h2 className="lx-h2" id="vp-output-h">Output</h2>
        <Tabs label="Output" value={output} onChange={setOutput}
          items={[["mine", "Converted vocals", voice ? counts.mine ?? null : null], ["all", "All history", counts.all ?? null]]} />
      </header>
      {output === "mine" && (voice ? <HistoryList API={API} profileId={voice.id} refresh={refresh}
        onCount={n => setCounts(c => ({ ...c, mine: n }))} /> : <div className="lx-empty">Select or record a voice first.</div>)}
      {output === "all" && <HistoryList API={API} refresh={refresh} onCount={n => setCounts(c => ({ ...c, all: n }))} />}
      <footer className="vp-pane-foot">
        <span>Full songs with doubles, harmonies and ad-libs are sung in Create and kept as editable stems in Projects.</span>
        <span className="vp-foot-links">
          <button className="lx-btn quiet small" onClick={() => go?.("create")}>Create</button>
          <button className="lx-btn quiet small" onClick={() => go?.("projects")}>Projects</button>
        </span>
      </footer>
    </section>
  </div>;
}

/* ── My voices ────────────────────────────────────────────────────────── */

function VoiceCard({ API, voice, selected, engine, onSelect, onChanged, onRecordMore }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(voice.name);
  const [train, setTrain] = useState(null);
  const minutes = minutesOf(voice);
  const canTrain = engine?.installed && minutes >= STUDIO_MINUTES && voice.training_status !== "training";
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
  const [tone, state] = voiceState(voice, engine);
  const trained = voice.training_status === "trained";

  return <div className="lx-glass vp-card" data-selected={selected}>
    <div className="vp-card-top">
      <VoiceArt voice={voice} size={72} />
      <div style={{ minWidth: 0, flexGrow: 1 }}>
        {renaming ? <input className="lx-input" value={name} autoFocus onChange={e => setName(e.target.value)} onBlur={rename}
          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { setName(voice.name); setRenaming(false); } }} aria-label="Voice name" />
          : <div className="vp-card-name">{voice.name}</div>}
        <div className="vp-card-sub">
          {modelLabel(voice)}{voice.singer_name ? ` · ${voice.singer_name}` : ""} · {voice.created_via === "microphone" ? "mic" : "upload"}
          {voice.created_at ? ` · ${new Date(voice.created_at).toLocaleDateString()}` : ""}</div>
        <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Badge tone={tone}>{state}</Badge>{selected && <Badge tone="violet" plain>In use</Badge>}
        </div>
      </div>
      <Menu label={`More for ${voice.name}`}>
        <button data-close onClick={() => setRenaming(true)}><Icon name="edit" size={16} />Rename</button>
        <hr /><button className="danger" data-close onClick={remove}><Icon name="trash" size={16} />Delete voice</button>
      </Menu>
    </div>
    <div className="vp-card-stats">
      <Stat label="Singing" value={recorded(voice)} />
      <Stat label="Range" value={range(voice)} />
      <Stat label="Readiness" value={`${voice.readiness_score ?? 0}%`} />
      <Stat label="Takes" value={voice.take_count || "—"} />
    </div>
    <div className="vp-card-train">
      <div className="vp-card-train-head">
        <span className="lx-eyebrow">{trained ? "Studio model" : "Studio training"}</span>
        <span className="vp-small lx-muted">{trained ? `${(voice.training_steps || 0).toLocaleString()} steps trained`
          : `${Math.min(minutes, STUDIO_MINUTES).toFixed(1)} / ${STUDIO_MINUTES} min of singing`}</span>
      </div>
      <Progress pct={trained ? 100 : Math.min(100, minutes / STUDIO_MINUTES * 100)} state={trained ? "done" : ""} />
      <div className="vp-small lx-muted">
        {trained ? "Trained on this voice's own singing." : minutes >= STUDIO_MINUTES ? "Enough singing to train a studio model."
          : `Works now as an instant voice. ${Math.max(0, STUDIO_MINUTES - minutes).toFixed(1)} more minutes of singing unlocks studio training.`}</div>
    </div>
    {voice.readiness_notes?.length > 0 && <ul className="vp-notes" aria-label="How to make it stronger">
      {voice.readiness_notes.slice(0, 3).map((n, i) => <li key={i}>{n}</li>)}</ul>}
    {train && <div className="vp-small" style={{ color: train.error ? "var(--lx-danger)" : "var(--lx-cyan)" }}>
      {train.error || `Training: ${train.stage} · ${Math.round(train.pct || 0)}%`}</div>}
    <WavePlayer src={`${API}/voice/profiles/${voice.id}/reference`} duration={voice.duration_seconds} height={30} label={`the sample of ${voice.name}`} />
    {voice.consent_at && <div className="vp-small" style={{ color: "var(--lx-dim)" }}>Consent recorded {new Date(voice.consent_at).toLocaleString()}{voice.consent_clip ? " · spoken clip kept" : ""}</div>}
    <div className="vp-card-actions">
      <button className="lx-btn primary small" onClick={onSelect} disabled={selected}>{selected ? "Selected" : "Use this voice"}</button>
      <button className="lx-btn small" onClick={onRecordMore}><Icon name="voice" size={15} />Add more takes</button>
      {canTrain && <button className="lx-btn small" onClick={startTraining} disabled={!!train && !train.error && train.stage !== "done"}>
        {trained ? "Retrain studio model" : "Train studio model"}</button>}
    </div>
  </div>;
}

/* ── Local status ─────────────────────────────────────────────────────── */

function SystemStatus({ API, engine, go }) {
  const [models, setModels] = useState(null);
  useEffect(() => { apiJson(`${API}/models`).then(setModels).catch(() => setModels({})); }, [API]);
  const seed = models?.models?.find(m => m.id === "seed-vc");
  const gpu = models?.gpu;
  const free = models?.free_commit_gb;
  return <section className="lx-glass lx-status vp-status" aria-label="Local system">
    <StatusItem icon="voice" tone={engine == null ? "" : engine.installed ? "ready" : "warn"} title="Voice engine"
      detail={engine == null ? "checking…" : engine.installed ? "Ready" : "Not installed"} />
    {gpu ? <StatusItem icon="chip" tone={gpu.free_gb >= (seed?.vram_gb ?? 6) ? "ready" : "warn"} title="Graphics"
      detail={`${gpu.name.replace(/^NVIDIA GeForce /, "")} · ${gpu.free_gb} of ${gpu.total_gb} GB free`} />
      : models && <StatusItem icon="chip" title="Graphics" detail="not detected" />}
    {free != null && <StatusItem icon="memory" tone={free >= (seed?.min_commit_gb ?? 6) ? "ready" : "warn"} title="Memory"
      detail={free >= (seed?.min_commit_gb ?? 6) ? `${free} GB free` : `${free} GB free · close other apps before converting`} />}
    <StatusItem icon="shield" tone="ready" title="Local · Private" detail="Your audio never leaves this computer" />
    <button className="lx-btn quiet small vp-status-link" onClick={() => go?.("studio")}>Engine details</button>
  </section>;
}

/* ── Page ─────────────────────────────────────────────────────────────── */

export default function VoicePage({ API, classic, go }) {
  const [voices, setVoices] = useState([]);
  const [selected, setSelected] = useState(() => load("auralis.voice", ""));
  const [tab, setTab] = useState("convert");
  const [engine, setEngine] = useState(null);
  const [recordMore, setRecordMore] = useState(null);
  const [saved, setSaved] = useState(null);
  const [showClassic, setShowClassic] = useState(false);
  const classicRef = useRef(null);

  const refresh = () => apiJson(`${API}/voice/profiles`).then(setVoices).catch(() => setVoices([]));
  const refreshEngine = () => apiJson(`${API}/voice/provider`).then(setEngine).catch(() => setEngine({ installed: false }));
  useEffect(() => { refresh(); refreshEngine(); }, [API]);

  // Selection precedence: an explicit remembered choice wins. If it no longer
  // exists (first run, deleted voice, cleared browser storage), prefer the
  // strongest ready personal instrument instead of whichever profile happens
  // to be first in the API list. Persist the fallback so every Auralis voice
  // surface sees a stable choice on the next visit.
  const voice = useMemo(() => voices.find(v => v.id === selected)
    || voices.find(v => v.training_status === "trained")
    || voices.find(v => v.kind === "studio-dataset")
    || voices[0] || null, [voices, selected]);
  useEffect(() => {
    if (voice && voice.id !== selected) {
      setSelected(voice.id);
      keep("auralis.voice", voice.id);
    }
  }, [voice?.id, selected]);
  const select = id => { setSelected(id); keep("auralis.voice", id); };
  const scrollTo = id => requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }));

  const onSaved = (profile, take) => {
    setSaved({ profile, take, added: !!recordMore });
    setRecordMore(null);
    refresh();
    select(profile.id);
    setTab("voices");
  };
  const newVoice = () => { setRecordMore(null); setTab("new"); };
  const openPitchTools = () => { setTab("voices"); setShowClassic(true); requestAnimationFrame(() => classicRef.current?.scrollIntoView({ behavior: "smooth" })); };

  return <div className="vp lx-atmosphere">
    <header className="vp-top">
      <div>
        <span className="lx-eyebrow">My Voice</span>
        <div className="vp-tagline">Your voice. Your music. Your studio.</div>
      </div>
      <div className="vp-top-badges"><Badge tone="ready">Local</Badge><Badge tone="violet">Private</Badge></div>
    </header>

    <Hero API={API} voice={voice} voices={voices} engine={engine} onSelect={select} onNew={newVoice}
      onImprove={() => { setTab("voices"); scrollTo("vp-tabs"); }} onManage={() => { setTab("voices"); scrollTo("vp-tabs"); }} />

    <div className="vp-tabbar" id="vp-tabs">
      <Tabs large label="My Voice" value={tab} onChange={id => { setTab(id); if (id !== "new") setRecordMore(null); }}
        items={[["convert", "Convert"], ["voices", "My voices", voices.length || null], ["new", recordMore ? `Add takes · ${recordMore.name}` : "New voice"]]} />
    </div>

    {tab === "convert" && <Convert API={API} voice={voice} engine={engine} onEngine={refreshEngine} go={go} />}

    {tab === "voices" && <div className="vp-voices">
      {saved && <div className="vp-alert ok" role="status">
        {saved.added ? `Added the take to ${saved.profile.name}.` : `Saved “${saved.profile.name}”.`} Range {note(saved.profile.pitch_low_midi)}–{note(saved.profile.pitch_high_midi)},
        {" "}{Math.round(saved.profile.dataset_duration_seconds)} s of singing, readiness {saved.profile.readiness_score}%. It's selected and ready in Convert.
        <button className="lx-icon-btn" style={{ marginLeft: 8, width: 28, height: 28 }} onClick={() => setSaved(null)} aria-label="Dismiss"><Icon name="x" size={14} /></button></div>}
      {!voices.length && <div className="lx-glass lx-empty">No voices yet. <button className="lx-btn primary" onClick={newVoice}>Record a voice</button></div>}
      <div className="vp-cards">
        {voices.map(v => <VoiceCard key={v.id} API={API} voice={v} selected={v.id === voice?.id} engine={engine}
          onSelect={() => select(v.id)} onRecordMore={() => { setRecordMore(v); setTab("new"); }}
          onChanged={next => { if (next) setVoices(l => l.map(x => x.id === v.id ? next : x)); else refresh(); }} />)}
        <button className="lx-glass vp-card vp-card-new" onClick={newVoice}>
          <span aria-hidden="true"><Icon name="plus" size={30} /></span>Record a new voice
          <small>A minute of singing on the mic, with the singer's consent</small></button>
      </div>
      {classic && <div className="lx-glass vp-classic" ref={classicRef}>
        <button className="vp-details-btn" aria-expanded={showClassic} onClick={() => setShowClassic(v => !v)}>
          {showClassic ? "−" : "+"} Studio tools: upload datasets, paired calibration, deep training, pitch polish</button>
        {showClassic && <div style={{ marginTop: 12 }}>{classic}</div>}
      </div>}
    </div>}

    {tab === "new" && <VoiceCapture API={API} addTo={recordMore} onSaved={onSaved}
      onCancel={() => { setRecordMore(null); setTab(voices.length ? "voices" : "convert"); }} />}

    <section className="vp-tools" aria-labelledby="vp-tools-h">
      <h2 className="lx-h2" id="vp-tools-h">Voice tools</h2>
      <div className="vp-tool-grid">
        <ToolCard icon="convert" title="Voice conversion" text="Turn any dry vocal into the selected voice, one file at a time."
          action={tab === "convert" ? "Above" : "Open"} current={tab === "convert"} onClick={() => { setTab("convert"); scrollTo("vp-tabs"); }} />
        <ToolCard icon="pitch" title="Pitch & key" text="Shift by semitones while converting, or tune a take to its key with Pitch Polish."
          action="Pitch Polish" onClick={openPitchTools} />
        <ToolCard icon="layers" title="Vocal doubles" text="Tight left and right doubles under your lead, sung in your voice."
          action="In Create" onClick={() => go?.("create")} />
        <ToolCard icon="harmony" title="Harmonies" text="High and low parts that follow the song's chords and stay inside your range."
          action="In Create" onClick={() => go?.("create")} />
        <ToolCard icon="sparkle" title="Ad-libs" text="Ad-libs between phrases, levelled to the song's era."
          action="In Create" onClick={() => go?.("create")} />
        <ToolCard icon="chain" title="Vocal chain" text="Finish a vocal: tone, compression, de-essing and space."
          action="Open" onClick={() => go?.("rack")} />
      </div>
    </section>

    <SystemStatus API={API} engine={engine} go={go} />
  </div>;
}
