import React from "react";

/* Shared pieces for the bridge-console shell: stroke icons, cover tiles,
   formatting. Icons are decorative (aria-hidden); buttons carry the labels. */

const PATHS = {
  create: <><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></>,
  music: <path d="M4 4v16M9 4v16M14 4l6 16" />,
  studio: <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />,
  voice: <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 17v5" /></>,
  projects: <path d="M3 7h18M3 12h18M3 17h12" />,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>,
  edit: <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />,
  expand: <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />,
  volume: <path d="M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" />,
  folder: <path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  wave: <path d="M3 13h2M8 8v10M12 4v18M16 9v8M20 6v14M24 12v2" />,
  back: <path d="M15 18l-6-6 6-6" />,
  dna: <path d="M7 3c0 6 10 6 10 12s-10 6-10 6M17 3c0 6-10 6-10 12s10 6 10 6M8 7h8M8 17h8" />,
};

export function Icon({ name, size = 19, stroke = "currentColor", width = 2 }) {
  const box = name === "wave" ? "0 0 26 26" : "0 0 24 24";
  return <svg width={size} height={size} viewBox={box} fill="none" stroke={stroke} strokeWidth={width}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[name]}</svg>;
}

export function PlayGlyph({ playing }) {
  return playing
    ? <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></svg>
    : <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>;
}

const COVERS = ["#2b2416", "#1b2530", "#2a1f16", "#162628", "#27221a", "#1e1f2b", "#241c14", "#1a2320", "#2a2520"];

export function coverColor(id = "") {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COVERS[h % COVERS.length];
}

export function Cover({ id, size = 76, radius = 12, label }) {
  return <div className="au-cover" style={{ width: size, height: size, borderRadius: radius, background: coverColor(id) }}>
    <Icon name="wave" size={Math.round(size * 0.4)} stroke="#e9cf8a" />
    {label && <span className="au-mono" style={{
      position: "absolute", right: 6, bottom: 5, fontSize: 11, color: "#fff",
      background: "rgba(0,0,0,0.55)", padding: "1px 5px", borderRadius: 6,
    }}>{label}</span>}
  </div>;
}

export function fmtTime(seconds) {
  if (seconds == null || !isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export async function apiJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

/* Honest catalog aggregates for the "your sound" readouts. Only uses fields the
   library summary really has; anything not measurable is left out. */
export function catalogStats(songs) {
  const done = songs.filter(s => s.analysis_status === "done" && s.summary);
  if (!done.length) return null;
  const pct = (xs, p) => {
    const v = [...xs].sort((a, b) => a - b);
    const i = (v.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
    return v[lo] + (v[hi] - v[lo]) * (i - lo);
  };
  const bpm = done.map(s => s.summary.bpm).filter(Number.isFinite);
  const lufs = done.map(s => s.summary.lufs).filter(Number.isFinite);
  const chords = done.map(s => s.summary.chords_per_bar).filter(Number.isFinite);
  const minor = done.filter(s => /minor/.test(s.summary.key || "")).length;
  return {
    total: songs.length,
    analysed: done.length,
    stemSets: songs.filter(s => s.kind === "stem-set").length,
    tempoLow: Math.round(pct(bpm, 0.25)),
    tempoHigh: Math.round(pct(bpm, 0.75)),
    minorShare: Math.round((minor / done.length) * 100),
    minorCount: minor,
    chordsPerBar: pct(chords, 0.5).toFixed(1),
    lufs: pct(lufs, 0.5).toFixed(1),
    withVocal: done.filter(s => s.summary.vocal_range).length,
  };
}
