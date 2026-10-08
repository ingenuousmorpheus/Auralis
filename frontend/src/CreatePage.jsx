import React, { useEffect, useMemo, useState } from "react";
import AtlasPanel from "./AtlasPanel.jsx";
import BlueprintView from "./BlueprintView.jsx";
import SongStudio from "./SongStudio.jsx";
import DemoPanel from "./DemoPanel.jsx";
import { Cover, Icon, apiJson, catalogStats, fmtTime } from "./ui.jsx";
import { Badge, Progress, Segment } from "./Lux.jsx";
import "./CreatePage.css";

/* Create: prompt / lyrics beside the workspace.

   Luxury pass (Session 023): re-skinned on the shared Lux primitives
   (`lx-*` classes, `--lx-*` tokens from lux.css). Composition, voice
   selection, rendering pipeline and project behavior are unchanged.

   Create can build an editable Song Blueprint or run the implemented full-song
   chain (composer → guide singer → selected My Voice → vocal production →
   mix/master → persistent project). My Voice and Create intentionally share
   the same remembered voice selection. */

const FILTERS = ["All", "Stem sets", "Full mixes", "With vocal"];

/* Roadmap Screen 3: the visible stages of making a song. */
const STAGES = [
  ["writing the blueprint", "Writing song blueprint"], ["arranging", "Composing harmony, bass and drums"],
  ["planning atmosphere", "Creating atmosphere"], ["rendering", "Rendering instrumental"],
  ["mix and master", "Mixing and mastering the instrumental"], ["guide", "Creating guide vocals"],
  ["convert", "Rendering your voice"], ["pitch polish", "Pitch polish"], ["vocal finish", "Producing vocals"],
  ["song mix", "Mixing and mastering the song"], ["saving", "Saving to a new project"],
];

function MakingSong({ status, sung }) {
  const stage = (status?.stage || "").toLowerCase();
  const list = sung ? STAGES : STAGES.filter(([k]) => !["guide", "convert", "pitch polish", "vocal finish", "song mix"].includes(k));
  const current = list.reduce((found, [k], i) => (stage.includes(k.split(" ")[0]) ? i : found), 0);
  return <div className="cp-making">
    <div className="lx-glass cp-panel" role="status">
      <div className="lx-eyebrow">Making your song · {Math.round(status?.pct || 0)}%</div>
      <Progress pct={status?.pct || 0} state={status?.stage === "error" ? "fail" : ""} />
      <ol className="cp-stages">
        {list.map(([k, label], i) => <li key={k} className={i < current ? "done" : i === current ? "now" : ""}>
          {i < current ? "✓" : i === current ? "▸" : "·"} {label}</li>)}
      </ol>
      <div className="cp-stage-note">{status?.stage}</div>
      {sung && <div className="cp-stage-note">Singing takes several minutes; close big apps so the voice engine has memory.</div>}
    </div>
  </div>;
}

export default function CreatePage({ API, go, play, nowPlayingId }) {
  const [mode, setMode] = useState("advanced");
  const [useDna, setUseDna] = useState(true);
  const [useVoice, setUseVoice] = useState(true);
  const [influence, setInfluence] = useState("all");      // all | closest | picked (AU-12)
  const [picked, setPicked] = useState([]);
  const [idea, setIdea] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [styles, setStyles] = useState("");
  const [songs, setSongs] = useState([]);
  const [voice, setVoice] = useState(null);
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [style, setStyle] = useState({ era: "", harmony: "", vocal: "", groove: "" });
  const [blueprint, setBlueprint] = useState(null);
  const [view, setView] = useState("songs");
  const [creating, setCreating] = useState(false);
  const [songJob, setSongJob] = useState(null);
  const [songStatus, setSongStatus] = useState(null);
  const [projectId, setProjectId] = useState(null);
  const [showDemo, setShowDemo] = useState(false);

  useEffect(() => {
    apiJson(`${API}/artist/library`).then(d => setSongs(d.songs)).catch(() => setSongs([]));
    apiJson(`${API}/voice/profiles`).then(list => {
      let remembered = "";
      try { remembered = localStorage.getItem("auralis.voice") || ""; } catch { /* private mode */ }
      const chosen = list.find(p => p.id === remembered)
        || list.find(p => p.training_status === "trained")
        || list.find(p => p.kind === "studio-dataset")
        || list[0] || null;
      setVoice(chosen);
      if (chosen && chosen.id !== remembered) {
        try { localStorage.setItem("auralis.voice", chosen.id); } catch { /* private mode */ }
      }
    }).catch(() => setVoice(null));
  }, [API]);

  const stats = useMemo(() => catalogStats(songs), [songs]);
  const dnaTags = stats ? [
    `${stats.tempoLow}–${stats.tempoHigh} BPM`,
    stats.minorShare >= 50 ? "minor keys" : "major keys",
    `${stats.chordsPerBar} chords / bar`,
    `${stats.lufs} LUFS`,
  ] : [];

  const visible = songs.filter(s => {
    if (filter === "Stem sets" && s.kind !== "stem-set") return false;
    if (filter === "Full mixes" && s.kind !== "mix") return false;
    if (filter === "With vocal" && !s.summary?.vocal_range) return false;
    const q = query.trim().toLowerCase();
    return !q || s.title.toLowerCase().includes(q);
  });

  const addTag = tag => setStyles(prev => (prev.trim() ? `${prev.trim().replace(/,$/, "")}, ${tag}` : tag));
  const requestBody = () => ({
    prompt: mode === "simple" ? idea : [styles, idea].filter(s => s.trim()).join(", "),
    lyrics: mode === "advanced" ? lyrics : "", use_dna: useDna, use_voice: useVoice,
    influence: useDna ? (influence === "picked" && !picked.length ? "all" : influence) : "all", influence_song_ids: picked,
    ...(mode === "advanced" && Object.fromEntries(Object.entries(style).filter(([, v]) => v))),
  });
  useEffect(() => {
    if (!songJob) return;
    let stop = false;
    const tick = async () => {
      const st = await apiJson(`${API}/jobs/${songJob}`).catch(e => ({ stage: "error", error: e.message }));
      if (stop) return;
      setSongStatus(st);
      if (st.stage === "done") { setProjectId(st.result.project_id); setView("studio"); setCreating(false); }
      else if (st.stage === "error") { setNotice(`The song could not be made: ${st.error}`); setCreating(false); }
      else setTimeout(tick, 1200);
    };
    tick();
    return () => { stop = true; };
  }, [songJob]);
  const makeSong = async () => {
    setCreating("song"); setNotice(""); setSongStatus(null); setProjectId(null);
    try {
      const r = await apiJson(`${API}/composer/song`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...requestBody(), profile_id: useVoice && voice ? voice.id : null, production: "full", quality: "studio" }) });
      setSongJob(r.job_id);
      setView("making");
    } catch (e) { setNotice(`Could not start the song: ${e.message}`); setCreating(false); }
  };
  const editProjectBlueprint = async () => {
    try { setBlueprint(await apiJson(`${API}/projects/${projectId}/blueprint`)); setView("blueprint"); }
    catch (e) { setNotice(e.message); }
  };
  const create = async () => {
    const prompt = mode === "simple" ? idea : [styles, idea].filter(s => s.trim()).join(", ");
    setCreating("blueprint");
    setNotice("");
    try {
      const bp = await apiJson(`${API}/composer/blueprint`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt, lyrics: mode === "advanced" ? lyrics : "", use_dna: useDna, use_voice: useVoice,
          influence: useDna ? (influence === "picked" && !picked.length ? "all" : influence) : "all", influence_song_ids: picked,
          ...(mode === "advanced" && Object.fromEntries(Object.entries(style).filter(([, v]) => v))),
          seed: blueprint ? (blueprint.inputs.seed || 0) + 1 : 0,
        }),
      });
      setBlueprint(bp);
      setView("blueprint");
      setNotice("Blueprint ready: edit it on the right, then save it to a project. Rendering audio from it is the next build phase.");
    } catch (e) {
      setNotice(`Could not build a blueprint: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  // Workspace view tabs reuse the same selection order as the old segmented
  // control (Blueprint → Song → My songs).
  const viewSeg = view === "making" || view === "studio" ? "song" : view;
  const viewItems = [
    ...(blueprint ? [["blueprint", "Blueprint"]] : []),
    ...(songJob ? [["song", "Song"]] : []),
    ["songs", "My songs"],
  ];

  return <div className="au-page cp">
    <section aria-label="Create a song" className="cp-create">
      <div className="cp-top">
        <Segment label="Create mode" items={[["simple", "Simple"], ["advanced", "Advanced"]]} value={mode} onChange={setMode} />
        <Badge plain>local engine</Badge>
      </div>

      <div className="cp-body">
        <div className="cp-actions">
          <button className="lx-btn"
            onClick={() => setShowDemo(v => !v)} aria-expanded={showDemo}>
            <Icon name="plus" size={16} width={2.4} />Demo</button>
          <button className="lx-btn" onClick={() => go("voice")}>
            <Icon name="voice" size={16} />My Voice</button>
          <button className="lx-btn" onClick={() => go("music")}><Icon name="plus" size={16} width={2.4} />My songs</button>
        </div>

        {showDemo && <DemoPanel API={API} prompt={mode === "simple" ? idea : [styles, idea].filter(x => x.trim()).join(", ")}
          lyrics={mode === "advanced" ? lyrics : ""} useDna={useDna} useVoice={useVoice} era={mode === "advanced" ? style.era : ""}
          onClose={() => setShowDemo(false)}
          onBlueprint={bp => { setBlueprint(bp); setView("blueprint"); setShowDemo(false);
            setNotice(`Built around your demo: ${bp.demo.note_count} notes kept as the ${bp.demo.role} at ${bp.tempo} BPM in ${bp.key}.`); }} />}
        {mode === "simple" && <div className="lx-glass cp-field-block">
          <label htmlFor="idea" className="lx-eyebrow">Song description</label>
          <textarea id="idea" rows={7} className="cp-textarea" style={{ fontSize: 15 }} value={idea} onChange={e => setIdea(e.target.value)}
            placeholder="Dark late-night R&B, big chorus, feels like my last three songs without copying them" />
        </div>}

        {mode === "advanced" && <>
          <div className="lx-glass cp-field-block">
            <div className="cp-field-head">
              <label htmlFor="lyrics" className="lx-eyebrow">Lyrics</label>
              <span className="cp-count">{lyrics.trim() ? `${lyrics.trim().split(/\n+/).length} lines` : "instrumental if empty"}</span>
            </div>
            <textarea id="lyrics" rows={7} className="cp-textarea" value={lyrics} onChange={e => setLyrics(e.target.value)}
              placeholder="Write or paste lyrics. Leave empty for an instrumental." />
          </div>

          <div className="lx-glass cp-field-block">
            <label htmlFor="styles" className="lx-eyebrow">Styles</label>
            <input id="styles" className="cp-textarea" style={{ resize: "none", padding: "10px 14px" }} value={styles} onChange={e => setStyles(e.target.value)}
              placeholder="late-night R&B, warm low end, big chorus" />
            {dnaTags.length > 0 && <div className="cp-dna-tags">
              <span className="lx-eyebrow">From your music</span>
              {dnaTags.map(tag => <button key={tag} className="lx-tag" onClick={() => addTag(tag)}>+ {tag}</button>)}
            </div>}
          </div>

          <AtlasPanel API={API} value={style} onChange={setStyle} />

          <div className="lx-glass cp-setting">
            <div className="cp-setting-row">
              <div><div className="cp-label">Use my Artist DNA</div>
                <div className="cp-sub">{stats ? `Tempo, keys, form and groove from ${stats.analysed} analysed songs` : "Add your songs in My Music first"}</div></div>
              <button role="switch" className="cp-switch" aria-checked={useDna} aria-label="Use my Artist DNA" onClick={() => setUseDna(v => !v)} />
            </div>
            {useDna && <div className="cp-influence">
              <span className="lx-eyebrow">Influence</span>
              <Segment label="Influence from my songs" value={influence}
                onChange={id => { setInfluence(id); if (id === "picked") setView("songs"); }}
                items={[["all", "All my songs"], ["closest", "Closest 5"], ["picked", "Songs I pick"]]} />
              {influence === "picked" && <span className="cp-sub">
                {picked.length ? `${picked.length} picked` : "click songs on the right to pick them"}</span>}
            </div>}
            <div className="cp-setting-row">
              <div><div className="cp-label">Sing it in my voice</div>
                <div className="cp-sub">{voice ? `Guide singer → ${voice.name} → pitch + vocal finish` : "Create a voice profile in My Voice"}</div></div>
              <button role="switch" className="cp-switch" aria-checked={useVoice} aria-label="Sing it in my voice" onClick={() => setUseVoice(v => !v)} />
            </div>
            <div className="cp-summary-grid">
              <div><div className="lx-eyebrow">Vocals</div><div className="cp-summary-value">Lead + doubles</div></div>
              <div><div className="lx-eyebrow">Mix</div><div className="cp-summary-value">Vocal-forward R&amp;B</div></div>
              <div><div className="lx-eyebrow">Master</div><div className="cp-summary-value cp-mono">−14 LUFS</div></div>
            </div>
          </div>
        </>}

        {notice && <div role="status" className="lx-glass cp-notice">{notice}</div>}
      </div>

      <div className="cp-cta">
        <div className="cp-cta-row">
          <button className="lx-btn primary big" onClick={create} disabled={creating} title="Write an editable blueprint first">
            <Icon name="create" size={18} width={2.4} />{creating === "blueprint" ? "Writing…" : blueprint ? "New blueprint" : "Create"}</button>
          <button className="lx-btn big" onClick={makeSong} disabled={creating}
            title={useVoice && voice ? `Blueprint, instrumental and vocals in ${voice.name}, saved to a new project` : "Blueprint and instrumental, saved to a new project"}>
            {creating === "song" ? "Making the song…" : "Make the whole song"}</button>
        </div>
      </div>
    </section>

    <section aria-label="Workspace" className="cp-workspace">
      <div className="cp-work-head">
        <div className="cp-work-title">
          <h1 className="cp-title">{view === "blueprint" && blueprint ? "Song blueprint" : "My workspace"}</h1>
          {(blueprint || songJob) && <Segment label="Workspace view" items={viewItems} value={viewSeg}
            onChange={id => setView(id === "song" ? (projectId ? "studio" : "making") : id)} />}
        </div>
        {view === "songs" && <label className="cp-search">
          <Icon name="search" size={16} />
          <input aria-label="Search songs" placeholder="Search" value={query} onChange={e => setQuery(e.target.value)} />
        </label>}
      </div>
      {view === "making" && <MakingSong status={songStatus} sung={useVoice && !!voice} />}
      {view === "studio" && projectId && <div className="cp-view">
        <SongStudio API={API} projectId={projectId} onEditBlueprint={editProjectBlueprint} />
      </div>}
      {view === "blueprint" && blueprint && <div className="cp-view">
        <BlueprintView API={API} blueprint={blueprint} setBlueprint={setBlueprint} />
      </div>}
      {view === "songs" && <><div className="cp-filters">
        {FILTERS.map(f => <button key={f} className="cp-pill" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      <div className="cp-song-list">
        {songs.length === 0 && <div className="lx-empty">
          Your songs appear here. <button className="lx-btn small" style={{ marginLeft: 8 }} onClick={() => go("music")}>Add a music folder</button>
        </div>}
        {visible.map(s => {
          const sm = s.summary || {};
          const active = s.id === nowPlayingId;
          const picking = influence === "picked" && useDna;
          const isPicked = picked.includes(s.id);
          return <button key={s.id} aria-pressed={picking ? isPicked : undefined}
            className={`cp-song${active ? " active" : ""}${isPicked && picking ? " picked" : ""}`}
            onClick={() => picking ? setPicked(p => isPicked ? p.filter(x => x !== s.id) : [...p, s.id].slice(0, 8)) : play(s)}
            aria-label={picking ? `${isPicked ? "Unpick" : "Pick"} ${s.title} as an influence` : `Play ${s.title}`}>
            <Cover id={s.id} label={sm.duration_seconds ? fmtTime(sm.duration_seconds) : null} />
            <div className="cp-song-meta">
              <div className="cp-song-top">
                <span className="cp-song-title">{s.title}</span>
                <span className={`cp-kind${s.kind === "stem-set" ? " stems" : ""}`}>
                  {s.kind === "stem-set" ? "STEMS" : "MIX"}</span>
                {s.variants.map(v => <span key={v} className="lx-tag">{v}</span>)}
                {influence === "picked" && useDna && isPicked && <span className="lx-tag">✓ influence</span>}
              </div>
              <div className="cp-song-line">
                {[sm.key, sm.roles_form, sm.vocal_range && `voice ${sm.vocal_range}`].filter(Boolean).join(" · ") || s.analysis_status}
              </div>
              <div className="cp-song-tags">
                {sm.bpm && <span className="lx-tag mono">{sm.bpm} BPM</span>}
                {sm.lufs != null && <span className="lx-tag mono">{sm.lufs} LUFS</span>}
                {s.has_lyrics && <span className="lx-tag">lyrics</span>}
              </div>
            </div>
          </button>;
        })}
      </div></>}
    </section>
  </div>;
}
