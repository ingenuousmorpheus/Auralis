import React, { useEffect, useState } from "react";
import "./Projects.css";

/* Saves a finished job (master, mix, converted/polished/finished vocal) into a
   persistent project. Job outputs otherwise live only in a temp folder and are
   unreachable after the backend restarts. */

const NEW = "__new__";

export default function SaveToProject({ API, jobId, label = "Save to project" }) {
  const [projects, setProjects] = useState([]);
  const [choice, setChoice] = useState(NEW);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/projects`).then(r => r.json()).then(list => {
      const open = list.filter(p => p.status === "open");
      setProjects(open);
      if (open.length) setChoice(open[0].id);
    }).catch(() => {});
  }, [API]);

  useEffect(() => { setSaved(null); setError(""); }, [jobId]);

  async function json(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  async function save() {
    setBusy(true); setError("");
    try {
      let projectId = choice;
      let projectName = projects.find(p => p.id === choice)?.name;
      if (choice === NEW) {
        const created = await json(`${API}/projects`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.trim() }),
        });
        projectId = created.id;
        projectName = created.name;
        setProjects(prev => [created, ...prev]);
        setChoice(created.id);
      }
      const result = await json(`${API}/projects/${projectId}/import-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });
      setSaved({ name: projectName, count: result.assets.length });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!jobId) return null;
  if (saved) {
    return <div className="pj-save">
      <div className="pj-save-done">✓ Saved {saved.count} file{saved.count === 1 ? "" : "s"} to “{saved.name}”</div>
    </div>;
  }
  const canSave = !busy && (choice !== NEW || name.trim());
  return <div className="pj-save">
    <div className="pj-save-title">{label}</div>
    <div className="pj-row">
      <select className="pj-select" value={choice} onChange={e => setChoice(e.target.value)}>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        <option value={NEW}>+ New project…</option>
      </select>
      <button className="pj-button primary" disabled={!canSave} onClick={save}>
        {busy ? "Saving…" : "Save"}
      </button>
    </div>
    {choice === NEW && <input className="pj-input" style={{ marginTop: 8, width: "100%" }}
      placeholder="Project name" value={name} maxLength={80}
      onChange={e => setName(e.target.value)} />}
    {error && <div className="pj-error">{error}</div>}
  </div>;
}
