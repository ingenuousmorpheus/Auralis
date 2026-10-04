import React, { useEffect, useMemo, useRef, useState } from "react";
import "./lux.css";
import { Icon, PlayGlyph, fmtTime } from "./ui.jsx";

/* Reusable pieces of the luxury design layer (lux.css). Pages compose these
   instead of styling audio, status and tabs one-off. */

/* ── Audio → peaks ────────────────────────────────────────────────────── */

const decoded = new Map();          // url → Promise<{peaks, duration}>
const MAX_DECODE_BYTES = 80 * 1024 * 1024;

/* Peaks (0..1) and duration for a URL, File or Blob, decoded in the browser.
   Used where the backend has no peaks endpoint (a voice's sample, files the
   user is about to convert). Returns null when the audio can't be decoded. */
export function decodePeaks(source, buckets = 160) {
  const key = typeof source === "string" ? source : null;
  if (key && decoded.has(key)) return decoded.get(key);
  const job = (async () => {
    try {
      if (typeof source !== "string" && source.size > MAX_DECODE_BYTES) return null;
      const data = typeof source === "string"
        ? await fetch(source).then(r => { if (!r.ok) throw new Error(); return r.arrayBuffer(); })
        : await source.arrayBuffer();
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      try {
        const audio = await ctx.decodeAudioData(data);
        const ch = audio.getChannelData(0);
        const step = Math.max(1, Math.floor(ch.length / buckets));
        const peaks = [];
        for (let i = 0; i < buckets; i++) {
          let m = 0;
          for (let j = i * step, end = Math.min(ch.length, j + step); j < end; j += 4) m = Math.max(m, Math.abs(ch[j]));
          peaks.push(m);
        }
        const top = Math.max(...peaks, 1e-6);
        return { peaks: peaks.map(p => p / top), duration: audio.duration };
      } finally { ctx.close?.(); }
    } catch { return null; }
  })();
  if (key) decoded.set(key, job);
  return job;
}

function resample(peaks, bars) {
  if (!peaks?.length) return null;
  if (peaks.length <= bars) return peaks;
  const out = [];
  const step = peaks.length / bars;
  for (let i = 0; i < bars; i++) {
    let m = 0;
    for (let j = Math.floor(i * step); j < Math.floor((i + 1) * step); j++) m = Math.max(m, peaks[j]);
    out.push(m);
  }
  const top = Math.max(...out, 1e-6);
  return out.map(p => p / top);
}

/* ── Waveform player ──────────────────────────────────────────────────── */

/* A player drawn as its waveform: play/pause, click or arrow keys to seek,
   time and duration. Changing `src` keeps the position and play state, so
   an A/B switch compares the same moment. Only one plays at a time. */
export function WavePlayer({ src, peaks, duration, decode = false, height = 40, bars = 110,
  size = "", label = "audio", disabled = false }) {
  const audio = useRef(null);
  const pending = useRef(null);
  const [own, setOwn] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(duration || 0);

  useEffect(() => { if (duration) setDur(d => d || duration); }, [duration]);
  useEffect(() => {
    if (!decode || peaks || !src) return;
    let live = true;
    decodePeaks(src).then(r => { if (live && r) { setOwn(r.peaks); setDur(d => d || r.duration); } });
    return () => { live = false; };
  }, [src, decode, peaks]);

  useEffect(() => {                                   // A/B: keep the moment
    const el = audio.current;
    if (!el || !src) return;
    const resume = !el.paused, at = el.currentTime;
    el.src = src;
    if (resume || at > 0) {
      pending.current = { at, resume };
      el.load();
    }
  }, [src]);

  useEffect(() => {
    const stop = e => { if (e.detail !== audio.current) audio.current?.pause(); };
    window.addEventListener("lx-play", stop);
    return () => window.removeEventListener("lx-play", stop);
  }, []);

  const shown = useMemo(() => resample(peaks || own, bars), [peaks, own, bars]);
  const frac = dur ? Math.min(1, time / dur) : 0;

  const toggle = () => {
    const el = audio.current;
    if (!el || disabled) return;
    if (el.paused) el.play().catch(() => {});
    else el.pause();
  };
  const seekTo = f => {
    const el = audio.current;
    if (!el) return;
    if (el.readyState >= 1 && el.duration) el.currentTime = f * el.duration;
    else { pending.current = { frac: f, resume: true }; el.load(); }
  };

  return <div className={`lx-wave ${size} ${playing ? "playing" : ""}`}>
    <audio ref={audio} preload="none"
      onLoadedMetadata={e => {
        const el = e.currentTarget;
        setDur(el.duration);
        const p = pending.current; pending.current = null;
        if (p?.frac != null) el.currentTime = p.frac * el.duration;
        else if (p?.at) el.currentTime = Math.min(p.at, el.duration);
        if (p?.resume) el.play().catch(() => {});
      }}
      onTimeUpdate={e => setTime(e.currentTarget.currentTime)}
      onPlay={e => { setPlaying(true); window.dispatchEvent(new CustomEvent("lx-play", { detail: e.currentTarget })); }}
      onPause={() => setPlaying(false)}
      onEnded={() => { setPlaying(false); setTime(0); }} />
    <button className="lx-wave-play" onClick={toggle} disabled={disabled || !src}
      aria-label={`${playing ? "Pause" : "Play"} ${label}`}><PlayGlyph playing={playing} /></button>
    <div className="lx-wave-track" role="slider" tabIndex={0} aria-label={`Position in ${label}`}
      aria-valuemin={0} aria-valuemax={Math.round(dur) || 0} aria-valuenow={Math.round(time)}
      onClick={e => { const b = e.currentTarget.getBoundingClientRect(); seekTo(Math.max(0, Math.min(1, (e.clientX - b.left) / b.width))); }}
      onKeyDown={e => {
        const el = audio.current;
        if (!el || !el.duration) return;
        if (e.key === "ArrowRight") el.currentTime = Math.min(el.duration, el.currentTime + 5);
        if (e.key === "ArrowLeft") el.currentTime = Math.max(0, el.currentTime - 5);
        if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(); }
      }}>
      {shown ? <svg viewBox={`0 0 ${shown.length * 3} ${height}`} preserveAspectRatio="none" style={{ height }} aria-hidden="true">
        <defs><linearGradient id="lx-wave-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--lx-cyan)" /><stop offset="1" stopColor="var(--lx-violet)" /></linearGradient></defs>
        {shown.map((p, i) => {
          const h = Math.max(2, p * height);
          return <rect key={i} className={i / shown.length < frac ? "played" : ""} x={i * 3} y={(height - h) / 2} width={2} height={h} rx={1} />;
        })}
      </svg> : <div style={{ height, display: "flex", alignItems: "center" }}><div className="lx-wave-flat" style={{ width: "100%" }} /></div>}
      {(playing || time > 0) && <i className="lx-wave-head" style={{ left: `${frac * 100}%` }} aria-hidden="true" />}
    </div>
    <span className="lx-wave-time">{fmtTime(time)} / {fmtTime(dur)}</span>
  </div>;
}

/* ── Small primitives ─────────────────────────────────────────────────── */

export function Badge({ tone = "", plain = false, children }) {
  return <span className={`lx-badge ${tone} ${plain ? "plain" : ""}`}>{children}</span>;
}

export function Tabs({ items, value, onChange, label, large = false }) {
  return <div className={`lx-tabs ${large ? "large" : ""}`} role="tablist" aria-label={label}>
    {items.map(([id, text, count, disabled]) => <button key={id} role="tab" aria-selected={value === id}
      disabled={disabled} onClick={() => onChange(id)}>{text}{count != null && <small>{count}</small>}</button>)}
  </div>;
}

export function Segment({ items, value, onChange, label }) {
  return <div className="lx-segment" role="radiogroup" aria-label={label}>
    {items.map(([id, text]) => <button key={id} role="radio" aria-checked={value === id} aria-selected={value === id}
      onClick={() => onChange(id)}>{text}</button>)}
  </div>;
}

export function Stat({ label, value, hint }) {
  return <div className="lx-stat"><span className="lx-eyebrow">{label}</span><b>{value}</b>{hint && <small>{hint}</small>}</div>;
}

export function Progress({ pct = 0, state = "" }) {
  return <div className={`lx-progress ${state}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
    <i style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} /></div>;
}

export function ToolCard({ icon, title, text, action, onClick, current = false }) {
  return <button className="lx-glass lx-tool" onClick={onClick} aria-current={current ? "true" : undefined}>
    <span className="lx-tool-icon"><Icon name={icon} size={20} /></span>
    <b>{title}</b><span>{text}</span>{action && <em>{action} →</em>}
  </button>;
}

export function StatusItem({ icon, tone = "", title, detail }) {
  return <div className="lx-status-item"><span className={`lx-dot ${tone}`} aria-hidden="true" />
    {icon && <Icon name={icon} size={16} />}<b>{title}</b>{detail && <span>{detail}</span>}</div>;
}

/* A popover menu that closes on an outside click or Escape. */
export function Menu({ label, children, icon = "more" }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = e => { if (!box.current?.contains(e.target)) setOpen(false); };
    const esc = e => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return <div ref={box} style={{ position: "relative" }}>
    <button className="lx-icon-btn" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(v => !v)}>
      <Icon name={icon} size={18} /></button>
    {open && <div className="lx-menu" role="menu" onClick={e => { if (e.target.closest("[data-close]")) setOpen(false); }}>{children}</div>}
  </div>;
}
