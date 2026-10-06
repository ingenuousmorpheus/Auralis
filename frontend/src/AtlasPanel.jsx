/* Song Blueprint view (AU-04). Uses the approved Lux token set. */

.bp { display: flex; flex-direction: column; gap: 14px; padding: 0 28px 24px; }
.bp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.bp-title-input {
  font-family: var(--font-display); font-size: 20px; letter-spacing: 0.02em; color: var(--lx-text);
  background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 4px 8px; margin-left: -8px;
  width: min(520px, 100%);
}
.bp-title-input:hover, .bp-title-input:focus { border-color: var(--lx-border-strong); outline: none; }
.bp-meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 6px; }

.bp-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.bp-fact { background: var(--lx-surface); border: 1px solid var(--lx-border); border-radius: 14px; padding: 10px 12px; min-width: 0; }
.bp-fact .au-input { height: 36px; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 0 10px; }
.bp-fact-value { font-family: var(--font-mono); font-size: 18px; margin-top: 6px; color: var(--lx-cyan); }

.bp-why { font-size: 12px; color: var(--lx-muted); line-height: 1.5; margin-top: 6px; }
.bp-why li { margin: 2px 0; }
.bp-why ul { margin: 0; padding-left: 16px; }
.bp-why-toggle {
  background: none; border: none; padding: 0; margin-top: 6px; cursor: pointer; font: inherit;
  font-size: 12px; font-weight: 700; color: var(--lx-violet);
}

.bp-curve { background: var(--lx-surface); border: 1px solid var(--lx-border); border-radius: 14px; padding: 12px; }
.bp-curve svg { display: block; width: 100%; height: 96px; }

.bp-section {
  background: var(--lx-surface); border: 1px solid var(--lx-border); border-radius: 16px; padding: 12px 14px;
  display: flex; flex-direction: column; gap: 10px; box-shadow: var(--lx-glow);
}
.bp-section-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.bp-section-head .au-input { height: 34px; padding: 0 8px; }
.bp-section-name { font-weight: 800; font-size: 14px; min-width: 96px; color: var(--lx-text); }
.bp-bars { width: 64px; }
.bp-tools { margin-left: auto; display: flex; gap: 4px; }
.bp-icon {
  height: 32px; min-width: 32px; padding: 0 8px; border-radius: 9px; cursor: pointer;
  background: transparent; border: 1px solid var(--lx-border); color: var(--lx-muted); font: inherit; font-size: 12px; font-weight: 700;
}
.bp-icon:hover:not(:disabled) { color: var(--lx-text); border-color: var(--lx-border-strong); }
.bp-icon:disabled { opacity: 0.35; cursor: default; }

.bp-chords { display: flex; gap: 6px; flex-wrap: wrap; }
.bp-chord {
  display: flex; flex-direction: column; align-items: center; min-width: 58px; padding: 6px 8px;
  border-radius: 10px; background: rgba(255,255,255,0.03); border: 1px solid var(--lx-border);
}
.bp-chord b { font-family: var(--font-mono); font-size: 13px; color: var(--lx-cyan); font-weight: 500; }
.bp-chord span { font-size: 11px; color: var(--lx-muted); font-family: var(--font-mono); }
.bp-chord-edit { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; }
.bp-chord-edit .au-input { height: 34px; width: 100%; box-sizing: border-box; padding: 0 10px; font-family: var(--font-mono); font-size: 13px; }

.bp-roles { display: flex; gap: 6px; flex-wrap: wrap; }
.bp-role {
  height: 28px; padding: 0 10px; border-radius: 999px; cursor: pointer; font: inherit; font-size: 12px; font-weight: 700;
  border: 1px solid var(--lx-border); background: transparent; color: var(--lx-muted);
}
.bp-role[data-level="light"] { color: var(--lx-text); border-color: var(--lx-border-strong); }
.bp-role[data-level="medium"] { color: var(--lx-text); background: rgba(160, 139, 255, 0.08); border-color: rgba(160, 139, 255, 0.32); }
.bp-role[data-level="full"] { color: #100d17; background: linear-gradient(135deg, var(--lx-violet), var(--lx-magenta)); border-color: transparent; }

.bp-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--lx-muted); }
.bp-row input[type="range"] { accent-color: var(--lx-violet); width: 120px; }

.bp-grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.bp-panel { background: var(--lx-surface); border: 1px solid var(--lx-border); border-radius: 14px; padding: 12px 14px; font-size: 13px; color: var(--lx-text); }
.bp-check { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px; line-height: 1.45; }
.bp-check i { font-style: normal; font-weight: 800; }
.bp-alert { border-radius: 12px; padding: 10px 12px; font-size: 13px; line-height: 1.5; }
.bp-alert.warn { background: rgba(255, 133, 151, 0.08); color: var(--lx-danger); border: 1px solid rgba(255, 133, 151, 0.25); }
.bp-alert.note { background: rgba(242, 196, 111, 0.10); color: var(--lx-warning); border: 1px solid rgba(242, 196, 111, 0.25); }

@media (max-width: 720px) {
  .bp { padding: 0 16px 20px; }
  .bp-chord-edit { grid-template-columns: 1fr; }
  .bp-tools { margin-left: 0; }
}

