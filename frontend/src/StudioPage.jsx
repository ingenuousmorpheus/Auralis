import React from "react";
import EnginesPanel from "./EnginesPanel.jsx";
import { Icon } from "./ui.jsx";

/* Studio hub: the finishing tools that already run locally. A per-song stem
   studio (lanes, section regenerate) arrives with generated songs. */

export default function StudioPage({ API, go, tools }) {
  const blurbs = {
    master: "Upload a stereo mix. Match a reference if you like, hit a loudness target with a true-peak ceiling.",
    mix: "Drop every stem. Auralis labels roles, balances and carves the mix, then masters it.",
    rack: "Any recorded vocal through EQ, de-ess, compression, saturation, doubling and space.",
    harmony: "Compare two tracks in the note domain: key, mode, scale degrees and notes outside the key.",
  };
  return <div className="au-page-scroll">
    <h1 className="au-title au-shine">Studio</h1>
    <p className="au-sub">Finishing tools running on this PC. Your own voice lives in My Voice.</p>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14, marginTop: 22 }}>
      {tools.map(tool => <button key={tool.id} className="au-card au-console" onClick={() => go(tool.id)} style={{
        textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit", padding: 20,
        display: "flex", flexDirection: "column", gap: 10, minHeight: 170,
      }}>
        <Icon name={tool.icon || "studio"} size={26} stroke="#d4af5f" />
        <span style={{ fontSize: 18, fontWeight: 800 }}>{tool.label}</span>
        <span style={{ fontSize: 13, color: "var(--steel)", lineHeight: 1.55 }}>{blurbs[tool.id] || ""}</span>
      </button>)}
      <button className="au-card au-console" onClick={() => go("voice")} style={{
        textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit", padding: 20,
        display: "flex", flexDirection: "column", gap: 10, minHeight: 170, borderColor: "#1d5566",
      }}>
        <Icon name="voice" size={26} stroke="#7fe6ff" />
        <span style={{ fontSize: 18, fontWeight: 800 }}>Sing in my voice</span>
        <span style={{ fontSize: 13, color: "var(--steel)", lineHeight: 1.55 }}>Convert a guide vocal into your trained voice, then pitch-polish and finish it inside the beat.</span>
      </button>
    </div>
    {API && <details style={{ marginTop: 22 }}>
      <summary style={{ cursor: "pointer", fontWeight: 700 }}>Advanced: engines and GPU</summary>
      <EnginesPanel API={API} />
    </details>}
  </div>;
}
