import React, { useEffect, useRef, useState } from "react";
import "./HarmonicReference.css";

/* Harmonic Reference — reference matching in the note domain.

   Mirrors the mastering reference flow, but the readout is notes rather than
   EQ. The centrepiece is the degree-delta bar chart: it is deliberately drawn
   like a per-band EQ match, because that is exactly what it is — the same
   comparison, one axis over. Degrees are relative to each track's own tonic
   (see auralis/engine/harmony.py), which is what makes two songs in different
   keys comparable at all. */

const DEGREE_LABELS = ["1", "♭2", "2", "♭3", "3", "4", "♭5", "5", "♭6", "6", "♭7", "7"];

const SEVERITY = {
  high: { color: "#ff62c8", label: "Major" },
  medium: { color: "#ffbd73", label: "Worth a look" },
  low: { color: "#46f6bd", label: "Fine" },
};

const KIND_GLYPH = {
  transpose: "⇅",
  mode: "◑",
  degree: "≈",
  out_of_key: "!",
  register: "⇵",
  confidence: "?",
};

function DegreeChart({ target, reference, deltas }) {
  // Scale to the largest single value present so small differences stay
  // readable instead of collapsing into a flat line.
  const peak = Math.max(
    0.08,
    ...target.map(Math.abs),
    ...reference.map(Math.abs),
  );
  return (
    <div className="hr-chart">
      <div className="hr-chart-legend">
        <span><i className="hr-swatch hr-swatch-target" /> your track</span>
        <span><i className="hr-swatch hr-swatch-ref" /> reference</span>
      </div>
      <div className="hr-bars">
        {DEGREE_LABELS.map((label, i) => {
          const delta = deltas[i] ?? 0;
          const notable = Math.abs(delta) >= 0.035;
          return (
            <div className="hr-bar-col" key={label} title={
              `Degree ${label} — you ${(target[i] * 100).toFixed(1)}%, ` +
              `reference ${(reference[i] * 100).toFixed(1)}%`
            }>
              <div className="hr-bar-stack">
                <i className="hr-bar hr-bar-target"
                   style={{ height: `${Math.min(100, (target[i] / peak) * 100)}%` }} />
                <i className="hr-bar hr-bar-ref"
                   style={{ height: `${Math.min(100, (reference[i] / peak) * 100)}%` }} />
              </div>
              <div className={`hr-degree ${notable ? "hr-degree-notable" : ""}`}>{label}</div>
              <div className="hr-delta" style={{
                color: !notable ? "#8f9bb4" : delta > 0 ? "#ff62c8" : "#66e8ff",
              }}>
                {delta > 0 ? "+" : ""}{(delta * 100).toFixed(0)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="hr-chart-caption">
        Scale degrees relative to each track&rsquo;s own tonic. Pink = you use it more,
        blue = the reference does. Numbers are percentage points of tonal energy.
      </div>
    </div>
  );
}

function KeyCard({ title, analysis, accent }) {
  if (!analysis) return null;
  const confident = analysis.key_confidence >= 0.5;
  return (
    <div className="hr-keycard" style={{ "--accent": accent }}>
      <div className="hr-keycard-title">{title}</div>
      <div className="hr-keyname">{analysis.key_name}</div>
      <div className="hr-keymeta">
        <span className={confident ? "" : "hr-warn"}>
          {(analysis.key_confidence * 100).toFixed(0)}% confident
        </span>
        {analysis.median_midi != null && <span>{analysis.note_count} notes</span>}
        {analysis.out_of_key_energy > 0 &&
          <span>{(analysis.out_of_key_energy * 100).toFixed(0)}% outside key</span>}
      </div>
    </div>
  );
}

export default function HarmonicReference({ API, onBack }) {
  const [targetFile, setTargetFile] = useState(null);
  const [referenceFile, setReferenceFile] = useState(null);
  const [targetKey, setTargetKey] = useState("auto");
  const [referenceKey, setReferenceKey] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [pct, setPct] = useState(0);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const targetInput = useRef(null);
  const referenceInput = useRef(null);
  const pollTimer = useRef(null);

  useEffect(() => () => clearInterval(pollTimer.current), []);

  async function run() {
    if (!targetFile || !referenceFile) return;
    setBusy(true);
    setError(null);
    setReport(null);
    setPct(0);
    setStage("uploading");
    try {
      const body = new FormData();
      body.append("target", targetFile);
      body.append("reference", referenceFile);
      body.append("target_key", targetKey);
      body.append("reference_key", referenceKey);
      const started = await fetch(`${API}/harmony/compare`, { method: "POST", body });
      const data = await started.json().catch(() => ({}));
      if (!started.ok) throw new Error(data.detail || `Request failed (${started.status})`);
      const { job_id } = data;

      // Polling rather than the websocket the master flow uses: this job is
      // analysis-only and short, and /jobs/{id} already carries stage + pct.
      pollTimer.current = setInterval(async () => {
        try {
          const response = await fetch(`${API}/jobs/${job_id}`);
          const data = await response.json();
          setStage(data.stage || "");
          setPct(data.pct || 0);
          if (data.error) {
            clearInterval(pollTimer.current);
            setError(data.error);
            setBusy(false);
          } else if (data.stage === "done" && data.result) {
            clearInterval(pollTimer.current);
            setReport(data.result);
            setBusy(false);
          }
        } catch (pollError) {
          clearInterval(pollTimer.current);
          setError(pollError.message);
          setBusy(false);
        }
      }, 700);
    } catch (submitError) {
      setError(submitError.message);
      setBusy(false);
    }
  }

  const ready = targetFile && referenceFile && !busy;

  return (
    <div className="hr-shell">
      <div className="hr-head">
        <div>
          <div className="eyebrow"><span className="pulse-dot" />note-domain reference match</div>
          <h2 className="panel-title" style={{ marginBottom: 4 }}>Harmonic Reference</h2>
          <p className="panel-copy" style={{ maxWidth: 560 }}>
            Mastering reference matching compares your <em>spectrum</em> to a song you like.
            This compares your <em>notes</em> — key, mode, which scale degrees you lean on,
            and anything sitting outside the key. It only advises; Pitch Polish is the
            stage that edits audio.
          </p>
        </div>
        {onBack && <button className="hr-back" onClick={onBack}>←</button>}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="hr-inputs">
        {[
          { label: "Your track", file: targetFile, set: setTargetFile, ref: targetInput,
            keyValue: targetKey, setKey: setTargetKey, accent: "#ff62c8" },
          { label: "Reference", file: referenceFile, set: setReferenceFile, ref: referenceInput,
            keyValue: referenceKey, setKey: setReferenceKey, accent: "#66e8ff" },
        ].map(slot => (
          <div className="hr-slot" key={slot.label} style={{ "--accent": slot.accent }}>
            <div className="hr-slot-label">{slot.label}</div>
            <button className="hr-drop" onClick={() => slot.ref.current.click()}>
              {slot.file ? slot.file.name : "Choose an audio file"}
            </button>
            <input ref={slot.ref} type="file" hidden
                   accept=".wav,.flac,.mp3,.aif,.aiff,.ogg"
                   onChange={e => slot.set(e.target.files[0] || null)} />
            <label className="hr-keyfield">
              Key
              <input value={slot.keyValue}
                     onChange={e => slot.setKey(e.target.value)}
                     placeholder="auto"
                     spellCheck={false} />
            </label>
          </div>
        ))}
      </div>

      <p className="hr-hint">
        Leave the key on <code>auto</code> unless detection gets it wrong. A full mix or
        instrumental reads far more reliably than a bare vocal — a lone vocal often
        can&rsquo;t distinguish related keys.
      </p>

      <button className="hr-run" disabled={!ready} onClick={run}>
        {busy ? `${stage || "working"}… ${Math.round(pct)}%` : "Compare harmony"}
      </button>

      {busy && <div className="hr-progress"><span style={{ width: `${pct}%` }} /></div>}

      {report && <div className="hr-results">
        <div className="hr-keys">
          <KeyCard title="Your track" analysis={report.target} accent="#ff62c8" />
          <div className="hr-transpose">
            {report.suggested_transpose === 0
              ? <><div className="hr-transpose-value">=</div><div className="hr-transpose-label">same tonic</div></>
              : <>
                  <div className="hr-transpose-value">
                    {report.suggested_transpose > 0 ? "+" : ""}{report.suggested_transpose}
                  </div>
                  <div className="hr-transpose-label">semitones to match</div>
                </>}
          </div>
          <KeyCard title="Reference" analysis={report.reference} accent="#66e8ff" />
        </div>

        <DegreeChart
          target={report.target.degree_weights}
          reference={report.reference.degree_weights}
          deltas={report.degree_deltas}
        />

        <div className="hr-suggestions">
          <div className="eyebrow" style={{ marginBottom: 8 }}>What to change</div>
          {report.suggestions.map((suggestion, i) => {
            const severity = SEVERITY[suggestion.severity] || SEVERITY.low;
            return (
              <div className="hr-suggestion" key={i} style={{ "--accent": severity.color }}>
                <div className="hr-suggestion-glyph">{KIND_GLYPH[suggestion.kind] || "•"}</div>
                <div className="hr-suggestion-body">
                  <div className="hr-suggestion-meta">
                    <span className="hr-kind">{suggestion.kind.replace(/_/g, " ")}</span>
                    <span className="hr-sev" style={{ color: severity.color }}>{severity.label}</span>
                  </div>
                  <div className="hr-suggestion-text">{suggestion.message}</div>
                </div>
              </div>
            );
          })}
        </div>

        {report.target.out_of_key_notes?.length > 0 && <div className="hr-strays">
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Notes outside {report.target.key_name}
          </div>
          <div className="hr-stray-grid">
            {report.target.out_of_key_notes.slice(0, 12).map((note, i) => (
              <div className="hr-stray" key={i}>
                <span className="hr-stray-time">
                  {Math.floor(note.start_seconds / 60)}:
                  {(note.start_seconds % 60).toFixed(1).padStart(4, "0")}
                </span>
                <span className="hr-stray-move">
                  {note.detected_note} <em>→</em> {note.nearest_in_key_note}
                </span>
                <span className="hr-stray-cents">{note.cents_away > 0 ? "+" : ""}{note.cents_away}¢</span>
              </div>
            ))}
          </div>
          <div className="hr-chart-caption">
            Not every one of these is a mistake — blue notes, borrowed tones and passing
            notes live here too. Auralis flags them; it doesn&rsquo;t change them.
          </div>
        </div>}
      </div>}
    </div>
  );
}
