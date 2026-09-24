import React, { useEffect, useRef, useState } from "react";
import "./Projects.css";

/* My Projects: every song's sources, stems, vocals, mixes, masters and reports
   in one folder on this PC, reopenable after Auralis restarts. */

const KIND_ORDER = [
  ["source", "Sources"],
  ["stem", "Stems"],
  ["vocal", "Vocals"],
  ["mix", "Mixes"],
  ["master", "Masters"],
  ["report", "Reports"],
  ["generated", "Generated"],
];
const AUDIO = /\.(wav|flac|mp3|aif|aiff|ogg)$/i;

function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function size(bytes) {
  return bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`;
}

export default function ProjectsPanel({ API, onBack }) {
  const [projects, setProjects] = useState([]);
  const [current, setCurrent] = useState(null);
  const [name, setName] = useState("");
  const [uploadKind, setUploadKind] = useState("source");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef();

  async function json(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function run(task) {
    setBusy(true); setError("");
    try { await task(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const refreshList = () => json(`${API}/projects`).then(setProjects);

  useEffect(() => { run(refreshList); }, [API]);

  const create = () => run(async () => {
    const project = await json(`${API}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    setName("");
    await refreshList();
    setCurrent(await json(`${API}/projects/${project.id}`));
  });

  const openProject = id => run(async () => {
    setCurrent(await json(`${API}/projects/${id}/open`, { method: "POST" }));
    await refreshList();
  });

  const closeProject = () => run(async () => {
    await json(`${API}/projects/${current.id}/close`, { method: "POST" });
    setCurrent(await json(`${API}/projects/${current.id}`));
    await refreshList();
  });

  const deleteProject = () => {
    if (!window.confirm(`Delete “${current.name}” and every file in it? This cannot be undone.`)) return;
    run(async () => {
      await json(`${API}/projects/${current.id}`, { method: "DELETE" });
      setCurrent(null);
      await refreshList();
    });
  };

  const addFiles = files => run(async () => {
    for (const file of files) {
      const form = new FormData();
      form.append("kind", uploadKind);
      form.append("file", file);
      await json(`${API}/projects/${current.id}/assets`, { method: "POST", body: form });
    }
    setCurrent(await json(`${API}/projects/${current.id}`));
    await refreshList();
  });

  const removeAsset = asset => {
    if (!window.confirm(`Remove ${asset.name} from this project?`)) return;
    run(async () => {
      await json(`${API}/projects/${current.id}/assets/${asset.id}`, { method: "DELETE" });
      setCurrent(await json(`${API}/projects/${current.id}`));
      await refreshList();
    });
  };

  const isOpen = current?.status === "open";
  const integrity = current?.integrity;

  return <div style={{ width: "100%" }}>
    {onBack && <button className="pj-button" onClick={onBack} style={{ marginBottom: 14 }}>← Auralis home</button>}
    <div className="pj-shell">
      <aside className="pj-card">
        <h2 className="pj-heading">My Projects</h2>
        <p className="pj-sub">Each song keeps its sources, stems, vocals, mixes and masters in one folder on this PC.</p>
        <div className="pj-row">
          <input className="pj-input" placeholder="New project name" value={name} maxLength={80}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && name.trim()) create(); }} />
          <button className="pj-button primary" disabled={busy || !name.trim()} onClick={create}>Create</button>
        </div>
        <div className="pj-list">
          {projects.length === 0 && <div className="pj-empty">No projects yet.</div>}
          {projects.map(p => <button key={p.id}
            className={`pj-item ${current?.id === p.id ? "active" : ""}`}
            onClick={() => openProject(p.id)}>
            <div className="pj-item-name">{p.name}</div>
            <div className="pj-meta">
              <span className={`pj-status ${p.status}`}>{p.status}</span> · {p.asset_count} file{p.asset_count === 1 ? "" : "s"} · {when(p.updated_at)}
            </div>
          </button>)}
        </div>
        {error && <div className="pj-error">{error}</div>}
      </aside>

      <section className="pj-card">
        {!current && <div className="pj-empty">Choose a project to open it, or create one.<br />
          Finished masters, mixes and vocals have a “Save to project” button.</div>}

        {current && <>
          <div className="pj-row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
            <div style={{ minWidth: 0 }}>
              <h2 className="pj-heading">{current.name}</h2>
              <div className="pj-meta">
                <span className={`pj-status ${current.status}`}>{current.status}</span>
                {integrity && !integrity.linked && <> <span className="pj-status bad">
                  {integrity.missing.length} missing · {integrity.changed.length} changed</span></>}
                {" "}· created {when(current.created_at)}
              </div>
            </div>
            <div className="pj-row">
              {isOpen
                ? <button className="pj-button" disabled={busy} onClick={closeProject}>Close</button>
                : <button className="pj-button primary" disabled={busy} onClick={() => openProject(current.id)}>Reopen</button>}
              <button className="pj-button danger" disabled={busy} onClick={deleteProject}>Delete</button>
            </div>
          </div>

          {isOpen && <div className="pj-row" style={{ marginTop: 14 }}>
            <select className="pj-select" style={{ flex: "0 1 160px" }} value={uploadKind}
              onChange={e => setUploadKind(e.target.value)}>
              {KIND_ORDER.filter(([k]) => k !== "report").map(([k, label]) =>
                <option key={k} value={k}>{label}</option>)}
            </select>
            <button className="pj-button" disabled={busy} onClick={() => fileInput.current.click()}>
              {busy ? "Working…" : "Add audio files"}
            </button>
            <input ref={fileInput} type="file" accept="audio/*" multiple hidden
              onChange={e => { const files = Array.from(e.target.files); e.target.value = ""; if (files.length) addFiles(files); }} />
          </div>}

          {current.assets.length === 0 && <div className="pj-empty">This project is empty.</div>}
          {KIND_ORDER.map(([kind, label]) => {
            const assets = current.assets.filter(a => a.kind === kind);
            if (!assets.length) return null;
            return <div className="pj-group" key={kind}>
              <div className="pj-group-title">{label}</div>
              {assets.map(asset => {
                const url = `${API}/projects/${current.id}/assets/${asset.id}`;
                const missing = integrity?.missing?.includes(asset.id);
                return <div className="pj-asset" key={asset.id}>
                  <div>
                    <div className="pj-asset-name">{asset.name}</div>
                    <div className="pj-meta">
                      {asset.origin?.role || asset.origin?.type} · {size(asset.size_bytes)}
                      {asset.metadata?.profile_id ? ` · ${asset.metadata.profile_id}` : ""}
                      {asset.metadata?.key ? ` · ${asset.metadata.key}` : ""}
                      {missing && <span className="pj-status bad" style={{ marginLeft: 6 }}>missing</span>}
                    </div>
                  </div>
                  <div className="pj-asset-actions">
                    {!missing && <a className="pj-link" href={url}>download</a>}
                    {isOpen && <button className="pj-link danger" onClick={() => removeAsset(asset)}>remove</button>}
                  </div>
                  {!missing && AUDIO.test(asset.name) && <audio controls preload="none" src={url} />}
                </div>;
              })}
            </div>;
          })}
        </>}
      </section>
    </div>
  </div>;
}
