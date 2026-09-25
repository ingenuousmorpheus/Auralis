import React, { useEffect, useState } from "react";
import "./Blueprint.css";
import SaveToProject from "./SaveToProject.jsx";
import { apiJson, fmtTime } from "./ui.jsx";

/* Song Blueprint (AU-04): the editable plan Create makes before any audio.
   Every edit goes through POST /composer/blueprint/revise, which re-derives
   chord names, timings, energy and vocal registers, so the view never has to
   duplicate music logic. */

const MAJORS = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const MINORS = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B"];
const KEYS = [...MAJORS.map(k => `${k} major`), ...MINORS.map(k => `${k} minor`)];
const TYPES = [["intro", "Intro"], ["verse", "Verse"], ["pre-chorus", "Pre-chorus"], ["chorus", "Chorus"],
  ["bridge", "Bridge"], ["instrumental", "Interlude"], ["outro", "Outro"]];
const ROLE_NAMES = { drums: "Drums", bass: "Bass", keys: "Keys", pad: "Pad", lead_vocal: "Lead vox",
  backing_vocals: "BGVs", fx: "FX", atmos: "Atmos" };
const LEVELS = ["off", "light", "medium", "full"];
const RATES = [[0.5, "½ / bar"], [1, "1 / bar"], [2, "2 / bar"]];
const TYPE_COLOR = { intro: "#3a4252", verse: "#7fe6ff", "pre-chorus": "#9fe8c9", chorus: "#d4af5f",
  bridge: "#b8923f", instrumental: "#8fe9ff", outro: "#3a4252" };

function Why({ lines, open: startOpen = false }) {
  const [open, setOpen] = useState(startOpen);
  if (!lines?.length) return null;
  return <div>
    <button className="bp-why-toggle" aria-expanded={open} onClick={() => setOpen(v => !v)}>{open ? "Hide why" : "Why?"}</button>
    {open && <div className="bp-why"><ul>{lines.map((l, i) => <li key={i}>{l}</li>)}</ul></div>}
  </div>;
}

function EnergyCurve({ bp }) {
  const total = bp.total_bars || 1;
  const w = total * 10;
  return <div className="bp-curve">
    <div className="au-caption" style={{ marginBottom: 8 }}>Energy curve · {bp.total_bars} bars · {fmtTime(bp.duration_seconds)}</div>
    <svg viewBox={`0 0 ${w} 100`} preserveAspectRatio="none" role="img"
      aria-label={`Energy by bar across ${bp.sections.length} sections`}>
      {bp.sections.map(s => {
        const start = (s.start_bar - 1);
        return <g key={s.id}>
          {Array.from({ length: s.bars }, (_, b) => {
            const e = bp.energy_curve[start + b] ?? s.energy;
            return <rect key={b} x={(start + b) * 10 + 1} y={100 - e * 84} width={8} height={e * 84}
              rx={2} fill={TYPE_COLOR[s.type] || "#9aa1ad"} opacity={0.85} />;
          })}
          <line x1={start * 10} x2={start * 10} y1={0} y2={100} stroke="#2d3441" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        </g>;
      })}
    </svg>
    <div style={{ display: "flex", fontSize: 10, color: "var(--steel)", marginTop: 4 }}>
      {bp.sections.map(s => <span key={s.id} style={{ width: `${(s.bars / total) * 100}%`, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "clip" }}>{s.label}</span>)}
    </div>
  </div>;
}

function Section({ s, index, count, options, busy, onChange, onMove, onRemove, onDuplicate, onRegenerate, generators = [] }) {
  const [draft, setDraft] = useState(s.progression.roman.join(" "));
  useEffect(() => setDraft(s.progression.roman.join(" ")), [s.progression.roman.join(" ")]);
  const commitChords = () => { if (draft.trim() !== s.progression.roman.join(" ")) onChange({ progression: draft }); };
  const optIndex = options.findIndex(o => o.roman.join(" ") === s.progression.roman.join(" "));
  const v = s.vocal;
  // first pass of the progression, so a long section shows each chord once
  const shown = s.chords.slice(0, Math.max(s.progression.roman.length, 1));

  return <div className="bp-section" style={{ borderLeft: `3px solid ${TYPE_COLOR[s.type] || "var(--edge)"}` }}>
    <div className="bp-section-head">
      <span className="bp-section-name">{s.label}</span>
      <select aria-label={`${s.label} type`} className="au-input" value={s.type} disabled={busy}
        onChange={e => onChange({ type: e.target.value })}>
        {TYPES.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </select>
      <label className="bp-row">Bars
        <input aria-label={`${s.label} bars`} className="au-input bp-bars" type="number" min={1} max={64} step={1}
          defaultValue={s.bars} key={`bars-${s.bars}`} disabled={busy}
          onBlur={e => { const n = parseInt(e.target.value, 10); if (n && n !== s.bars) onChange({ bars: n }); }}
          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} />
      </label>
      <span className="au-mono" style={{ fontSize: 12, color: "var(--steel)" }}>{fmtTime(s.start_seconds)}</span>
      <div className="bp-tools">
        <button className="bp-icon" aria-label={`Move ${s.label} up`} disabled={busy || index === 0} onClick={() => onMove(-1)}>↑</button>
        <button className="bp-icon" aria-label={`Move ${s.label} down`} disabled={busy || index === count - 1} onClick={() => onMove(1)}>↓</button>
        <button className="bp-icon" aria-label={`Duplicate ${s.label}`} disabled={busy} onClick={onDuplicate}>Copy</button>
        <button className="bp-icon" aria-label={`Remove ${s.label}`} disabled={busy || count === 1} onClick={onRemove}>✕</button>
      </div>
    </div>

    <div className="bp-chords" aria-label={`${s.label} chords`}>
      {shown.map((c, i) => <div key={i} className="bp-chord"><b>{c.chord}</b><span>{c.roman}</span></div>)}
      {s.chords.length > shown.length && <span style={{ alignSelf: "center", fontSize: 12, color: "var(--steel)" }}>
        repeats · {s.chords.length} changes</span>}
    </div>

    <div className="bp-chord-edit">
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="au-caption">Roman numerals</span>
        <input className="au-input" value={draft} disabled={busy} onChange={e => setDraft(e.target.value)}
          onBlur={commitChords} onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }}
          aria-label={`${s.label} Roman numerals`} spellCheck={false} />
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span className="au-caption">Harmony option</span>
        <div style={{ display: "flex", gap: 6 }}>
          <select className="au-input" value={optIndex} disabled={busy || !options.length} aria-label={`${s.label} harmony option`}
            onChange={e => { const o = options[+e.target.value]; if (o) onChange({ progression: o }); }}>
            {optIndex < 0 && <option value={-1}>{s.progression.name || "Your chords"}</option>}
            {options.map((o, i) => <option key={i} value={i}>{o.name} · {o.roman.join(" ")}</option>)}
          </select>
          <button className="bp-icon" disabled={busy || options.length < 2} onClick={onRegenerate}
            title="New chords for every section of this type">New</button>
        </div>
      </label>
    </div>

    <div className="bp-row">
      <label className="bp-row">Chords
        <select className="au-input" style={{ height: 30 }} value={s.chords_per_bar} disabled={busy}
          onChange={e => onChange({ chords_per_bar: +e.target.value })} aria-label={`${s.label} chords per bar`}>
          {RATES.map(([r, l]) => <option key={r} value={r}>{l}</option>)}
        </select>
      </label>
      <label className="bp-row">Energy
        <input type="range" min={0} max={1} step={0.05} defaultValue={s.energy} key={`e-${s.energy}`} disabled={busy}
          aria-label={`${s.label} energy`}
          onPointerUp={e => onChange({ energy: +e.currentTarget.value })}
          onKeyUp={e => onChange({ energy: +e.currentTarget.value })} />
        <span className="au-mono">{Math.round(s.energy * 100)}</span>
      </label>
      {generators.length > 0 && <label className="bp-row">Render with
        <select className="au-input" style={{ height: 30 }} value={s.renderer || "synth"} disabled={busy}
          onChange={e => onChange({ renderer: e.target.value })} aria-label={`${s.label} renderer`}>
          <option value="synth">Auralis synth</option>
          {generators.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select></label>}
      {v && <span>Vocal <b style={{ color: "var(--ivory)" }}>{v.low}–{v.high}</b>, peak <b style={{ color: "var(--gold-light)" }}>{v.peak}</b>
        {v.pattern && <> · {v.pattern}</>}{v.lines > 0 && <> · {v.lines} lyric lines</>}</span>}
    </div>

    <div className="bp-roles" aria-label={`${s.label} arrangement`}>
      {Object.entries(s.arrangement).map(([role, level]) =>
        <button key={role} className="bp-role" data-level={level} disabled={busy}
          title={`${ROLE_NAMES[role] || role}: ${level} (click to change)`}
          aria-label={`${ROLE_NAMES[role] || role} ${level}`}
          onClick={() => onChange({ arrangement: { ...s.arrangement, [role]: LEVELS[(LEVELS.indexOf(level) + 1) % LEVELS.length] } })}>
          {ROLE_NAMES[role] || role}</button>)}
    </div>
    <Why lines={s.why} />
  </div>;
}

function SaveBox({ API, bp, onSaved }) {
  const [projects, setProjects] = useState([]);
  const [target, setTarget] = useState("");
  const [state, setState] = useState("");
  useEffect(() => {
    apiJson(`${API}/projects`).then(list => {
      const open = list.filter(p => p.status === "open");
      setProjects(open);
      setTarget(t => t || (open[0]?.id ?? "new"));
    }).catch(() => setTarget("new"));
  }, [API]);
  const save = async () => {
    setState("saving");
    try {
      let pid = target;
      if (pid === "new") {
        const p = await apiJson(`${API}/projects`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: bp.title || "New song" }) });
        pid = p.id;
        setProjects(list => [p, ...list]);
        setTarget(p.id);
      }
      const saved = await apiJson(`${API}/projects/${pid}/blueprint`, { method: "PUT",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ blueprint: bp }) });
      const name = projects.find(p => p.id === pid)?.name || bp.title;
      setState(`Saved revision ${saved.saved_revision} to “${name}”`);
      onSaved?.(pid);
    } catch (e) { setState(e.message); }
  };
  return <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
    <select className="au-input" value={target} onChange={e => setTarget(e.target.value)} aria-label="Save to project" style={{ height: 38, maxWidth: 220 }}>
      {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      <option value="new">New project: {bp.title}</option>
    </select>
    <button className="au-btn gold" onClick={save} disabled={state === "saving" || !bp.validation?.ok}>Save blueprint</button>
    {state && state !== "saving" && <span role="status" style={{ fontSize: 12, color: state.startsWith("Saved") ? "var(--signal)" : "var(--warn)" }}>
      {state.startsWith("Saved") ? "✓ " : ""}{state}</span>}
  </div>;
}

const STEM_NAMES = { drums: "Drums", bass: "Bass", keys: "Keys", pad: "Pad", fx: "FX", atmosphere: "Atmosphere" };

/* AU-05: render the blueprint with the local instruments, then mix and master
   it with the existing engine. Progress comes from /jobs/{id}. */
function RenderPanel({ API, bp }) {
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [seed, setSeed] = useState(0);
  const renderedRev = status?.result?.blueprint_revision;

  useEffect(() => {
    if (!job) return;
    let stop = false;
    const tick = async () => {
      try {
        const st = await apiJson(`${API}/jobs/${job}`);
        if (stop) return;
        setStatus(st);
        if (st.stage === "error") setError(st.error || "Render failed.");
        if (st.stage !== "done" && st.stage !== "error") setTimeout(tick, 700);
      } catch (e) { if (!stop) setError(e.message); }
    };
    tick();
    return () => { stop = true; };
  }, [job]);

  const start = async (nextSeed = seed) => {
    setError(""); setStatus(null);
    try {
      const r = await apiJson(`${API}/composer/render`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blueprint: bp, seed: nextSeed }) });
      setSeed(nextSeed);
      setJob(r.job_id);
    } catch (e) { setError(e.message); }
  };
  const running = status && status.stage !== "done" && status.stage !== "error";
  const done = status?.stage === "done" ? status.result : null;
  const file = name => `${API}/composer/render/${job}/file/${name}`;

  return <div className="bp-panel" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
      <div>
        <div className="au-caption">Instrumental</div>
        <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 2 }}>Local instruments play the blueprint, then the Auralis mixer and mastering finish it.</div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {done && <button className="au-btn" disabled={running} onClick={() => start(seed + 1)} title="Same blueprint, new performance (melody guide, humanising)">New take</button>}
        <button className="au-btn gold" disabled={running || !bp.validation?.ok} onClick={() => start(seed)}>
          {running ? "Rendering…" : done ? "Render again" : "Render instrumental"}</button>
      </div>
    </div>
    {error && <div role="alert" className="bp-alert warn">{error}</div>}
    {running && <div role="status">
      <div style={{ fontSize: 12, color: "var(--steel)", marginBottom: 6 }}>{status.stage} · {Math.round(status.pct)}%</div>
      <div style={{ height: 6, borderRadius: 3, background: "var(--edge)", overflow: "hidden" }}>
        <div style={{ width: `${status.pct}%`, height: "100%", background: "var(--gold)", transition: "width 0.3s" }} /></div>
    </div>}
    {done && <>
      {renderedRev != null && renderedRev !== bp.revision && <div className="bp-alert note">
        The blueprint changed since this render (revision {renderedRev} → {bp.revision}). Render again to hear the edits.</div>}
      <div style={{ fontSize: 12, color: "var(--steel)" }}>
        {done.tempo} BPM · {done.key} · {fmtTime(done.duration_seconds)} · mastered with <span className="au-mono">{done.profile_id}</span>
        {done.after_lufs != null && <> · {done.after_lufs} LUFS</>} · take {done.seed + 1}</div>
      <audio controls preload="none" src={file("master")} style={{ width: "100%" }} aria-label="Mastered instrumental" />
      {done.atmosphere && <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700 }}>
          Atmosphere · {Object.entries(done.atmosphere.counts).map(([k, n]) => `${n} ${k}`).join(", ")}</summary>
        <ul className="bp-why" style={{ maxHeight: 180, overflowY: "auto", paddingLeft: 16 }}>
          {[...new Map(done.atmosphere.layers.map(l => [l.why.replace(/ on .*$/, ""), l])).values()]
            .map((l, i) => <li key={i}>{l.why.replace(/ on .*$/, "")}</li>)}
        </ul>
      </details>}
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700 }}>Stems, melody guide and MIDI</summary>
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          {Object.keys(done.stems).map(k => <label key={k} style={{ display: "grid", gridTemplateColumns: "90px minmax(0, 1fr)", alignItems: "center", gap: 8, fontSize: 12 }}>
            <span>{STEM_NAMES[k] || k}</span><audio controls preload="none" src={file(k)} style={{ width: "100%", height: 32 }} /></label>)}
          {done.melody_guide_path && <label style={{ display: "grid", gridTemplateColumns: "90px minmax(0, 1fr)", alignItems: "center", gap: 8, fontSize: 12 }}>
            <span title="A plain tone singing the guide melody; not in the instrumental">Melody guide</span>
            <audio controls preload="none" src={file("melody_guide")} style={{ width: "100%", height: 32 }} /></label>}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <a className="au-btn" href={file("master")} download>Download instrumental</a>
            <a className="au-btn" href={file("midi")} download>Download MIDI</a>
          </div>
        </div>
      </details>
      <OriginalityCheck API={API} bp={bp} seed={done.seed} />
      <SaveToProject API={API} jobId={job} label="Save render to project" />
      {renderedRev === bp.revision && <SingPanel API={API} bp={bp} renderJob={job} />}
    </>}
  </div>;
}

/* AU-07/08: the guide singer sings the blueprint melody, a saved voice takes it
   over (Seed-VC), then Pitch Polish, Vocal Finish and a full song mix. */
function SingPanel({ API, bp, renderJob }) {
  const [voices, setVoices] = useState([]);
  const [voice, setVoice] = useState("");
  const [quality, setQuality] = useState("studio");
  const [production, setProduction] = useState("full");
  const [backingDb, setBackingDb] = useState(4);
  const [partLevels, setPartLevels] = useState({});
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    apiJson(`${API}/voice/profiles`).then(list => {
      setVoices(list);
      let saved = "";
      try { saved = localStorage.getItem("auralis.voice") || ""; } catch { /* private mode */ }
      const pick = list.find(v => v.id === saved) || list.find(v => v.training_status === "trained") || list[0];
      if (pick) setVoice(pick.id);
    }).catch(() => {});
  }, [API]);
  useEffect(() => {
    if (!job) return;
    let stop = false;
    const tick = async () => {
      try {
        const st = await apiJson(`${API}/jobs/${job}`);
        if (stop) return;
        setStatus(st);
        if (st.stage === "error") setError(st.error || "Singing failed.");
        if (st.stage !== "done" && st.stage !== "error") setTimeout(tick, 1000);
      } catch (e) { if (!stop) setError(e.message); }
    };
    tick();
    return () => { stop = true; };
  }, [job]);
  const start = async () => {
    setError(""); setStatus(null);
    try {
      const r = await apiJson(`${API}/composer/sing`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blueprint: bp, render_job_id: renderJob, profile_id: voice, quality, production,
          backing_db: backingDb, backing_levels: partLevels }) });
      setJob(r.job_id);
    } catch (e) { setError(e.message); }
  };
  const running = status && status.stage !== "done" && status.stage !== "error";
  const done = status?.stage === "done" ? status.result : null;
  const file = name => `${API}/composer/sing/${job}/file/${name}`;
  const sungLines = bp.sections.some(s => s.lyrics?.length);
  if (!voices.length) return <div className="bp-alert note">Save a voice in My Voice to hear this song sung.</div>;
  return <div className="bp-panel" style={{ display: "flex", flexDirection: "column", gap: 10, borderColor: "rgba(127,230,255,0.35)" }}>
    <div className="au-caption">Sing it in a saved voice</div>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <select className="au-input" value={voice} onChange={e => setVoice(e.target.value)} aria-label="Voice" style={{ height: 38 }}>
        {voices.map(v => <option key={v.id} value={v.id}>{v.name} · {v.training_status === "trained" ? "studio trained" : "instant"}</option>)}
      </select>
      <div className="au-segment" role="tablist" aria-label="Voice quality">
        {[["fast", "Fast"], ["studio", "Studio"], ["ultra", "Ultra"]].map(([q, l]) =>
          <button key={q} role="tab" aria-selected={quality === q} onClick={() => setQuality(q)}>{l}</button>)}
      </div>
      <button className="au-btn gold" onClick={start} disabled={running || !voice}>{running ? "Singing…" : done ? "Sing again" : "Sing it"}</button>
    </div>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <span className="au-caption">Vocals</span>
      <div className="au-segment" role="tablist" aria-label="Vocal production">
        {[["lead", "Lead only"], ["doubles", "Lead + doubles"], ["harmony", "Lead + harmony"], ["full", "Full production"]].map(([p, l]) =>
          <button key={p} role="tab" aria-selected={production === p} onClick={() => setProduction(p)}>{l}</button>)}
      </div>
      <span style={{ fontSize: 11, color: "var(--steel)" }}>each section's BGVs level sets how much it gets</span>
    </div>
    {production !== "lead" && <details>
      <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 700 }}>Backing mix</summary>
      <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
        {[["__stack", "Whole stack"], ...Object.entries({ double_l: "Double (left)", double_r: "Double (right)", harmony_high: "Harmony (high)", harmony_low: "Harmony (low)", adlibs: "Ad-libs" })].map(([k, l]) => {
          const val = k === "__stack" ? backingDb - 4 : (partLevels[k] ?? 0);
          return <label key={k} className="bp-row" style={{ display: "grid", gridTemplateColumns: "120px minmax(0, 1fr) 52px", gap: 8 }}>
            <span>{l}</span>
            <input type="range" min={-12} max={6} step={1} value={val} aria-label={`${l} level`}
              onChange={e => k === "__stack" ? setBackingDb(4 + +e.target.value) : setPartLevels(p => ({ ...p, [k]: +e.target.value }))} />
            <span className="au-mono">{val > 0 ? "+" : ""}{val} dB</span>
          </label>;
        })}
      </div>
    </details>}
    <div style={{ fontSize: 12, color: "var(--steel)" }}>
      The built-in guide singer performs the melody{sungLines ? ", the rhythm of your lyrics and their vowels" : ""}; your voice model supplies the timbre.
      {sungLines && " It doesn't pronounce clear words yet: that needs a lyric-capable singing engine (planned)."} Close big apps first: the voice engine needs memory.</div>
    {error && <div role="alert" className="bp-alert warn">{error}</div>}
    {running && <div role="status">
      <div style={{ fontSize: 12, color: "var(--steel)", marginBottom: 6 }}>{status.stage} · {Math.round(status.pct)}%</div>
      <div style={{ height: 6, borderRadius: 3, background: "var(--edge)", overflow: "hidden" }}>
        <div style={{ width: `${status.pct}%`, height: "100%", background: "var(--holo)", transition: "width 0.3s" }} /></div>
    </div>}
    {done && <>
      {done.parts_why?.length > 0 && <Why lines={done.parts_why} />}
      <div style={{ fontSize: 12, color: "var(--steel)" }}>{done.profile_name} · {done.notes_sung} notes · {done.notes_corrected ?? 0} tuned
        {Object.keys(done.backing_stems || {}).length > 0 && <> · {Object.keys(done.backing_stems).length} backing parts · {done.conversion_calls} engine {done.conversion_calls === 1 ? "run" : "runs"}</>}
        {done.after_lufs != null && <> · song {done.after_lufs} LUFS</>}</div>
      {done.song_master_path && <audio controls preload="none" src={file("song")} style={{ width: "100%" }} aria-label="The finished song" />}
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700 }}>Vocal stages</summary>
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          {[["vocal", "Lead vocal"], ...(done.backing_path ? [["backing", "Backing stack"]] : []),
            ...Object.keys(done.backing_stems || {}).map(k => [k, { double_l: "Double (left)", double_r: "Double (right)",
              harmony_high: "Harmony (high)", harmony_low: "Harmony (low)", adlibs: "Ad-libs" }[k] || k]),
            ["converted", `${done.profile_name} (raw lead)`], ["guide", "Guide singer"]].map(([k, l]) =>
            <label key={k} style={{ display: "grid", gridTemplateColumns: "120px minmax(0, 1fr)", alignItems: "center", gap: 8, fontSize: 12 }}>
              <span>{l}</span><audio controls preload="none" src={file(k)} style={{ width: "100%", height: 32 }} /></label>)}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {done.song_master_path && <a className="au-btn" href={file("song")} download>Download song</a>}
            <a className="au-btn" href={file("vocal")} download>Download vocal</a>
          </div>
        </div>
      </details>
      <SaveToProject API={API} jobId={job} label="Save song to project" />
    </>}
  </div>;
}

/* AU-12: compare the rendered take with your own songs (chords with every song,
   melody with your closest lead vocals). */
function OriginalityCheck({ API, bp, seed }) {
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState(null);
  useEffect(() => { setJob(null); setStatus(null); }, [bp.revision, seed]);
  useEffect(() => {
    if (!job) return;
    let stop = false;
    const tick = async () => {
      const st = await apiJson(`${API}/jobs/${job}`).catch(e => ({ stage: "error", error: e.message }));
      if (stop) return;
      setStatus(st);
      if (st.stage !== "done" && st.stage !== "error") setTimeout(tick, 900);
    };
    tick();
    return () => { stop = true; };
  }, [job]);
  const run = async () => {
    const r = await apiJson(`${API}/composer/similarity`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ blueprint: bp, seed }) }).catch(e => ({ error: e.message }));
    if (r.job_id) setJob(r.job_id); else setStatus({ stage: "error", error: r.error });
  };
  const running = status && status.stage !== "done" && status.stage !== "error";
  return <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <button className="au-btn" onClick={run} disabled={running}>{running ? "Checking…" : "Check originality"}</button>
      <span style={{ fontSize: 12, color: "var(--steel)" }}>{running ? status.stage : "Compares chords with all your songs and the melody with your closest lead vocals."}</span>
    </div>
    {status?.stage === "error" && <div role="alert" className="bp-alert warn">{status.error}</div>}
    {status?.stage === "done" && status.result.checks.map(c => <div key={c.id} className="bp-check">
      <i style={{ color: c.status === "flag" ? "var(--warn)" : c.status === "pass" ? "var(--signal)" : "var(--gold-light)" }}>
        {c.status === "flag" ? "!" : c.status === "pass" ? "✓" : "i"}</i>
      <span><b>{c.label}</b><br /><span style={{ color: "var(--steel)", fontSize: 12 }}>{c.detail}</span></span>
    </div>)}
  </div>;
}

export default function BlueprintView({ API, blueprint, setBlueprint }) {
  const bp = blueprint;
  // installed section generators (none until one is installed; then a per-section choice appears)
  const [generators, setGenerators] = useState([]);
  useEffect(() => {
    apiJson(`${API}/models`).then(st => setGenerators(st.models.filter(m => m.kind === "section_generator" && m.installed)))
      .catch(() => setGenerators([]));
  }, [API]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const post = async (path, body) => {
    setBusy(true);
    try {
      const next = await apiJson(`${API}/composer/blueprint/${path}`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setBlueprint(next);
      setError("");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const revise = changes => post("revise", { blueprint: bp, changes });
  const ids = () => bp.sections.map(s => ({ id: s.id }));
  const editSection = (i, patch) => { const list = ids(); list[i] = { ...list[i], ...patch }; revise({ sections: list }); };
  const moveSection = (i, d) => { const list = ids(); [list[i], list[i + d]] = [list[i + d], list[i]]; revise({ sections: list }); };
  const removeSection = i => revise({ sections: ids().filter((_, k) => k !== i) });
  const duplicateSection = i => {
    const s = bp.sections[i];
    const list = ids();
    list.splice(i + 1, 0, { type: s.type, bars: s.bars, energy: s.energy, chords_per_bar: s.chords_per_bar,
      arrangement: s.arrangement, progression: s.progression });
    revise({ sections: list });
  };
  const addSection = type => revise({ sections: [...ids(), { type }] });

  const v = bp.vocal;
  const checks = bp.originality?.checks || [];

  return <div className="bp" aria-busy={busy}>
    <div className="bp-head">
      <div style={{ minWidth: 0, flexGrow: 1 }}>
        <input className="bp-title-input" defaultValue={bp.title} key={`t-${bp.title}`} aria-label="Blueprint title"
          onBlur={e => { if (e.target.value.trim() && e.target.value !== bp.title) revise({ title: e.target.value.trim() }); }}
          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} />
        <div className="bp-meta">
          <span className="au-chip holo">{bp.era.name}</span>
          <span className="au-chip mono">revision {bp.revision}</span>
          {bp.inputs.used_dna && <span className="au-chip signal">Artist DNA · {bp.inputs.dna_songs} songs</span>}
          {bp.demo && <span className="au-chip holo" title={(bp.why.demo || []).join(" ")}>{bp.demo.role} melody from your demo</span>}
          {bp.edited.length > 0 && <span className="au-chip">edited: {bp.edited.join(", ")}</span>}
          {busy && <span className="au-chip">updating…</span>}
        </div>
      </div>
      <SaveBox API={API} bp={bp} />
    </div>

    {error && <div role="alert" className="bp-alert warn">{error}</div>}
    {bp.validation?.warnings?.length > 0 && <div className="bp-alert note">
      {bp.validation.warnings.map((w, i) => <div key={i}>{w}</div>)}</div>}

    <div className="bp-facts">
      <div className="bp-fact">
        <label className="au-caption" htmlFor="bp-tempo">Tempo (BPM)</label>
        <input id="bp-tempo" className="au-input au-mono" type="number" min={40} max={220} step={1}
          defaultValue={bp.tempo} key={`tempo-${bp.tempo}`} disabled={busy}
          onBlur={e => { const n = parseFloat(e.target.value); if (n && n !== bp.tempo) revise({ tempo: n }); }}
          onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} />
        <Why lines={bp.why.tempo} />
      </div>
      <div className="bp-fact">
        <label className="au-caption" htmlFor="bp-key">Key</label>
        <select id="bp-key" className="au-input" value={bp.key} disabled={busy} onChange={e => revise({ key: e.target.value })}>
          {!KEYS.includes(bp.key) && <option value={bp.key}>{bp.key}</option>}
          {KEYS.map(k => <option key={k} value={k}>{k}</option>)}
        </select>
        <Why lines={[...(bp.why.key || []), ...(bp.why.mode || [])]} />
      </div>
      <div className="bp-fact">
        <div className="au-caption">Meter · length</div>
        <div className="bp-fact-value">{bp.meter} · {fmtTime(bp.duration_seconds)}</div>
        <Why lines={bp.why.form} />
      </div>
      <div className="bp-fact">
        <div className="au-caption">Groove</div>
        <div style={{ fontWeight: 700, marginTop: 6 }}>{bp.groove.name}</div>
        <div style={{ fontSize: 12, color: "var(--steel)" }}>{bp.groove.push_pull} · {bp.groove.status}</div>
        <Why lines={bp.why.groove} />
      </div>
    </div>

    <RenderPanel API={API} bp={bp} />

    <EnergyCurve bp={bp} />
    <Why lines={[...(bp.why.demo || []), ...(bp.why.influence || []), ...(bp.why.era || []), ...(bp.why.energy || []), ...(bp.why.harmony || [])]} />

    <div className="au-caption">Sections</div>
    {bp.sections.map((s, i) => <Section key={s.id} s={s} index={i} count={bp.sections.length} busy={busy}
      options={bp.harmony_options?.[s.type] || []} generators={generators}
      onChange={patch => editSection(i, patch)} onMove={d => moveSection(i, d)}
      onRemove={() => removeSection(i)} onDuplicate={() => duplicateSection(i)}
      onRegenerate={() => post("regenerate", { blueprint: bp, section_id: s.id })} />)}
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      <span className="au-caption">Add</span>
      {TYPES.map(([id, name]) => <button key={id} className="au-pill" disabled={busy} onClick={() => addSection(id)}>+ {name}</button>)}
    </div>

    <div className="bp-grid2">
      <div className="bp-panel">
        <div className="au-caption">Vocal range constraints</div>
        <div style={{ marginTop: 6 }}>Range <b>{v.range}</b> · {v.range_source}</div>
        {v.lift_semitones != null && <div>Chorus lift: <b style={{ color: "var(--gold-light)" }}>{v.lift_semitones} semitones</b> over the verse peak</div>}
        {Object.values(v.patterns || {}).map(p => <div key={p.id} style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>
          {p.name}: {p.contour}, {p.phrase_bars[0]}–{p.phrase_bars[1]}-bar phrases, ends on {p.end_degree} ({p.status})</div>)}
        <Why lines={v.why} />
      </div>
      <div className="bp-panel">
        <div className="au-caption">Arrangement</div>
        <div style={{ marginTop: 6 }}>{bp.arrangement.palette.join(" · ")}</div>
        <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>
          {bp.arrangement.palette_status} · mix profile <span className="au-mono">{bp.arrangement.mix_profile}</span></div>
        {(bp.arrangement.comments || []).map((n, i) => <div key={i} style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>{n}</div>)}
        <Why lines={bp.why.arrangement} />
      </div>
      {bp.atmosphere && <div className="bp-panel">
        <div className="au-caption">Atmosphere</div>
        <div style={{ marginTop: 6 }}>{bp.atmosphere.layers.join(" · ")}</div>
        <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>
          {bp.atmosphere.status} · set each section's <b>Atmos</b> chip to shape it</div>
        <Why lines={bp.why.atmosphere} />
      </div>}
      <div className="bp-panel">
        <div className="au-caption">Originality</div>
        {checks.map(c => <div key={c.id} className="bp-check">
          <i style={{ color: c.status === "flag" ? "var(--warn)" : c.status === "pass" ? "var(--signal)" : "var(--gold-light)" }}>
            {c.status === "flag" ? "!" : c.status === "pass" ? "✓" : "i"}</i>
          <span><b>{c.label}</b><br /><span style={{ color: "var(--steel)", fontSize: 12 }}>{c.detail}</span></span>
        </div>)}
        <div style={{ fontSize: 11, color: "var(--steel-dim)", marginTop: 8 }}>{bp.originality?.note}</div>
      </div>
    </div>
  </div>;
}
