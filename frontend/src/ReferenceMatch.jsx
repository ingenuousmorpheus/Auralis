import React, { useEffect, useState } from 'react';
import { WavePlayer } from './Lux.jsx';
import './ReferenceMatch.css';

function rememberedJob() {
  try { return sessionStorage.getItem('auralis.vocalMatch') || ''; } catch { return ''; }
}
function remember(id) {
  try { if (id) sessionStorage.setItem('auralis.vocalMatch', id); else sessionStorage.removeItem('auralis.vocalMatch'); } catch { /* optional */ }
}
function useFileUrl(file) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!file) { setUrl(''); return; }
    const next = URL.createObjectURL(file); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  return url;
}

export default function ReferenceMatch({ API }) {
  const [guide, setGuide] = useState(null);
  const [take, setTake] = useState(null);
  const [jobId, setJobId] = useState(rememberedJob);
  const [busy, setBusy] = useState(() => Boolean(rememberedJob()));
  const [stage, setStage] = useState('');
  const [pct, setPct] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const guideUrl = useFileUrl(guide), takeUrl = useFileUrl(take);

  useEffect(() => {
    if (!jobId) return;
    let active = true, timer;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch(`${API}/jobs/${jobId}`, { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'The vocal match could not be found.');
        if (!active) return;
        setStage(data.stage || 'Working'); setPct(data.pct || 0);
        if (data.error) { setError(data.error); setBusy(false); }
        else if (data.stage === 'done' && data.result) { setResult(data.result); setBusy(false); }
        else timer = setTimeout(poll, 800);
      } catch (e) {
        if (active) { setError(e.message); setBusy(false); }
      }
    }
    poll();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [API, jobId]);

  function selectFile(kind, file) {
    setJobId(''); remember(''); setResult(null); setError(''); setStage(''); setPct(0);
    if (kind === 'guide') setGuide(file); else setTake(file);
  }
  async function run() {
    if (!guide || !take || busy) return;
    setBusy(true); setResult(null); setError(''); setStage('Uploading your vocals'); setPct(0);
    setJobId(''); remember('');
    try {
      const body = new FormData(); body.append('guide', guide); body.append('take', take);
      const response = await fetch(`${API}/voice/match`, { method: 'POST', body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The two vocals could not be submitted.');
      remember(data.job_id); setJobId(data.job_id);
    } catch (e) { setError(e.message); setBusy(false); }
  }
  const preview = which => `${API}/voice/match/${jobId}/audio/${which}`;
  return <main className="au-page-scroll reference-match lx-atmosphere">
    <header><span className="lx-eyebrow">YOUR PERFORMANCE · THE DEMO’S DIRECTION</span>
      <h1>Match the demo</h1><p>Your voice, following the demo’s timing and melody.</p></header>
    <div className="reference-match-inputs">
      <section className="lx-glass"><h2>1. Demo singer</h2>
        <p>The performance you want to follow. A human or AI solo vocal works.</p>
        <label className="reference-match-file">Demo vocal WAV
          <input type="file" accept=".wav,audio/wav" disabled={busy} onChange={e => selectFile('guide', e.target.files?.[0] || null)} />
        </label>{(guideUrl || (result && jobId)) && <WavePlayer src={guideUrl || preview('guide')} decode label="Demo singer" />}
      </section>
      <section className="lx-glass"><h2>2. Your vocal</h2>
        <p>Sing the same words, in the same order. Keep the take dry and unaccompanied.</p>
        <label className="reference-match-file">Your vocal WAV
          <input type="file" accept=".wav,audio/wav" disabled={busy} onChange={e => selectFile('take', e.target.files?.[0] || null)} />
        </label>{(takeUrl || (result && jobId)) && <WavePlayer src={takeUrl || preview('take')} decode label="Your original vocal" />}
      </section>
    </div>
    <section className="lx-glass reference-match-action">
      <p>Use isolated solo vocals of the same section, up to 3 minutes each. Backing music, different words, or missing phrases can confuse the match.</p>
      <button className="lx-btn primary big" onClick={run} disabled={busy || !guide || !take}>{busy ? 'Matching…' : 'Match my vocal'}</button>
      <p className="lx-muted">Creates a new WAV. Your original recordings stay untouched. No voice model or plugin setup needed.</p>
      {busy && <div role="status" aria-live="polite"><p>{stage}</p>
        <progress value={pct} max="100" aria-label="Vocal matching progress" /> <span>{Math.round(pct)}%</span></div>}
      {error && <p className="reference-match-error" role="alert">{error}</p>}
    </section>
    {result && <section className="lx-glass reference-match-result" aria-label="Matched vocal">
      <span className="lx-eyebrow">YOUR MATCHED TAKE</span><h2>Hear your vocal with the demo</h2>
      <WavePlayer src={preview('result')} decode label="Matched vocal" />
      <p>{result.duration_seconds} seconds · {result.pitch_regions_changed} melody regions adjusted</p>
      <a className="lx-btn primary" href={preview('result')} download="auralis_matched_vocal.wav">Download matched WAV</a>
      <details><summary>Match notes</summary><ul>{result.warnings?.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
        <a href={`${API}/voice/match/${jobId}/report`} download>Download match report</a></details>
      <p className="lx-muted">Listen to the demo, your original, and the matched take above. Check words, breaths, and note changes before mixing. Experimental Auralis matching.</p>
    </section>}
  </main>;
}
