import React, { useEffect, useRef, useState } from "react";
import { Cover, Icon, PlayGlyph, apiJson, fmtTime } from "./ui.jsx";

const MAIN = [
  { id: "create", label: "Create", icon: "create" },
  { id: "music", label: "My Music", icon: "music" },
  { id: "studio", label: "Studio", icon: "studio" },
  { id: "voice", label: "My Voice", icon: "voice" },
  { id: "projects", label: "Projects", icon: "projects" },
];

export function Sidebar({ API, page, go, tools }) {
  const [morphing, setMorphing] = useState(false);
  const [voice, setVoice] = useState(null);

  useEffect(() => {
    apiJson(`${API}/voice/profiles`).then(list => {
      const trained = list.find(p => p.training_status === "trained");
      setVoice(trained || list[0] || null);
    }).catch(() => setVoice(null));
  }, [API]);

  return <nav className="au-nav" aria-label="Main">
    <div className="au-brand">
      <button className="au-logo" aria-label="Auralis, go to Create"
        onClick={() => { setMorphing(false); requestAnimationFrame(() => setMorphing(true)); go("create"); }}>
        <span className={`au-logo-word${morphing ? " morphing" : ""}`}
          onAnimationEnd={e => { if (e.animationName === "au-morph") setMorphing(false); }}>AURALIS</span>
      </button>
      <div className="au-status"><span className="au-dot" />LOCAL CORE · ONLINE</div>
    </div>

    <div className="au-nav-group">
      {MAIN.map(item => <button key={item.id} className="au-nav-item"
        aria-current={page === item.id ? "page" : undefined} onClick={() => go(item.id)}>
        <Icon name={item.icon} />{item.label}
      </button>)}
    </div>

    <div className="au-nav-group">
      <div className="au-nav-label">Tools</div>
      {tools.map(tool => <button key={tool.id} className="au-nav-item small"
        aria-current={page === tool.id ? "page" : undefined} onClick={() => go(tool.id)}>{tool.label}</button>)}
    </div>

    <div className="au-spacer" style={{ flexGrow: 1 }} />

    <button className="au-voice-card" style={{ cursor: "pointer", textAlign: "left", color: "inherit", font: "inherit" }}
      onClick={() => go("voice")} aria-label="Open My Voice">
      {voice ? <>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="au-avatar">{voice.name.slice(0, 1).toUpperCase()}</div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{voice.name}</div>
            <div style={{ fontSize: 12, color: "var(--steel)" }}>
              My voice · {voice.training_status === "trained" ? "studio trained" : voice.kind.replace("-", " ")}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {voice.training_steps > 0 && <span className="au-chip holo">{voice.training_steps.toLocaleString()} steps</span>}
          <span className="au-chip signal">local · private</span>
        </div>
      </> : <div style={{ fontSize: 13, color: "var(--steel)" }}>No voice profile yet. Open My Voice to create one.</div>}
    </button>
  </nav>;
}

export function PlayerBar({ API, track, onOpen }) {
  const audio = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [error, setError] = useState("");

  useEffect(() => {
    const el = audio.current;
    if (!el || !track) return;
    setError(""); setTime(0); setDuration(track.duration || 0);
    // A stem set is summed into a preview the first time; that can take a moment.
    setLoading(true);
    el.src = `${API}/artist/library/songs/${track.id}/preview`;
    el.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }, [API, track?.id]);

  useEffect(() => { if (audio.current) audio.current.volume = volume; }, [volume]);

  const toggle = () => {
    const el = audio.current;
    if (!el || !track) return;
    if (el.paused) el.play().then(() => setPlaying(true)).catch(() => {});
    else { el.pause(); setPlaying(false); }
  };
  const seek = e => {
    const el = audio.current;
    if (!el || !duration) return;
    const box = e.currentTarget.getBoundingClientRect();
    el.currentTime = Math.max(0, Math.min(1, (e.clientX - box.left) / box.width)) * duration;
  };

  return <footer className="au-player" aria-label="Player">
    <audio ref={audio} preload="none"
      onLoadedMetadata={e => { setDuration(e.currentTarget.duration); setLoading(false); }}
      onCanPlay={() => setLoading(false)}
      onTimeUpdate={e => setTime(e.currentTarget.currentTime)}
      onPlay={() => setPlaying(true)}
      onPause={() => setPlaying(false)}
      onEnded={() => setPlaying(false)}
      onError={() => { setLoading(false); setPlaying(false); setError("This song could not be played."); }} />
    <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
      {track ? <Cover id={track.id} size={48} radius={10} /> : <div style={{ width: 48, height: 48, borderRadius: 10, background: "var(--panel)" }} />}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {track ? track.title : "Nothing playing"}
        </div>
        <div className="au-mono" style={{ fontSize: 12, color: error ? "var(--warn)" : "var(--steel)" }}>
          {error || (loading && track ? "preparing preview…" : track ? [track.bpm && `${track.bpm} BPM`, track.key].filter(Boolean).join(" · ") : "choose a song to listen")}
        </div>
      </div>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "center", minWidth: 0 }}>
      <span className="au-mono" style={{ fontSize: 11, color: "var(--steel)" }}>{fmtTime(time)}</span>
      <button className="au-play" onClick={toggle} disabled={!track} aria-label={playing ? "Pause" : "Play"}>
        <PlayGlyph playing={playing} />
      </button>
      <div className="au-progress" style={{ maxWidth: 560 }} onClick={seek} role="slider" aria-label="Position"
        aria-valuemin={0} aria-valuemax={Math.round(duration) || 0} aria-valuenow={Math.round(time)} tabIndex={track ? 0 : -1}
        onKeyDown={e => {
          if (!audio.current) return;
          if (e.key === "ArrowRight") audio.current.currentTime += 5;
          if (e.key === "ArrowLeft") audio.current.currentTime -= 5;
        }}>
        <div style={{ width: `${duration ? (time / duration) * 100 : 0}%` }} />
      </div>
      <span className="au-mono" style={{ fontSize: 11, color: "var(--steel)" }}>{fmtTime(duration)}</span>
    </div>
    <div className="au-player-right" style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}>
      {track && onOpen && <button className="au-btn" style={{ height: 36, fontSize: 13 }} onClick={() => onOpen(track)}>Song details</button>}
      <span style={{ color: "var(--steel)", display: "flex" }}><Icon name="volume" size={18} /></span>
      <input type="range" min="0" max="1" step="0.01" value={volume} aria-label="Volume"
        onChange={e => setVolume(Number(e.target.value))} style={{ width: 90, accentColor: "#efe9dc" }} />
    </div>
  </footer>;
}
