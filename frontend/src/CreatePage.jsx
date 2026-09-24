import React, { useEffect, useMemo, useState } from "react";
import { Cover, Icon, apiJson, catalogStats, fmtTime } from "./ui.jsx";

/* Create: the prompt / lyrics panel beside the workspace list.

   Song generation (blueprint → composer → guide singer) is roadmap AU-04+.
   Until then the Create button says so plainly instead of pretending, while
   everything around it (voice, DNA readouts, the catalog list, playback) is
   real. */

const FILTERS = ["All", "Stem sets", "Full mixes", "With vocal"];

export default function CreatePage({ API, go, play, nowPlayingId }) {
  const [mode, setMode] = useState("advanced");
  const [useDna, setUseDna] = useState(true);
  const [useVoice, setUseVoice] = useState(true);
  const [idea, setIdea] = useState("");
  const [lyrics, setLyrics] = useState("");
  const [styles, setStyles] = useState("");
  const [songs, setSongs] = useState([]);
  const [voice, setVoice] = useState(null);
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");

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
  const create = () => setNotice(
    "Song generation is the next build phase (Song Blueprint → composer → guide singer). " +
    "Your prompt, DNA and voice choices here are the inputs it will use.");

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
            onClick={() => setNotice("Turning a voice memo or rough demo into a full arrangement is a later build phase (Demo-to-Song).")}>
            <Icon name="plus" size={16} width={2.4} />Demo</button>
          <button className="au-btn" style={{ height: 48, borderRadius: 14, background: "#0b1f27", borderColor: "#1d5566", color: "#aef0ff" }} onClick={() => go("voice")}>
            <Icon name="voice" size={16} />My Voice</button>
          <button className="au-btn" style={{ height: 48, borderRadius: 14 }} onClick={() => go("music")}><Icon name="plus" size={16} width={2.4} />My songs</button>
        </div>

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

          <div className="au-card au-console" style={{ padding: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", borderBottom: "1px solid var(--hairline)", gap: 12 }}>
              <div><div className="au-label">Use my Artist DNA</div>
                <div style={{ fontSize: 12, color: "var(--steel)" }}>{stats ? `Tempo, keys, form and groove from ${stats.analysed} analysed songs` : "Add your songs in My Music first"}</div></div>
              <button role="switch" className="au-switch" aria-checked={useDna} aria-label="Use my Artist DNA" onClick={() => setUseDna(v => !v)} />
            </div>
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
        <button className="au-btn gold big" style={{ width: "100%" }} onClick={create}><Icon name="create" size={18} width={2.4} />Create</button>
      </div>
    </section>

    <section aria-label="Workspace" style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 28px 12px", gap: 12, flexWrap: "wrap" }}>
        <h1 className="au-title au-shine" style={{ fontSize: 22 }}>My workspace</h1>
        <label style={{ display: "flex", alignItems: "center", gap: 8, height: 40, padding: "0 14px", borderRadius: 12, background: "var(--panel)", border: "1px solid var(--edge)", color: "var(--steel)", width: 260, boxSizing: "border-box" }}>
          <Icon name="search" size={16} />
          <input aria-label="Search songs" placeholder="Search" value={query} onChange={e => setQuery(e.target.value)}
            style={{ background: "transparent", border: "none", outline: "none", color: "var(--ivory)", fontFamily: "inherit", fontSize: 14, width: "100%" }} />
        </label>
      </div>
      <div style={{ display: "flex", gap: 8, padding: "0 28px 14px", flexWrap: "wrap" }}>
        {FILTERS.map(f => <button key={f} className="au-pill" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      <div style={{ flexGrow: 1, minHeight: 0, overflowY: "auto", padding: "0 16px 16px" }}>
        {songs.length === 0 && <div style={{ padding: 40, textAlign: "center", color: "var(--steel)" }}>
          Your songs appear here. <button className="au-btn" style={{ marginLeft: 8 }} onClick={() => go("music")}>Add a music folder</button>
        </div>}
        {visible.map(s => {
          const sm = s.summary || {};
          const active = s.id === nowPlayingId;
          return <button key={s.id} onClick={() => play(s)} aria-label={`Play ${s.title}`} style={{
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
      </div>
    </section>
  </div>;
}
