import React, { useEffect, useMemo, useRef, useState } from "react";
import { Cover, apiJson, catalogStats, fmtTime } from "./ui.jsx";
import "./MyMusic.css";

/* My Music: the user's own catalog, indexed in place and analysed locally.
   This is the evidence Artist DNA will be built from, so every number here is
   shown with where it came from (stems vs mix) and guesses are labelled. */

const ROLE_COLORS = {
  intro: "#3a4252", verse: "#3c4d66", "pre-chorus": "#2b6f7d", chorus: "#b8923f",
  bridge: "#7a5f33", instrumental: "#2f5a4f", outro: "#3a4252", section: "#2d3441",
};
const STEM_LABEL = {
  lead_vocal: "Lead vox", vocal: "Vocals", backing_vocal: "BGV", drums: "Drums",
  bass: "Bass", harmonic: "Music", other: "Other",
};
const FILTERS = ["All", "Stem sets", "Full mixes", "In DNA", "Needs analysis"];

function EnergyTimeline({ analysis }) {
  const energy = analysis.energy?.per_bar || [];
  const sections = analysis.structure?.sections || [];
  const n = Math.max(energy.length, 1);
  const w = 600, h = 90;
  const points = energy.map((e, i) => `${(i + 0.5) / n * w},${h - 22 - e * (h - 34)}`).join(" ");
  return <svg className="mm-timeline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img"
    aria-label="Energy per bar with detected sections">
    {sections.map((s, i) => <g key={i}>
      <rect x={s.start_bar / n * w} y={h - 16} width={Math.max(s.bars / n * w - 1.5, 1)} height={12}
        fill={ROLE_COLORS[s.role_guess] || "#2d3441"} rx="2" />
      <title>{`${s.label} · ${s.role_guess} · ${s.bars} bars · ${fmtTime(s.start_seconds)}`}</title>
    </g>)}
    <polyline points={points} fill="none" stroke="#d4af5f" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
  </svg>;
}

function Fact({ label, value, note }) {
  return <div className="mm-fact">
    <div className="au-caption">{label}</div>
    <div className="mm-fact-value">{value ?? "—"}</div>
    {note && <div className="mm-fact-note">{note}</div>}
  </div>;
}

function SongDetail({ song, play }) {
  const a = song.analysis;
  return <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
    <Cover id={song.id} size={132} radius={18} />
    <div>
      <h2 className="au-title" style={{ fontSize: 20, lineHeight: 1.35, overflowWrap: "anywhere" }}>{song.title}</h2>
      <div className="au-sub" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
        {song.kind === "stem-set" ? `Stem set · ${song.files.filter(f => f.role !== "reference").length} stems` : "Full mix"}
        {song.has_lyrics ? " · lyrics linked" : ""} · {song.location}
      </div>
    </div>
    <div style={{ display: "flex", gap: 8 }}>
      <button className="au-btn light" onClick={() => play(song)}>Play</button>
    </div>
    {!a && <div className="mm-empty">{song.analysis_status === "error" ? `Analysis failed: ${song.error}` : "Not analysed yet."}</div>}
    {a && <>
      <div className="mm-facts">
        <Fact label="Tempo" value={`${a.tempo.bpm} BPM`} note={`or ${a.tempo.alternates.join(" / ")}`} />
        <Fact label="Key" value={a.key.name} note={`${Math.round(a.key.confidence * 100)}% · from ${a.key.source}`} />
        <Fact label="Length" value={fmtTime(a.global.duration_seconds)} note={`${a.tempo.bar_count} bars`} />
        <Fact label="Loudness" value={`${a.global.integrated_lufs} LUFS`} note={`LRA ${a.global.loudness_range_lu ?? "—"} · TP ${a.global.true_peak_db}`} />
      </div>

      <div>
        <h3 className="mm-h">Structure <span className="mm-guess">roles are guesses · {a.structure?.method}</span></h3>
        <EnergyTimeline analysis={a} />
        <div className="mm-sections">
          {(a.structure?.sections || []).map((s, i) => <span key={i} className="mm-section" style={{ borderLeftColor: ROLE_COLORS[s.role_guess] }}>
            <b>{s.label}</b> {s.role_guess} · {s.bars}</span>)}
        </div>
      </div>

      <div>
        <h3 className="mm-h">Harmony <span className="mm-guess">{a.harmony.changes_per_bar} changes / bar</span></h3>
        <div className="mm-chips">
          {a.harmony.top_progressions.slice(0, 4).map((pr, i) => <span className="mm-chip" key={i}>
            {pr.progression.join(" – ")}{pr.count > 1 ? ` ×${pr.count}` : ""}</span>)}
        </div>
      </div>

      <div>
        <h3 className="mm-h">Rhythm <span className="mm-guess">from {a.rhythm.source}</span></h3>
        <div className="mm-facts">
          <Fact label="Onsets / beat" value={a.rhythm.onsets_per_beat} />
          <Fact label="Syncopation" value={a.rhythm.syncopation} note="share off the beat" />
        </div>
      </div>

      {a.melody && <div>
        <h3 className="mm-h">Lead vocal</h3>
        <div className="mm-facts">
          <Fact label="Range" value={`${a.melody.range_low_note}–${a.melody.range_high_note}`} note={`centre ${a.melody.median_note}`} />
          <Fact label="Phrases" value={a.melody.phrase_count} note={a.melody.phrase_beats_median ? `median ${a.melody.phrase_beats_median} beats` : ""} />
        </div>
      </div>}

      {a.production?.instrumentation && <div>
        <h3 className="mm-h">Balance <span className="mm-guess">dB below the loudest stem</span></h3>
        <div className="mm-bars">
          {Object.entries(a.production.instrumentation).map(([role, db]) => <div className="mm-bar-row" key={role}>
            <span>{STEM_LABEL[role] || role}</span>
            <div className="mm-bar"><div style={{ width: `${Math.max(4, 100 + db * 3)}%` }} /></div>
            <span className="au-mono">{db}</span>
          </div>)}
        </div>
        {a.stems_ignored?.length > 0 && <div className="mm-guess" style={{ marginLeft: 0, marginTop: 6 }}>
          ignored as near-silent: {a.stems_ignored.map(r => STEM_LABEL[r] || r).join(", ")}</div>}
      </div>}
    </>}
  </div>;
}

export default function MyMusic({ API, play }) {
  const [library, setLibrary] = useState({ sources: [], songs: [] });
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const socket = useRef(null);
  const lastDone = useRef(-1);

  const refresh = () => apiJson(`${API}/artist/library`).then(setLibrary);
  useEffect(() => { refresh().catch(e => setError(e.message)); return () => socket.current?.close(); }, [API]);

  async function run(task) {
    setBusy(true); setError("");
    try { await task(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const addFolder = () => run(async () => {
    await apiJson(`${API}/artist/library/sources`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }),
    });
    setPath("");
    await refresh();
  });

  const removeFolder = source => {
    if (!window.confirm(`Stop using ${source.path}? Its analyses are forgotten; the folder itself is not touched.`)) return;
    run(async () => { await apiJson(`${API}/artist/library/sources/${source.id}`, { method: "DELETE" }); await refresh(); });
  };

  const rescan = () => run(async () => { await apiJson(`${API}/artist/library/rescan`, { method: "POST" }); await refresh(); });

  const analyse = () => run(async () => {
    const started = await apiJson(`${API}/artist/library/analyze`, {
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

  const open = id => run(async () => setSelected(await apiJson(`${API}/artist/library/songs/${id}`)));

  const toggleIncluded = (song, included) => run(async () => {
    await apiJson(`${API}/artist/library/songs/${song.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ included }),
    });
    await refresh();
    if (selected?.id === song.id) setSelected({ ...selected, included });
  });

  const stats = useMemo(() => catalogStats(library.songs), [library]);
  const songs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return library.songs.filter(s => {
      if (filter === "Stem sets" && s.kind !== "stem-set") return false;
      if (filter === "Full mixes" && s.kind !== "mix") return false;
      if (filter === "In DNA" && !s.included) return false;
      if (filter === "Needs analysis" && s.analysis_status === "done") return false;
      return !q || s.title.toLowerCase().includes(q) || s.variants.join(" ").includes(q);
    });
  }, [library, query, filter]);
  const pending = library.songs.filter(s => s.analysis_status !== "done").length;
  const running = job && job.stage !== "done" && job.stage !== "error";

  return <div className="au-page mm-page">
    <section className="mm-main" aria-label="Catalog">
      <div className="mm-head">
        <div>
          <h1 className="au-title au-shine">My Music</h1>
          <p className="au-sub">Read in place from your folders. Nothing is copied or uploaded.</p>
        </div>
        <div className="mm-sources">
          {library.sources.map(s => <span className="mm-source" key={s.id}>
            <span className="au-mono">{s.path}</span>
            <button className="mm-link" aria-label={`Remove ${s.path}`} onClick={() => removeFolder(s)}>×</button>
          </span>)}
        </div>
      </div>

      <div className="mm-row">
        <input className="au-input" style={{ flex: "1 1 240px", minWidth: 0 }} placeholder="Add a folder, e.g. D:\Music\My Songs" value={path}
          aria-label="Folder path" onChange={e => setPath(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && path.trim()) addFolder(); }} />
        <button className="au-btn" disabled={busy || !path.trim()} onClick={addFolder}>Add folder</button>
        <button className="au-btn" disabled={busy || running} onClick={rescan}>Rescan</button>
        <button className="au-btn gold" disabled={busy || running || pending === 0} onClick={analyse}>
          {pending ? `Analyse ${pending} song${pending === 1 ? "" : "s"}` : "All analysed"}
        </button>
      </div>
      {running && <div className="mm-progress">
        <div className="au-mono mm-progress-text">{job.details?.done ?? 0}/{job.details?.total ?? "?"} · {job.stage}</div>
        <div className="au-progress"><div style={{ width: `${job.pct || 0}%` }} /></div>
      </div>}
      {job?.stage === "done" && job.result?.failed?.length > 0 &&
        <div className="mm-error">{job.result.failed.length} song(s) failed. Their rows say why.</div>}
      {error && <div className="mm-error" role="alert">{error}</div>}

      {stats && <div className="au-card au-console mm-sound">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h2 className="au-title au-shine" style={{ fontSize: 18 }}>Your sound so far</h2>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--holo-soft)" }}>PREVIEW · full Artist DNA is next</span>
        </div>
        <div className="mm-sound-grid">
          <Fact label="Songs" value={stats.total} note={`${stats.stemSets} stem sets`} />
          <Fact label="Tempo" value={`${stats.tempoLow}–${stats.tempoHigh}`} note="middle half, BPM" />
          <Fact label="Mode" value={`${stats.minorShare}% minor`} note={`${stats.minorCount} of ${stats.analysed}`} />
          <Fact label="Chords" value={`${stats.chordsPerBar} / bar`} note="median change rate" />
          <Fact label="Loudness" value={stats.lufs} note="median LUFS" />
          <Fact label="Vocal stems" value={stats.withVocal} note="with a lead melody" />
        </div>
      </div>}

      <div className="mm-row">
        {FILTERS.map(f => <button key={f} className="au-pill" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
        <div style={{ flexGrow: 1 }} />
        <input className="au-input" style={{ width: 200 }} placeholder="Filter" aria-label="Filter songs" value={query} onChange={e => setQuery(e.target.value)} />
        <span className="au-mono" style={{ fontSize: 12, color: "var(--signal)" }}>{library.songs.length - pending}/{library.songs.length} analysed</span>
      </div>

      <div className="mm-table-wrap">
        <table className="mm-table">
          <thead><tr><th>Song</th><th>BPM</th><th>Key</th><th className="mm-hide-sm">Form</th><th className="mm-hide-sm">Vocal</th><th title="Use for Artist DNA">DNA</th></tr></thead>
          <tbody>
            {songs.map(s => <tr key={s.id} className={selected?.id === s.id ? "active" : ""} onClick={() => open(s.id)}>
              <td>
                <div style={{ display: "flex", gap: 12, alignItems: "center", minWidth: 0 }}>
                  <Cover id={s.id} size={40} radius={9} />
                  <div style={{ minWidth: 0 }}>
                    <button className="mm-song" onClick={e => { e.stopPropagation(); open(s.id); }}>{s.title}</button>
                    <div className="mm-tags">
                      <span className="mm-tag" style={{ color: s.kind === "stem-set" ? "var(--signal)" : "var(--steel)" }}>
                        {s.kind === "stem-set" ? `STEMS · ${s.stem_roles.length}` : "MIX"}</span>
                      {s.variants.map(v => <span className="mm-tag" key={v}>{v}</span>)}
                      {s.analysis_status !== "done" && <span className={`mm-tag ${s.analysis_status === "error" ? "bad" : ""}`}>{s.analysis_status}</span>}
                    </div>
                  </div>
                </div>
              </td>
              <td className="au-mono">{s.summary?.bpm ?? ""}</td>
              <td>{s.summary?.key ?? ""}</td>
              <td className="mm-form mm-hide-sm">{s.summary?.roles_form ?? ""}</td>
              <td className="mm-hide-sm" style={{ color: "var(--holo-soft)" }}>{s.summary?.vocal_range ?? ""}</td>
              <td onClick={e => e.stopPropagation()}>
                <button role="switch" className="au-switch small" aria-checked={s.included}
                  aria-label={`Use ${s.title} for Artist DNA`} onClick={() => toggleIncluded(s, !s.included)} />
              </td>
            </tr>)}
          </tbody>
        </table>
        {library.songs.length === 0 && <div className="mm-empty">Add a folder that holds your songs, stems, or stem .zip packages.</div>}
      </div>
    </section>

    <aside className="mm-detail" aria-label="Song detail">
      {selected ? <SongDetail song={selected} play={play} />
        : <div className="mm-empty">Choose a song to see its tempo, key, structure, chords, groove and vocal range.</div>}
    </aside>
  </div>;
}
