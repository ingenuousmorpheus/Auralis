import React, { useEffect, useState } from "react";
import { apiJson } from "./ui.jsx";

/* Era & style controls for Create, backed by the R&B Theory Atlas.
   Shows documented, transposable candidates with sources and a key fitted to
   the user's voice. Nothing here plays or generates audio. */

const HARMONY = [["", "Any"], ["familiar", "Familiar"], ["rich", "Rich"], ["gospel", "Gospel-influenced"],
  ["dark", "Dark"], ["romantic", "Romantic"], ["experimental", "Experimental"]];
const VOCAL = [["", "Any"], ["smooth", "Smooth"], ["conversational", "Conversational"], ["melismatic", "Melismatic"],
  ["falsetto", "Falsetto-heavy"], ["power_ballad", "Power ballad"], ["adlib_heavy", "Ad-lib heavy"]];
const GROOVE = [["", "Any"], ["straight", "Straight"], ["laid_back", "Laid-back"], ["deep_pocket", "Deep pocket"],
  ["swing", "Swing"], ["hiphop", "Hip-hop influenced"]];

function Status({ status }) {
  const sourced = status === "sourced";
  return <span className="au-chip mono" title={sourced ? "Stated in the cited source" : "Starting hypothesis, not yet validated"}
    style={{ color: sourced ? "var(--signal)" : "var(--gold-light)", background: "#11151c" }}>{status}</span>;
}

function Sources({ list }) {
  return <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
    {list.map(s => s.url
      ? <a key={s.id} href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: "var(--holo-soft)" }}>{s.title}</a>
      : <span key={s.id} style={{ fontSize: 11, color: "var(--steel-dim)" }}>{s.title}</span>)}
  </div>;
}

function Select({ id, label, value, onChange, options }) {
  return <label htmlFor={id} style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
    <span className="au-caption">{label}</span>
    <select id={id} value={value} onChange={e => onChange(e.target.value)} className="au-input" style={{ height: 38, padding: "0 10px" }}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  </label>;
}

export default function AtlasPanel({ API }) {
  const [open, setOpen] = useState(false);
  const [eraList, setEraList] = useState([]);
  const [era, setEra] = useState("80s_quiet_storm");
  const [harmony, setHarmony] = useState("");
  const [vocal, setVocal] = useState("");
  const [groove, setGroove] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { if (open && !eraList.length) apiJson(`${API}/theory/eras`).then(setEraList).catch(e => setError(e.message)); }, [open]);
  useEffect(() => {
    if (!open) return;
    const q = new URLSearchParams({ era, ...(harmony && { harmony }), ...(vocal && { vocal }), ...(groove && { groove }) });
    apiJson(`${API}/theory/candidates?${q}`).then(r => { setResult(r); setError(""); }).catch(e => setError(e.message));
  }, [open, era, harmony, vocal, groove]);

  return <div className="au-card au-console" style={{ padding: 0 }}>
    <button onClick={() => setOpen(v => !v)} aria-expanded={open} style={{
      width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "13px 16px",
      background: "transparent", border: "none", color: "inherit", cursor: "pointer", font: "inherit", textAlign: "left",
    }}>
      <span><span className="au-label">Era &amp; style</span>
        <span style={{ display: "block", fontSize: 12, color: "var(--steel)" }}>R&amp;B Theory Atlas: documented options, keyed to your voice</span></span>
      <span aria-hidden="true" style={{ color: "var(--gold-light)", fontSize: 18 }}>{open ? "−" : "+"}</span>
    </button>

    {open && <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
        <Select id="atlas-era" label="Era" value={era} onChange={setEra}
          options={eraList.length ? eraList.map(e => [e.id, e.name]) : [[era, "Loading…"]]} />
        <Select id="atlas-harmony" label="Harmony" value={harmony} onChange={setHarmony} options={HARMONY} />
        <Select id="atlas-vocal" label="Vocal approach" value={vocal} onChange={setVocal} options={VOCAL} />
        <Select id="atlas-groove" label="Groove" value={groove} onChange={setGroove} options={GROOVE} />
      </div>
      {error && <div role="alert" style={{ color: "var(--warn)", fontSize: 13 }}>{error}</div>}

      {result && <>
        <div style={{ fontSize: 12, color: "var(--steel)", lineHeight: 1.5 }}>
          <b style={{ color: "var(--ivory)" }}>{result.era.name}</b> · {result.era.bpm_band[0]}–{result.era.bpm_band[1]} BPM · {result.era.harmonic_rhythm} <Status status={result.era.status} />
        </div>

        <div>
          <div className="au-caption" style={{ marginBottom: 6 }}>Harmony candidates</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {result.harmony.map(h => <div key={h.id} style={{ border: "1px solid var(--edge)", borderRadius: 12, padding: "10px 12px", background: "var(--deck)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <span style={{ fontWeight: 800, fontSize: 13 }}>{h.name}</span><Status status={h.status} />
              </div>
              <div className="au-mono" style={{ color: "var(--gold-light)", fontSize: 14, margin: "6px 0" }}>{h.roman.join("  –  ")}</div>
              {h.keys[0] && <div style={{ fontSize: 12 }}>
                <span style={{ color: "var(--holo-soft)", fontWeight: 700 }}>Try {h.keys[0].key}</span>
                <span style={{ color: "var(--steel)" }}> · {h.keys[0].why}</span>
              </div>}
              <div style={{ fontSize: 12, color: "var(--steel)", marginTop: 4 }}>{h.comment}</div>
              <Sources list={h.sources} />
            </div>)}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 8 }}>
          {result.vocal[0] && <div style={{ border: "1px solid var(--edge)", borderRadius: 12, padding: "10px 12px" }}>
            <div className="au-caption">Vocal · {result.vocal[0].section}</div>
            <div style={{ fontWeight: 700, fontSize: 13, marginTop: 4 }}>{result.vocal[0].name}</div>
            <div style={{ fontSize: 12, color: "var(--steel)" }}>{result.vocal[0].contour} · {result.vocal[0].phrase_bars[0]}–{result.vocal[0].phrase_bars[1]} bar phrases</div>
            <Status status={result.vocal[0].status} />
          </div>}
          {result.groove[0] && <div style={{ border: "1px solid var(--edge)", borderRadius: 12, padding: "10px 12px" }}>
            <div className="au-caption">Groove</div>
            <div style={{ fontWeight: 700, fontSize: 13, marginTop: 4 }}>{result.groove[0].name}</div>
            <div style={{ fontSize: 12, color: "var(--steel)" }}>{result.groove[0].bpm_band[0]}–{result.groove[0].bpm_band[1]} BPM · {result.groove[0].push_pull}</div>
            <Status status={result.groove[0].status} />
          </div>}
        </div>
        <div style={{ fontSize: 11, color: "var(--steel-dim)" }}>{result.originality}</div>
      </>}
    </div>}
  </div>;
}
