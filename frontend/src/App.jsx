import React, { useState } from "react";
import ReferenceMatch from "./ReferenceMatch.jsx";
import PluginLibrary from "./PluginLibrary.jsx";
import CreatePage from "./CreatePage.jsx";
import DnaPage from "./DnaPage.jsx";
import MasterMix from "./MasterMix.jsx";
import MyMusic from "./MyMusic.jsx";
import ProjectsPanel from "./ProjectsPanel.jsx";
import StudioPage from "./StudioPage.jsx";
import VocalRack from "./VocalRack.jsx";
import VoicePage from "./VoicePage.jsx";
import VoiceStudio from "./VoiceStudio.jsx";
import { PlayerBar, Sidebar } from "./Shell.jsx";
import "./App.css";
import "./theme.css";
import "./lux.css";
import "./shell-lux.css";

const API = import.meta.env.VITE_API ?? "http://127.0.0.1:8001";

// Shell look: "lux" (approved luxury direction) or "classic" (the original
// gold console, kept intact in theme.css). `?shell=classic` / `?shell=lux`
// switches and is remembered; VITE_SHELL sets the build default.
const SHELLS = ["lux", "classic"];
function pickShell() {
  try {
    const asked = new URLSearchParams(window.location.search).get("shell");
    if (SHELLS.includes(asked)) { localStorage.setItem("auralis.shell", asked); return asked; }
    const kept = localStorage.getItem("auralis.shell");
    if (SHELLS.includes(kept)) return kept;
  } catch { /* storage blocked: use the default */ }
  return SHELLS.includes(import.meta.env.VITE_SHELL) ? import.meta.env.VITE_SHELL : "lux";
}
document.documentElement.dataset.shell = pickShell();

// Optional screens: shown only when their module exists in this checkout.
const optional = import.meta.glob("./HarmonicReference.jsx", { eager: true });
const HarmonicReference = optional["./HarmonicReference.jsx"]?.default ?? null;

const TOOLS = [
  { id: "reference-match", label: "Match the demo", icon: "voice" },
  { id: "plugins", label: "Plugin Library", icon: "studio" },
  { id: "master", label: "Master a mix", icon: "wave" },
  { id: "mix", label: "Mix from stems", icon: "studio" },
  { id: "rack", label: "Vocal chain", icon: "voice" },
  ...(HarmonicReference ? [{ id: "harmony", label: "Harmonic reference", icon: "music" }] : []),
];

// Style hooks the voice screen takes as props, in the console palette.
const VOICE_COLORS = {
  V: "#d4af5f", T: "#7fe6ff", PK: "#ff9a7a",
  PANEL2: "#131720", TEXT: "#efe9dc", MUTE: "#9aa1ad",
};
const voiceCard = {
  background: "#0e1116", borderRadius: 18, padding: 18,
  border: "1px solid #222834", boxShadow: "0 18px 60px rgba(0,0,0,.35)",
};
const voiceBtn = primary => ({
  width: "100%", padding: 15, borderRadius: 14, cursor: "pointer", fontSize: 15, fontWeight: 800,
  marginTop: 12, fontFamily: "inherit",
  border: primary ? "none" : "1px solid #2d3441",
  background: primary ? "#d4af5f" : "#131720",
  color: primary ? "#1a1206" : "#efe9dc",
});

function toTrack(song) {
  const sm = song.summary || {};
  return { id: song.id, title: song.title, bpm: sm.bpm, key: sm.key, duration: sm.duration_seconds };
}

export default function App() {
  const [page, setPage] = useState("create");
  const [track, setTrack] = useState(null);
  const play = song => setTrack(toTrack(song));

  let content;
  if (page === "create") content = <CreatePage API={API} go={setPage} play={play} nowPlayingId={track?.id} />;
  else if (page === "music") content = <MyMusic API={API} play={play} nowPlayingId={track?.id} />;
  else if (page === "dna") content = <DnaPage API={API} go={setPage} play={play} />;
  else if (page === "studio") content = <StudioPage API={API} go={setPage} tools={TOOLS} />;
  else if (page === "master" || page === "mix") content = <MasterMix API={API} mode={page} />;
  else if (page === "projects") content = <div className="au-page-scroll"><ProjectsPanel API={API} /></div>;
  else if (page === "voice") content = <div className="au-page-scroll" style={{ padding: 0 }}>
    <VoicePage API={API} go={setPage} classic={<main className="voice-stage voice-studio-shell">
      <VoiceStudio API={API} card={voiceCard} btn={voiceBtn} colors={VOICE_COLORS} />
    </main>} />
  </div>;
  else if (page === "reference-match") content = <ReferenceMatch API={API} />;
  else if (page === "plugins") content = <PluginLibrary API={API} />;
  else if (page === "rack") content = <div className="au-page-scroll"><VocalRack API={API} /></div>;
  else if (page === "harmony" && HarmonicReference) content = <div className="au-page-scroll"><HarmonicReference API={API} /></div>;

  return <div className="au-shell">
    <div className="au-scan" aria-hidden="true" />
    <Sidebar API={API} page={page} go={setPage} tools={TOOLS} />
    <div className="au-page">{content}</div>
    <PlayerBar API={API} track={track} onOpen={() => setPage("music")} />
  </div>;
}
