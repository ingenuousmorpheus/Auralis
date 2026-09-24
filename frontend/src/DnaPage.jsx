import React, { useEffect, useState } from "react";
import { Icon, apiJson } from "./ui.jsx";

/* Artist DNA: what recurs across the user's own catalog, with the evidence
   for each trait. Computed live from the songs switched on in My Music. */

const TITLES = {
  tempo: "Tempo", key: "Keys", harmony: "Harmony", form: "Song form",
  groove: "Groove", melody: "Melody", production: "Production", voice: "Your voice",
};
const ORDER = ["tempo", "key", "harmony", "form", "groove", "melody", "voice", "production"];

function Badge({ level }) {
  if (!level) return null;
  const color = level === "strong" ? "var(--signal)" : level === "moderate" ? "var(--gold-light)" : "var(--warn)";
  return <span className="au-chip mono" style={{ color, background: "#11151c" }}>{level}</span>;
}

function Bars({ items }) {
  const max = Math.max(...items.map(i => i.value), 0.0001);
  return <div style={{ display: "grid", gap: 6 }}>
    {items.map(i => <div key={i.label} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) 2fr 44px", gap: 8, alignItems: "center", fontSize: 12 }}>
      <span style={{ overflowWrap: "anywhere" }}>{i.label}</span>
      <div style={{ height: 7, borderRadius: 99, background: "#161b24", overflow: "hidden" }}>
        <div style={{ width: `${(i.value / max) * 100}%`, height: "100%", background: "linear-gradient(90deg, #8a6a2c, #e9cf8a)" }} />
      </div>
      <span className="au-mono" style={{ textAlign: "right", color: "var(--steel)" }}>{Math.round(i.value * 100)}%</span>
    </div>)}
  </div>;
}

function RangeBar({ voice, melody }) {
  // MIDI 40 (E2) to 84 (C6): writing range drawn inside the trained range.
  const lo = 40, hi = 84;
  const x = m => `${((m - lo) / (hi - lo)) * 100}%`;
  const vLo = melody.range_low_midi - voice.footroom_semitones;
  const vHi = melody.range_high_midi + voice.headroom_semitones;
  return <div style={{ position: "relative", height: 46, marginTop: 6 }} role="img"
    aria-label={`Trained voice ${voice.trained_range}, songs written ${voice.writing_range}`}>
    <div style={{ position: "absolute", top: 8, left: x(vLo), width: `calc(${x(vHi)} - ${x(vLo)})`, height: 12, borderRadius: 6, background: "#0d2a33", border: "1px solid #1d5566" }} />
    <div style={{ position: "absolute", top: 10, left: x(melody.range_low_midi), width: `calc(${x(melody.range_high_midi)} - ${x(melody.range_low_midi)})`, height: 8, borderRadius: 4, background: "var(--gold)" }} />
    <div className="au-mono" style={{ position: "absolute", top: 26, left: 0, right: 0, display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--steel-dim)" }}>
      <span>E2</span><span>C4</span><span>C6</span>
    </div>
  </div>;
}

function TraitBody({ id, t }) {
  if (id === "tempo") return <Bars items={Object.entries(t.bands).map(([label, value]) => ({ label: `${label} BPM`, value }))} />;
  if (id === "key") return <>
    <Bars items={t.families.map(f => ({ label: f.signature, value: f.share }))} />
    <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 8 }}>Most detected keys: {t.exact_keys.slice(0, 3).map(k => k.key).join(", ")}</div>
  </>;
  if (id === "harmony") return <div style={{ display: "grid", gap: 10 }}>
    {Object.entries(t.loops).map(([mode, loops]) => <div key={mode}>
      <div className="au-caption" style={{ marginBottom: 6 }}>{mode}-key loops</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {loops.slice(0, 4).map(l => <span key={l.progression} className="mm-chip">{l.progression}</span>)}
      </div>
    </div>)}
  </div>;
  if (id === "form") return <div style={{ display: "grid", gap: 8 }}>
    {t.common_forms.map(f => <div key={f.form} className="au-mono" style={{ fontSize: 12, color: "var(--gold-light)" }}>{f.form}</div>)}
    <div style={{ fontSize: 12, color: "var(--steel)" }}>
      Typical lengths: {Object.entries(t.section_bars).filter(([r]) => r !== "section").map(([r, b]) => `${r} ${b}`).join(" · ")} bars
      {t.chorus_lift != null && <> · chorus lift {t.chorus_lift > 0 ? "+" : ""}{Math.round(t.chorus_lift * 100)}% energy</>}
    </div>
  </div>;
  if (id === "groove") return <div className="mm-facts">
    <div className="mm-fact"><div className="au-caption">Off the beat</div><div className="mm-fact-value">{Math.round(t.syncopation * 100)}%</div></div>
    <div className="mm-fact"><div className="au-caption">Hits / beat</div><div className="mm-fact-value">{t.onsets_per_beat}</div></div>
  </div>;
  if (id === "melody") return <div className="mm-facts">
    <div className="mm-fact"><div className="au-caption">Range</div><div className="mm-fact-value">{t.range_low}–{t.range_high}</div></div>
    <div className="mm-fact"><div className="au-caption">Motion</div><div className="mm-fact-value">{Math.round(t.motion.step * 100)}% steps</div>
      <div className="mm-fact-note">{Math.round(t.motion.repeat * 100)}% repeats · {Math.round(t.motion.leap * 100)}% leaps</div></div>
  </div>;
  if (id === "production") return <div className="mm-facts">
    <div className="mm-fact"><div className="au-caption">Loudness</div><div className="mm-fact-value">{t.lufs} LUFS</div></div>
    <div className="mm-fact"><div className="au-caption">Vocal vs music</div><div className="mm-fact-value">{t.vocal_to_music_db ?? "—"} dB</div></div>
  </div>;
  return null;
}

export default function DnaPage({ API, go, play }) {
  const [dna, setDna] = useState(null);
  const [error, setError] = useState("");

  const load = () => apiJson(`${API}/artist/dna`).then(d => { setDna(d); setError(""); }).catch(e => setError(e.message));
  useEffect(() => { load(); }, [API]);

  if (error) return <div className="au-page-scroll"><div className="au-card" role="alert" style={{ color: "var(--warn)" }}>{error}</div></div>;
  if (!dna) return <div className="au-page-scroll"><div className="au-sub">Reading your catalog…</div></div>;
  if (dna.empty) return <div className="au-page-scroll">
    <h1 className="au-title au-shine">Artist DNA</h1>
    <p className="au-sub">No analysed songs are switched on yet.</p>
    <button className="au-btn gold" style={{ marginTop: 16 }} onClick={() => go("music")}>Open My Music</button>
  </div>;

  const m = dna.method;
  const traits = dna.traits;
  return <div className="au-page-scroll">
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div>
        <h1 className="au-title au-shine">Artist DNA</h1>
        <p className="au-sub">How you write, measured from {m.songs_used} of your songs ({m.song_families} distinct songs, {m.stem_sets_used} stem sets).
          Nothing here is generated.</p>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="au-btn" onClick={() => go("music")}>Choose songs</button>
        <button className="au-btn" onClick={load}>Refresh</button>
      </div>
    </div>

    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14, marginTop: 20 }}>
      {ORDER.filter(id => traits[id]).map(id => {
        const t = traits[id];
        return <section key={id} className="au-card au-console" style={{ display: "flex", flexDirection: "column", gap: 12 }} aria-labelledby={`dna-${id}`}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <h2 id={`dna-${id}`} className="au-caption" style={{ margin: 0, color: id === "voice" ? "var(--holo-soft)" : "var(--gold-light)" }}>{TITLES[id]}</h2>
            <Badge level={t.confidence} />
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, lineHeight: 1.4 }}>{t.summary}</div>
          {id === "voice" && traits.melody ? <RangeBar voice={t} melody={traits.melody} /> : <TraitBody id={id} t={t} />}
          {t.note && <div style={{ fontSize: 12, color: "var(--steel)", lineHeight: 1.5 }}>{t.note}</div>}
          {t.evidence?.length > 0 && <div>
            <div className="au-caption" style={{ marginBottom: 6 }}>Strongest evidence</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {t.evidence.map(e => <button key={e.song_id} className="au-pill" style={{ height: 30 }}
                onClick={() => play({ id: e.song_id, title: e.title })} aria-label={`Play ${e.title}`}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>{e.title}</span>
              </button>)}
            </div>
          </div>}
        </section>;
      })}
    </div>

    <div className="au-card" style={{ marginTop: 16, fontSize: 13, color: "var(--steel)", lineHeight: 1.6 }}>
      <b style={{ color: "var(--ivory)" }}>How songs are weighted.</b> Stem sets count {m.weights.kind["stem-set"]}×, full mixes {m.weights.kind.mix}×
      (stems give cleaner melody, groove and form). Covers count {m.weights.variant.cover}× and type-beat packages {m.weights.variant["type-beat"]}×.
      Versions of one song (vocal, instrumental, remixes) share one song's weight. {m.songs_switched_off > 0
        ? `${m.songs_switched_off} song(s) are switched off and ignored.`
        : "Every song is switched on. Switch off anything that isn't your writing in My Music."}
    </div>
  </div>;
}
