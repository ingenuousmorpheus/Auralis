import React, { useEffect, useState } from "react";
import { apiJson } from "./ui.jsx";

/* Song studio (AU-10, roadmap Screen 4): a finished song's stems from its
   project, each with play, level, mute and solo; Remix rebuilds the master
   from those stems through the Auralis mixer and mastering and saves it as a
   new master in the project. Works after restarts: everything is in the project. */

const PART_NAMES = { drums: "Drums", bass: "Bass", keys: "Keys", pad: "Pad", fx: "FX", atmosphere: "Atmosphere",
  lead_vocal: "Lead vocal", backing_vocals: "Backing vocals" };
const ORDER = ["lead_vocal", "backing_vocals", "drums", "bass", "keys", "pad", "atmosphere", "fx"];

export default function SongStudio({ API, projectId, onEditBlueprint }) {
  const [project, setProject] = useState(null);
  const [stems, setStems] = useState([]);
  const [levels, setLevels] = useState({});
  const [bvParts, setBvParts] = useState([]);
  const [bvLevels, setBvLevels] = useState({});
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    const [p, s] = await Promise.all([apiJson(`${API}/projects/${projectId}`), apiJson(`${API}/projects/${projectId}/stems`)]);
    setProject(p);
    setStems(s.sort((a, b) => ORDER.indexOf(a.part) - ORDER.indexOf(b.part)));
    setBvParts(await apiJson(`${API}/projects/${projectId}/backing-parts`).catch(() => []));
  };
  useEffect(() => { load().catch(e => setError(e.message)); }, [API, projectId]);
  useEffect(() => {
    if (!job) return;
    let stop = false;
    const tick = async () => {
      const st = await apiJson(`${API}/jobs/${job}`).catch(e => ({ stage: "error", error: e.message }));
      if (stop) return;
      setStatus(st);
      if (st.stage === "done") load();
      else if (st.stage === "error") setError(st.error || "Remix failed.");
      else setTimeout(tick, 900);
    };
    tick();
    return () => { stop = true; };
  }, [job]);

  const set = (id, patch) => setLevels(l => ({ ...l, [id]: { ...(l[id] || {}), ...patch } }));
  const remix = async () => {
    setError(""); setStatus(null);
    try {
      const r = await apiJson(`${API}/projects/${projectId}/remix`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ levels, backing_levels: Object.keys(bvLevels).length ? bvLevels : null }) });
      setJob(r.job_id);
    } catch (e) { setError(e.message); }
  };
  if (!project) return <div className="vp-empty">{error || "Loading the song…"}</div>;
  const masters = project.assets.filter(a => a.kind === "master").slice().reverse();
  const running = status && status.stage !== "done" && status.stage !== "error";
  const anySolo = Object.values(levels).some(v => v.solo);
  const asset = id => `${API}/projects/${projectId}/assets/${id}`;

  return <div className="bp" style={{ paddingTop: 4 }}>
    <div className="bp-head">
      <div>
        <div className="au-caption">Song studio · project</div>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 20, marginTop: 4 }}>{project.name}</div>
        <div style={{ fontSize: 12, color: "var(--steel)" }}>Every stem is saved in the project; remixes are added as new masters.</div>
      </div>
      {onEditBlueprint && <button className="au-btn" onClick={onEditBlueprint}>Edit blueprint</button>}
    </div>
    {error && <div role="alert" className="bp-alert warn">{error}</div>}

    {masters.length > 0 && <div className="bp-panel">
      <div className="au-caption">Masters</div>
      {masters.map((m, i) => <div key={m.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 170px) minmax(0, 1fr) auto", gap: 10, alignItems: "center", marginTop: 8 }}>
        <span style={{ fontSize: 13, fontWeight: i === 0 ? 800 : 500 }}>{m.name}{m.metadata?.after_lufs != null ? ` · ${m.metadata.after_lufs} LUFS` : ""}</span>
        <audio controls preload="none" src={asset(m.id)} style={{ width: "100%", height: 34 }} aria-label={`Play ${m.name}`} />
        <a className="bp-icon" href={asset(m.id)} download style={{ display: "inline-flex", alignItems: "center", textDecoration: "none" }}>⤓ WAV</a>
      </div>)}
    </div>}

    <div className="bp-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div className="au-caption">Stems</div>
        <button className="au-btn gold" onClick={remix} disabled={running || !stems.length}>{running ? "Remixing…" : "Remix and master"}</button>
      </div>
      {running && <div role="status" style={{ fontSize: 12, color: "var(--steel)", marginTop: 6 }}>{status.stage} · {Math.round(status.pct)}%</div>}
      {status?.stage === "done" && <div role="status" style={{ fontSize: 12, color: "var(--signal)", marginTop: 6 }}>
        ✓ Saved {status.result.name} ({status.result.stems.length} stems, {status.result.after_lufs} LUFS)</div>}
      {stems.map(s => {
        const cfg = levels[s.asset_id] || {};
        const silent = anySolo ? !cfg.solo : cfg.mute;
        return <div key={s.asset_id} style={{ display: "grid", gridTemplateColumns: "120px minmax(0, 1fr) 150px auto", gap: 10, alignItems: "center",
          marginTop: 10, opacity: silent ? 0.45 : 1 }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{PART_NAMES[s.part] || s.part}</span>
          <audio controls preload="none" src={asset(s.asset_id)} style={{ width: "100%", height: 32 }} aria-label={`Play ${s.part}`} />
          <label className="bp-row" style={{ gap: 6 }}>
            <input type="range" min={-12} max={12} step={0.5} value={cfg.gain_db ?? 0} aria-label={`${s.part} level`}
              onChange={e => set(s.asset_id, { gain_db: +e.target.value })} />
            <span className="au-mono" style={{ width: 44 }}>{(cfg.gain_db ?? 0) > 0 ? "+" : ""}{cfg.gain_db ?? 0} dB</span>
          </label>
          <span style={{ display: "flex", gap: 4 }}>
            <button className="bp-icon" aria-pressed={!!cfg.mute} onClick={() => set(s.asset_id, { mute: !cfg.mute })} title="Mute">M</button>
            <button className="bp-icon" aria-pressed={!!cfg.solo} onClick={() => set(s.asset_id, { solo: !cfg.solo })} title="Solo">S</button>
          </span>
        </div>;
      })}
      {bvParts.length > 0 && <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700 }}>Backing vocal parts</summary>
        <div style={{ fontSize: 12, color: "var(--steel)", margin: "6px 0" }}>Rebalance the parts inside the backing stack (no re-singing), then Remix and master.</div>
        {bvParts.map(p => {
          const v = bvLevels[p.part] ?? 0;
          const muted = v <= -60;
          return <div key={p.asset_id} style={{ display: "grid", gridTemplateColumns: "120px minmax(0, 1fr) 150px auto", gap: 10, alignItems: "center", marginTop: 8, opacity: muted ? 0.45 : 1 }}>
            <span style={{ fontSize: 13 }}>{{ double_l: "Double (left)", double_r: "Double (right)", harmony_high: "Harmony (high)", harmony_low: "Harmony (low)", adlibs: "Ad-libs" }[p.part] || p.part}</span>
            <audio controls preload="none" src={asset(p.asset_id)} style={{ width: "100%", height: 30 }} aria-label={`Play ${p.part}`} />
            <label className="bp-row" style={{ gap: 6 }}>
              <input type="range" min={-12} max={6} step={1} value={muted ? -12 : v} disabled={muted} aria-label={`${p.part} level`}
                onChange={e => setBvLevels(l => ({ ...l, [p.part]: +e.target.value }))} />
              <span className="au-mono" style={{ width: 44 }}>{muted ? "off" : `${v > 0 ? "+" : ""}${v} dB`}</span>
            </label>
            <button className="bp-icon" aria-pressed={muted} title="Mute this part"
              onClick={() => setBvLevels(l => ({ ...l, [p.part]: muted ? 0 : -60 }))}>M</button>
          </div>;
        })}
      </details>}
    </div>
  </div>;
}
