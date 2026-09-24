import React, { useEffect, useMemo, useRef, useState } from "react";
import "./MyMusic.css";

/* My Music: the user's own catalog, indexed in place and analysed locally.
   This is the evidence Artist DNA will be built from, so every number here is
   shown with where it came from (stems vs mix) and guesses are labelled. */

const ROLE_COLORS = {
  intro: "#596276", verse: "#8d70ff", "pre-chorus": "#66e8ff", chorus: "#ff62c8",
  bridge: "#ffbd73", instrumental: "#46f6bd", outro: "#596276", section: "#3b4460",
};
const STEM_LABEL = {
  lead_vocal: "Lead vox", vocal: "Vocals", backing_vocal: "BGV", drums: "Drums",
  bass: "Bass", harmonic: "Music", other: "Other",
};

function fmtTime(seconds) {
  if (seconds == null) return "";
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

function EnergyTimeline({ analysis }) {
  const energy = analysis.energy?.per_bar || [];
  const sections = analysis.structure?.sections || [];
  const n = Math.max(energy.length, 1);
  const w = 600, h = 90;
  const points = energy.map((e, i) => `${(i + 0.5) / n * w},${h - 8 - e * (h - 30)}`).join(" ");
  return <svg className="mm-timeline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img"
    aria-label="Energy per bar with detected sections">
    {sections.map((s, i) => <g key={i}>
      <rect x={s.start_bar / n * w} y={h - 18} width={Math.max(s.bars / n * w - 1, 1)} height={14}
        fill={ROLE_COLORS[s.role_guess] || "#3b4460"} rx="2" />
      <title>{`${s.label} · ${s.role_guess} · ${s.bars} bars · ${fmtTime(s.start_seconds)}`}</title>
    </g>)}
    <polyline points={points} fill="none" stroke="var(--cyan)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
  </svg>;
}

function Fact({ label, value, note }) {
  return <div className="mm-fact">
    <div className="mm-fact-label">{label}</div>
    <div className="mm-fact-value">{value ?? "—"}</div>
    {note && <div className="mm-fact-note">{note}</div>}
  </div>;
}

function SongDetail({ song }) {
  const a = song.analysis;
  if (!a) return <div className="mm-empty">
    {song.analysis_status === "error" ? `Analysis failed: ${song.error}` : "Not analysed yet."}
  </div>;
  const t = a.tempo, k = a.key, g = a.global, h = a.harmony, r = a.rhythm, m = a.melody, p = a.production;
  const sections = a.structure?.sections || [];
  return <div>
    <div className="mm-facts">
      <Fact label="Tempo" value={`${t.bpm} BPM`} note={t.octave_folded ? `tracker said ${t.raw_tracker_bpm}` : `alt ${t.alternates.join(" / ")}`} />
      <Fact label="Key" value={k.name} note={`${Math.round(k.confidence * 100)}% · from ${k.source}`} />
      <Fact label="Length" value={fmtTime(g.duration_seconds)} note={`${t.bar_count} bars`} />
      <Fact label="Loudness" value={`${g.integrated_lufs} LUFS`} note={`LRA ${g.loudness_range_lu ?? "—"} · TP ${g.true_peak_db}`} />
      <Fact label="Width" value={g.stereo_width} note="side / mid" />
      <Fact label="Chord rate" value={`${h.changes_per_bar}/bar`} note={`${Math.round(h.diatonic_share * 100)}% diatonic`} />
    </div>

    <h4 className="mm-h">Structure <span className="mm-guess">roles are guesses · {a.structure?.method}</span></h4>
    <EnergyTimeline analysis={a} />
    <div className="mm-sections">
      {sections.map((s, i) => <span key={i} className="mm-section" style={{ borderColor: ROLE_COLORS[s.role_guess] }}>
        <b>{s.label}</b> {s.role_guess} · {s.bars}
      </span>)}
    </div>

    <h4 className="mm-h">Harmony</h4>
    <div className="mm-chips">
      {h.top_progressions.slice(0, 4).map((pr, i) => <span className="mm-chip" key={i}>
        {pr.progression.join(" – ")}{pr.count > 1 ? ` ×${pr.count}` : ""}</span>)}
    </div>
    <div className="mm-chords">{h.chords_per_bar.slice(0, 32).join("  ")}{h.chords_per_bar.length > 32 ? "  …" : ""}</div>

    <h4 className="mm-h">Rhythm <span className="mm-guess">from {r.source}</span></h4>
    <div className="mm-facts">
      <Fact label="Onsets / beat" value={r.onsets_per_beat} />
      <Fact label="Syncopation" value={r.syncopation} note="share off the beat" />
      <Fact label="Swing" value={r.swing_position ?? "—"} note="0.50 straight · 0.66 shuffle" />
    </div>

    {m && <>
      <h4 className="mm-h">Lead vocal</h4>
      <div className="mm-facts">
        <Fact label="Range" value={`${m.range_low_note}–${m.range_high_note}`} note={`centre ${m.median_note}`} />
        <Fact label="Phrases" value={m.phrase_count} note={m.phrase_beats_median ? `median ${m.phrase_beats_median} beats` : ""} />
        <Fact label="Motion" value={m.interval_profile.step != null ? `${Math.round(m.interval_profile.step * 100)}% steps` : "—"}
          note={m.interval_profile.leap != null ? `${Math.round(m.interval_profile.leap * 100)}% leaps` : ""} />
      </div>
    </>}

    {p.instrumentation && <>
      <h4 className="mm-h">Balance <span className="mm-guess">dB below the loudest stem</span></h4>
      <div className="mm-bars">
        {Object.entries(p.instrumentation).map(([role, db]) => <div className="mm-bar-row" key={role}>
          <span>{STEM_LABEL[role] || role}</span>
          <div className="mm-bar"><div style={{ width: `${Math.max(4, 100 + db * 3)}%` }} /></div>
          <span className="mm-num">{db}</span>
        </div>)}
      </div>
    </>}
  </div>;
}

export default function MyMusic({ API, onBack }) {
  const [library, setLibrary] = useState({ sources: [], songs: [] });
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const socket = useRef(null);
  const lastDone = useRef(-1);

  async function json(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  const refresh = () => json(`${API}/artist/library`).then(setLibrary);
  useEffect(() => { refresh().catch(e => setError(e.message)); return () => socket.current?.close(); }, [API]);

  async function run(task) {
    setBusy(true); setError("");
    try { await task(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const addFolder = () => run(async () => {
    await json(`${API}/artist/library/sources`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }),
    });
    setPath("");
    await refresh();
  });

  const removeFolder = source => {
    if (!window.confirm(`Stop using ${source.path}? Its analyses are forgotten; the folder itself is not touched.`)) return;
    run(async () => { await json(`${API}/artist/library/sources/${source.id}`, { method: "DELETE" }); await refresh(); });
  };

  const rescan = () => run(async () => { await json(`${API}/artist/library/rescan`, { method: "POST" }); await refresh(); });

  const analyse = () => run(async () => {
    const started = await json(`${API}/artist/library/analyze`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    if (!started.job_id) return;
    setJob({ stage: "queued", pct: 0, details: { done: 0, total: started.total } });
    socket.current?.close();
    const ws = new WebSocket(`${API.replace("http", "ws")}/ws/jobs/${started.job_id}`);
    socket.current = ws;
    ws.onmessage = event => {
      const d = JSON.parse(event.data);
      setJob(d);
      const doneCount = d.details?.done ?? 0;
      if (d.stage === "done" || d.stage === "error" || doneCount !== lastDone.current) {
        lastDone.current = doneCount;
        refresh();
      }
    };
  });

  const open = id => run(async () => setSelected(await json(`${API}/artist/library/songs/${id}`)));

  const toggleIncluded = (song, included) => run(async () => {
    await json(`${API}/artist/library/songs/${song.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ included }),
    });
    await refresh();
    if (selected?.id === song.id) setSelected({ ...selected, included });
  });

  const songs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return library.songs.filter(s => !q || s.title.toLowerCase().includes(q) || s.variants.join(" ").includes(q));
  }, [library, query]);
  const pending = library.songs.filter(s => s.analysis_status !== "done").length;
  const done = library.songs.length - pending;
  const running = job && job.stage !== "done" && job.stage !== "error";

  return <div className="mm-shell">
    {onBack && <button className="mm-button" onClick={onBack} style={{ marginBottom: 14 }}>← Auralis home</button>}
    <div className="mm-grid">
      <section className="mm-card">
        <h2 className="mm-title">My Music</h2>
        <p className="mm-sub">Your own songs, read in place and analysed on this PC. Nothing is copied or uploaded.
          This is what Artist DNA will learn from.</p>

        <div className="mm-sources">
          {library.sources.map(s => <div className="mm-source" key={s.id}>
            <span className="mm-path">{s.path}</span>
            <button className="mm-link danger" onClick={() => removeFolder(s)}>remove</button>
          </div>)}
        </div>
        <div className="mm-row">
          <input className="mm-input" placeholder="Folder path, e.g. D:\Music\My Songs" value={path}
            onChange={e => setPath(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && path.trim()) addFolder(); }} />
          <button className="mm-button" disabled={busy || !path.trim()} onClick={addFolder}>Add folder</button>
          <button className="mm-button" disabled={busy || running} onClick={rescan}>Rescan</button>
          <button className="mm-button primary" disabled={busy || running || pending === 0} onClick={analyse}>
            {pending ? `Analyse ${pending} song${pending === 1 ? "" : "s"}` : "All analysed"}
          </button>
        </div>
        {running && <div className="mm-progress">
          <div className="mm-progress-text">{job.details?.done ?? 0}/{job.details?.total ?? "?"} · {job.stage}</div>
          <div className="mm-track"><div style={{ width: `${job.pct || 0}%` }} /></div>
        </div>}
        {job?.stage === "done" && job.result?.failed?.length > 0 &&
          <div className="mm-error">{job.result.failed.length} song(s) failed — see their rows.</div>}
        {error && <div className="mm-error">{error}</div>}

        <div className="mm-row" style={{ marginTop: 14 }}>
          <input className="mm-input" placeholder="Filter songs" value={query} onChange={e => setQuery(e.target.value)} />
          <span className="mm-count">{done}/{library.songs.length} analysed</span>
        </div>
        <div className="mm-table-wrap">
          <table className="mm-table">
            <thead><tr><th>Song</th><th>BPM</th><th>Key</th><th className="mm-hide-sm">Form</th><th className="mm-hide-sm">Vocal</th><th title="Use for Artist DNA">DNA</th></tr></thead>
            <tbody>
              {songs.map(s => <tr key={s.id} className={selected?.id === s.id ? "active" : ""} onClick={() => open(s.id)}>
                <td>
                  <div className="mm-song">{s.title}</div>
                  <div className="mm-tags">
                    <span className={`mm-tag ${s.kind === "stem-set" ? "stems" : ""}`}>{s.kind === "stem-set" ? `stems · ${s.stem_roles.length}` : "mix"}</span>
                    {s.variants.map(v => <span className="mm-tag" key={v}>{v}</span>)}
                    {s.analysis_status !== "done" && <span className={`mm-tag ${s.analysis_status === "error" ? "bad" : ""}`}>{s.analysis_status}</span>}
                  </div>
                </td>
                <td className="mm-num">{s.summary?.bpm ?? ""}</td>
                <td>{s.summary?.key ?? ""}</td>
                <td className="mm-form mm-hide-sm">{s.summary?.roles_form ?? ""}</td>
                <td className="mm-hide-sm">{s.summary?.vocal_range ?? ""}</td>
                <td onClick={e => e.stopPropagation()}>
                  <input type="checkbox" checked={s.included} aria-label={`Use ${s.title} for Artist DNA`}
                    onChange={e => toggleIncluded(s, e.target.checked)} />
                </td>
              </tr>)}
            </tbody>
          </table>
          {library.songs.length === 0 && <div className="mm-empty">Add a folder that holds your songs, stems, or stem .zip packages.</div>}
        </div>
      </section>

      <section className="mm-card">
        {!selected && <div className="mm-empty">Choose a song to see its tempo, key, structure, chords, groove and vocal range.</div>}
        {selected && <>
          <h3 className="mm-detail-title">{selected.title}</h3>
          <div className="mm-sub">{selected.location} · {selected.files.length} file{selected.files.length === 1 ? "" : "s"}
            {selected.has_lyrics ? " · lyrics linked" : ""}</div>
          <SongDetail song={selected} />
        </>}
      </section>
    </div>
  </div>;
}
