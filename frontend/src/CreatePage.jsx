import React, { useEffect, useMemo, useState } from "react";
import AtlasPanel from "./AtlasPanel.jsx";
import BlueprintView from "./BlueprintView.jsx";
import SongStudio from "./SongStudio.jsx";
import DemoPanel from "./DemoPanel.jsx";
import { Cover, Icon, apiJson, catalogStats, fmtTime } from "./ui.jsx";

/* Create: the prompt / lyrics panel beside the workspace.

   Create builds a Song Blueprint (AU-04) from the prompt, lyrics, Era & style
   choices, Artist DNA and the trained voice range, and shows it editable in
   the workspace. Audio (composer → guide singer → voice) is the next phase,
   so nothing here pretends to render a song. */

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
  return <div style={{ padding: "0 28px 24px" }}>
    <div className="bp-panel" role="status">
      <div className="au-caption">Making your song · {Math.round(status?.pct || 0)}%</div>
      <div style={{ height: 6, borderRadius: 3, background: "var(--edge)", overflow: "hidden", margin: "10px 0" }}>
        <div style={{ width: `${status?.pct || 0}%`, height: "100%", background: "var(--gold)", transition: "width 0.4s" }} /></div>
      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
        {list.map(([k, label], i) => <li key={k} style={{ fontSize: 13, color: i < current ? "var(--signal)" : i === current ? "var(--ivory)" : "var(--steel-dim)" }}>
          {i < current ? "✓" : i === current ? "▸" : "·"} {label}</li>)}
      </ol>
      <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 10 }}>{status?.stage}</div>
      {sung && <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>Singing takes several minutes; close big apps so the voice engine has memory.</div>}
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
    apiJson(`${API}/voice/profiles`).then(list =>
      setVoice(list.find(p => p.training_status === "trained") || list[0] || null)).catch(() => {});
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

  return <div className="au-page" style={{ display: "grid", gridTemplateColumns: "452px minmax(0, 1fr)" }}>
    <section aria-label="Create a song" style={{ borderRight: "1px solid var(--hairline)", display: "flex", flexDirection: "column", minHeight: 0, background: "var(--deck)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px 14px" }}>
        <div className="au-segment" role="tablist" aria-label="Create mode">
          <button role="tab" aria-selected={mode === "simple"} onClick={() => setMode("simple")}>Simple</button>
          <button role="tab" aria-selected={mode === "advanced"} onClick={() => setMode("advanced")}>Advanced</button>
        </div>
        <span className="au-mono" style={{ fontSize: 12, color: "var(--steel)", border: "1px solid var(--edge-strong)", borderRadius: 999, padding: "6px 12px" }}>local engine</span>
      </div>

      <div style={{ flexGrow: 1, minHeight: 0, overflowY: "auto", padding: "0 20px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>
          <button className="au-btn" style={{ height: 48, borderRadius: 14 }}
            onClick={() => setShowDemo(v => !v)} aria-expanded={showDemo}>
            <Icon name="plus" size={16} width={2.4} />Demo</button>
          <button className="au-btn" style={{ height: 48, borderRadius: 14, background: "#0b1f27", borderColor: "#1d5566", color: "#aef0ff" }} onClick={() => go("voice")}>
            <Icon name="voice" size={16} />My Voice</button>
          <button className="au-btn" style={{ height: 48, borderRadius: 14 }} onClick={() => go("music")}><Icon name="plus" size={16} width={2.4} />My songs</button>
        </div>

        {showDemo && <DemoPanel API={API} prompt={mode === "simple" ? idea : [styles, idea].filter(x => x.trim()).join(", ")}
          lyrics={mode === "advanced" ? lyrics : ""} useDna={useDna} useVoice={useVoice} era={mode === "advanced" ? style.era : ""}
          onClose={() => setShowDemo(false)}
          onBlueprint={bp => { setBlueprint(bp); setView("blueprint"); setShowDemo(false);
            setNotice(`Built around your demo: ${bp.demo.note_count} notes kept as the ${bp.demo.role} at ${bp.tempo} BPM in ${bp.key}.`); }} />}
        {mode === "simple" && <div className="au-card au-console" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label htmlFor="idea" className="au-label">Song description</label>
          <textarea id="idea" rows={7} className="au-field" style={{ fontSize: 15 }} value={idea} onChange={e => setIdea(e.target.value)}
            placeholder="Dark late-night R&B, big chorus, feels like my last three songs without copying them" />
        </div>}

        {mode === "advanced" && <>
          <div className="au-card au-console" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <label htmlFor="lyrics" className="au-label">Lyrics</label>
              <span className="au-mono" style={{ fontSize: 11, color: "var(--steel)" }}>{lyrics.trim() ? `${lyrics.trim().split(/\n+/).length} lines` : "instrumental if empty"}</span>
            </div>
            <textarea id="lyrics" rows={7} className="au-field" value={lyrics} onChange={e => setLyrics(e.target.value)}
              placeholder="Write or paste lyrics. Leave empty for an instrumental." />
          </div>

          <div className="au-card au-console" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <label htmlFor="styles" className="au-label">Styles</label>
            <input id="styles" className="au-field" value={styles} onChange={e => setStyles(e.target.value)}
              placeholder="late-night R&B, warm low end, big chorus" />
            {dnaTags.length > 0 && <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--holo-soft)", letterSpacing: "0.04em" }}>FROM YOUR MUSIC</span>
              {dnaTags.map(tag => <button key={tag} onClick={() => addTag(tag)} style={{
                fontSize: 12, fontWeight: 600, padding: "6px 10px", borderRadius: 999, cursor: "pointer",
                border: "1px solid #1c4553", background: "#0b1b21", color: "#bdf3ff", fontFamily: "inherit",
              }}>+ {tag}</button>)}
            </div>}
          </div>

          <AtlasPanel API={API} value={style} onChange={setStyle} />

          <div className="au-card au-console" style={{ padding: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", borderBottom: "1px solid var(--hairline)", gap: 12 }}>
              <div><div className="au-label">Use my Artist DNA</div>
                <div style={{ fontSize: 12, color: "var(--steel)" }}>{stats ? `Tempo, keys, form and groove from ${stats.analysed} analysed songs` : "Add your songs in My Music first"}</div></div>
              <button role="switch" className="au-switch" aria-checked={useDna} aria-label="Use my Artist DNA" onClick={() => setUseDna(v => !v)} />
            </div>
            {useDna && <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", borderBottom: "1px solid var(--hairline)", flexWrap: "wrap" }}>
              <span className="au-caption">Influence</span>
              <div className="au-segment" role="tablist" aria-label="Influence from my songs">
                {[["all", "All my songs"], ["closest", "Closest 5"], ["picked", "Songs I pick"]].map(([k, l]) =>
                  <button key={k} role="tab" aria-selected={influence === k} onClick={() => { setInfluence(k); if (k === "picked") setView("songs"); }}>{l}</button>)}
              </div>
              {influence === "picked" && <span style={{ fontSize: 12, color: "var(--steel)" }}>
                {picked.length ? `${picked.length} picked` : "click songs on the right to pick them"}</span>}
            </div>}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", borderBottom: "1px solid var(--hairline)", gap: 12 }}>
              <div><div className="au-label">Sing it in my voice</div>
                <div style={{ fontSize: 12, color: "var(--steel)" }}>{voice ? `Guide singer → ${voice.name} → pitch + vocal finish` : "Create a voice profile in My Voice"}</div></div>
              <button role="switch" className="au-switch" aria-checked={useVoice} aria-label="Sing it in my voice" onClick={() => setUseVoice(v => !v)} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, padding: "13px 16px" }}>
              <div><div className="au-caption">Vocals</div><div style={{ fontSize: 13, fontWeight: 700, marginTop: 3 }}>Lead + doubles</div></div>
              <div><div className="au-caption">Mix</div><div style={{ fontSize: 13, fontWeight: 700, marginTop: 3 }}>Vocal-forward R&amp;B</div></div>
              <div><div className="au-caption">Master</div><div className="au-mono" style={{ fontSize: 13, marginTop: 3 }}>−14 LUFS</div></div>
            </div>
          </div>
        </>}

        {notice && <div role="status" className="au-card" style={{ borderColor: "rgba(212,175,95,0.45)", fontSize: 13, lineHeight: 1.55, color: "var(--gold-light)" }}>{notice}</div>}
      </div>

      <div style={{ padding: "14px 20px 18px", borderTop: "1px solid var(--hairline)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 8 }}>
          <button className="au-btn gold big" onClick={create} disabled={creating} title="Write an editable blueprint first">
            <Icon name="create" size={18} width={2.4} />{creating === "blueprint" ? "Writing…" : blueprint ? "New blueprint" : "Create"}</button>
          <button className="au-btn big" onClick={makeSong} disabled={creating}
            title={useVoice && voice ? `Blueprint, instrumental and vocals in ${voice.name}, saved to a new project` : "Blueprint and instrumental, saved to a new project"}>
            {creating === "song" ? "Making the song…" : "Make the whole song"}</button>
        </div>
      </div>
    </section>

    <section aria-label="Workspace" style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 28px 12px", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <h1 className="au-title au-shine" style={{ fontSize: 22 }}>{view === "blueprint" && blueprint ? "Song blueprint" : "My workspace"}</h1>
          {(blueprint || songJob) && <div className="au-segment" role="tablist" aria-label="Workspace view">
            {blueprint && <button role="tab" aria-selected={view === "blueprint"} onClick={() => setView("blueprint")}>Blueprint</button>}
            {songJob && <button role="tab" aria-selected={view === "making" || view === "studio"} onClick={() => setView(projectId ? "studio" : "making")}>Song</button>}
            <button role="tab" aria-selected={view === "songs"} onClick={() => setView("songs")}>My songs</button>
          </div>}
        </div>
        {view === "songs" && <label style={{ display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 14px", borderRadius: 12, background: "var(--panel)", border: "1px solid var(--edge)", color: "var(--steel)", width: 260, boxSizing: "border-box" }}>
          <Icon name="search" size={16} />
          <input aria-label="Search songs" placeholder="Search" value={query} onChange={e => setQuery(e.target.value)}
            style={{ background: "transparent", border: "none", outline: "none", color: "var(--ivory)", fontFamily: "inherit", fontSize: 14, width: "100%" }} />
        </label>}
      </div>
      {view === "making" && <MakingSong status={songStatus} sung={useVoice && !!voice} />}
      {view === "studio" && projectId && <div style={{ flexGrow: 1, minHeight: 0, overflowY: "auto" }}>
        <SongStudio API={API} projectId={projectId} onEditBlueprint={editProjectBlueprint} />
      </div>}
      {view === "blueprint" && blueprint && <div style={{ flexGrow: 1, minHeight: 0, overflowY: "auto" }}>
        <BlueprintView API={API} blueprint={blueprint} setBlueprint={setBlueprint} />
      </div>}
      {view === "songs" && <><div style={{ display: "flex", gap: 8, padding: "0 28px 14px", flexWrap: "wrap" }}>
        {FILTERS.map(f => <button key={f} className="au-pill" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      <div style={{ flexGrow: 1, minHeight: 0, overflowY: "auto", padding: "0 16px 16px" }}>
        {songs.length === 0 && <div style={{ padding: 40, textAlign: "center", color: "var(--steel)" }}>
          Your songs appear here. <button className="au-btn" style={{ marginLeft: 8 }} onClick={() => go("music")}>Add a music folder</button>
        </div>}
        {visible.map(s => {
          const sm = s.summary || {};
          const active = s.id === nowPlayingId;
          const picking = influence === "picked" && useDna;
          const isPicked = picked.includes(s.id);
          return <button key={s.id} aria-pressed={picking ? isPicked : undefined}
            onClick={() => picking ? setPicked(p => isPicked ? p.filter(x => x !== s.id) : [...p, s.id].slice(0, 8)) : play(s)}
            aria-label={picking ? `${isPicked ? "Unpick" : "Pick"} ${s.title} as an influence` : `Play ${s.title}`} style={{
            outline: isPicked && picking ? "1px solid var(--gold)" : "none",
            width: "100%", display: "flex", alignItems: "center", gap: 16, padding: "10px 12px", borderRadius: 16,
            border: "none", cursor: "pointer", fontFamily: "inherit", color: "inherit", textAlign: "left",
            background: active ? "var(--panel-raised)" : "transparent",
          }}>
            <Cover id={s.id} label={sm.duration_seconds ? fmtTime(sm.duration_seconds) : null} />
            <div style={{ minWidth: 0, flexGrow: 1, display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0 }}>
                <span style={{ fontSize: 16, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.title}</span>
                <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: s.kind === "stem-set" ? "var(--signal)" : "var(--steel)", flexShrink: 0 }}>
                  {s.kind === "stem-set" ? "STEMS" : "MIX"}</span>
                {s.variants.map(v => <span key={v} className="au-chip" style={{ flexShrink: 0 }}>{v}</span>)}
                {influence === "picked" && useDna && isPicked && <span className="au-chip holo" style={{ flexShrink: 0 }}>✓ influence</span>}
              </div>
              <div style={{ fontSize: 13, color: "var(--steel)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {[sm.key, sm.roles_form, sm.vocal_range && `voice ${sm.vocal_range}`].filter(Boolean).join(" · ") || s.analysis_status}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {sm.bpm && <span className="au-chip mono">{sm.bpm} BPM</span>}
                {sm.lufs != null && <span className="au-chip mono">{sm.lufs} LUFS</span>}
                {s.has_lyrics && <span className="au-chip holo">lyrics</span>}
              </div>
            </div>
          </button>;
        })}
      </div></>}
    </section>
  </div>;
}
