import React, { useEffect, useState } from 'react';
import './PluginLibrary.css';

export default function PluginLibrary({ API }) {
  const [catalog, setCatalog] = useState({ plugins: [], locations: [], categories: [], templates: [] });
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [paths, setPaths] = useState('');
  const [template, setTemplate] = useState('Modern pop/R&B lead');
  const [chain, setChain] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function request(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error('The plugin library request failed. Check the local backend.');
    return response.json();
  }
  useEffect(() => { let live = true;
    request(`${API}/plugins`).then(data => { if (live) setCatalog(data); }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [API]);
  async function scan() {
    setBusy(true); setError(''); setChain(null);
    try { setCatalog(await request(`${API}/plugins/scan`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: paths.split('\n').map(p => p.trim()).filter(Boolean) }) })); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function plan() {
    setError(''); setBusy(true);
    try { setChain(await request(`${API}/plugins/chains?template=${encodeURIComponent(template)}`)); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const shown = catalog.plugins.filter(p => (!category || p.categories.includes(category)) &&
    [p.name, p.manufacturer, p.description, ...p.categories].join(' ').toLowerCase().includes(query.toLowerCase()));
  return <main className="au-page-scroll plugin-library">
    <header><span className="lx-eyebrow">YOUR TOOLS · LOCAL INVENTORY</span><h1>Plugin Library</h1>
      <p>Find what you own. Plan a vocal chain from your discovered collection.</p></header>
    <section className="lx-glass plugin-section" aria-label="Discovery">
      <h2>Discover your plugins</h2><p>Read-only metadata scan. No plugins are loaded, activated, or tested in Mixcraft.</p>
      <label>Additional plugin folders (one absolute path per line)
        <textarea value={paths} onChange={e => setPaths(e.target.value)} rows={2} placeholder="Optional: a dedicated VST folder" />
      </label><p>Choose dedicated plugin folders only. Paths remain in this session. Standard Windows VST folders are included.</p>
      <button className="lx-btn" disabled={busy} onClick={scan}>{busy ? 'Working…' : 'Scan plugin folders'}</button>
      <p role="status">{catalog.notice}</p>
      {catalog.locations.length > 0 && <details><summary>Scan locations and coverage</summary><ul>
        {catalog.locations.map((loc, i) => <li key={i}>Folder {loc.root_index + 1}: {loc.status}</li>)}
      </ul></details>}
    </section>
    {error && <p role="alert">{error}</p>}
    <section className="lx-glass plugin-section" aria-label="Vocal chain planner">
      <h2>Vocal chain planner</h2><label>Vocal style<select value={template} onChange={e => { setTemplate(e.target.value); setChain(null); }}>
        {catalog.templates.map(t => <option key={t}>{t}</option>)}</select></label>
      <button className="lx-btn" onClick={plan} disabled={busy || !catalog.templates.length}>Suggest a chain</button>
      {chain && <><p>{chain.notice}</p><ol>{chain.steps.map((step, i) => <li key={i}>
        <strong>{step.category}: {step.plugin_name || 'Unavailable or unverified'}</strong> — {step.reason} <small>{step.status}</small>
      </li>)}</ol></>}
    </section>
    <section aria-label="Plugin catalog"><div className="plugin-filters">
      <label>Search plugins or functions<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Try pitch, alignment, delay…" /></label>
      <label>Category<select value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>
        {catalog.categories.map(c => <option key={c}>{c}</option>)}</select></label></div>
      <p>{shown.length} of {catalog.plugins.length} discovered entries</p>
      {!shown.length && <p>No matching plugins. Scan your plugin folders or adjust the filters.</p>}
      <div className="plugin-grid">{shown.map(p => <article key={p.id} className="lx-glass plugin-section">
        <h2>{p.name}</h2><p>{p.manufacturer} · {p.version} · {p.format} · {p.architecture}</p>
        <p>{p.categories.join(' · ')}</p><p>{p.description}</p>
        <p>{p.compatibility}</p><p>Discovery: {p.discovery_status}</p>
        {p.duplicate_ids.length > 0 && <p>Possible duplicates: {p.duplicate_ids.length}</p>}
        <details><summary>Local file and classification evidence</summary><p className="plugin-path">{p.path}</p>
          <ul>{p.classification_evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></details>
      </article>)}</div>
    </section>
  </main>;
}
