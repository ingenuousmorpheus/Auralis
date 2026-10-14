import React, { useEffect, useState } from "react";
import { apiJson } from "./ui.jsx";

/* Which guide singer sings the song (Session 025). The guide performs the
   melody before My Voice turns it into your voice; only some guides sing words.
   The choice is remembered; vocalise stays the default until the word guide is
   approved. Never implies a wordless guide sings the lyrics. */

const KEY = "auralis.guide";
const DESCRIBE = {
  vocalise: { label: "Vocalise", line: "Melody and lyric rhythm on vowels. Does not sing words." },
  "word-guide": { label: "Word guide · experimental", line: "Sings your lyrics as words, plainly. Personal, local use only until the speech voice's licence is reviewed." },
  diffsinger: { label: "DiffSinger", line: "Lyric singing engine." },
};

export function rememberedGuide() {
  try { return localStorage.getItem(KEY) || ""; } catch { return ""; }
}

/* `value` is a guide id or "" (the engine chosen in Studio → Advanced). */
export function GuideChoice({ API, value, onChange, hasLyrics }) {
  const [options, setOptions] = useState(null);
  useEffect(() => {
    apiJson(`${API}/models`).then(m => {
      setOptions((m.models || []).filter(x => x.kind === "guide_singer" && x.installed));
      if (!value) onChange(m.kinds?.guide_singer?.active || "vocalise");
    }).catch(() => setOptions([]));
  }, [API]);
  if (!options || options.length < 2) return <GuideNotice guide={value || "vocalise"} hasLyrics={hasLyrics} />;
  const pick = id => { onChange(id); try { localStorage.setItem(KEY, id); } catch { /* private mode */ } };
  return <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <span className="au-caption">Guide singer</span>
      <div className="au-segment" role="radiogroup" aria-label="Guide singer">
        {options.map(o => <button key={o.id} role="radio" aria-checked={value === o.id} aria-selected={value === o.id}
          title={DESCRIBE[o.id]?.line || o.notes} onClick={() => pick(o.id)}>{DESCRIBE[o.id]?.label || o.name}</button>)}
      </div>
    </div>
    <GuideNotice guide={value} hasLyrics={hasLyrics} />
  </div>;
}

/* The notice itself: shown before singing (from the choice) and after (from the song's own record). */
export function GuideNotice({ guide, hasLyrics, text }) {
  const wordless = guide === "vocalise" || guide === "" || guide == null;
  const message = text || (!hasLyrics ? null : wordless
    ? "This guide will not sing your lyrics. The vocal follows the melody and the rhythm of your words on vowels only, so it will sound like wordless ad-libs. Choose the word guide to hear the words."
    : guide === "word-guide"
      ? "Experimental word guide: your lyrics are sung as words, plainly, then turned into your voice. Personal, local use only until the speech voice's licence is reviewed."
      : null);
  if (!message) return null;
  const warn = text ? /Wordless/.test(text) : wordless;
  return <div role="note" className={`bp-alert ${warn ? "warn" : "note"}`} style={{ fontSize: 12, lineHeight: 1.5 }}>{message}</div>;
}
