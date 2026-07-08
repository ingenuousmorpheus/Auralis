import React, { useCallback, useEffect, useRef, useState } from "react";

/* Rotary knob in the iZotope idiom: 270° sweep, arc fill from its neutral
   point, vertical drag (hold Shift for fine control), double-click to reset. */
export default function Knob({
  label,
  value,
  min,
  max,
  defaultValue,
  unit = "",
  decimals = 1,
  bipolar = false,
  accent = "#66e8ff",
  disabled = false,
  size = 64,
  onChange,
}) {
  const [dragging, setDragging] = useState(false);
  const dragState = useRef(null);

  const span = max - min;
  const clamped = Math.min(max, Math.max(min, value));
  const norm = (clamped - min) / span;                 // 0..1
  const SWEEP = 270;                                   // degrees
  const START = -225;                                  // pointing down-left
  const angle = START + norm * SWEEP;

  // Arc fills from the visual zero: center for bipolar knobs, left for unipolar.
  const zeroNorm = bipolar ? (0 - min) / span : 0;
  const arcFrom = Math.min(norm, zeroNorm);
  const arcTo = Math.max(norm, zeroNorm);

  const onPointerDown = useCallback(event => {
    if (disabled) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragState.current = { startY: event.clientY, startValue: clamped };
    setDragging(true);
  }, [disabled, clamped]);

  useEffect(() => {
    if (!dragging) return;
    const move = event => {
      const state = dragState.current;
      if (!state) return;
      const fine = event.shiftKey ? 0.18 : 1;
      const delta = ((state.startY - event.clientY) / 160) * span * fine;
      const next = Math.min(max, Math.max(min, state.startValue + delta));
      onChange(Number(next.toFixed(3)));
    };
    const up = () => { dragState.current = null; setDragging(false); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [dragging, min, max, span, onChange]);

  const r = size / 2;
  const track = r - 5;
  const polar = (deg, radius) => {
    const rad = (deg * Math.PI) / 180;
    return [r + radius * Math.cos(rad), r + radius * Math.sin(rad)];
  };
  const arcPath = (fromNorm, toNorm, radius) => {
    const a0 = START + fromNorm * SWEEP;
    const a1 = START + toNorm * SWEEP;
    const [x0, y0] = polar(a0, radius);
    const [x1, y1] = polar(a1, radius);
    const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
    return `M ${x0} ${y0} A ${radius} ${radius} 0 ${large} 1 ${x1} ${y1}`;
  };
  const [tipX, tipY] = polar(angle, track - 7);

  const shown = Number(clamped.toFixed(decimals));
  const display = `${bipolar && shown > 0 ? "+" : ""}${shown}${unit}`;

  return (
    <div
      className={`knob ${disabled ? "knob-disabled" : ""} ${dragging ? "knob-active" : ""}`}
      onPointerDown={onPointerDown}
      onDoubleClick={() => !disabled && onChange(defaultValue ?? (bipolar ? 0 : min))}
      title={`${label}: drag to adjust · Shift = fine · double-click = reset`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <path d={arcPath(0, 1, track)} className="knob-track" />
        <path d={arcPath(arcFrom, arcTo, track)} className="knob-fill" style={{ stroke: accent }} />
        <circle cx={r} cy={r} r={track - 11} className="knob-cap" />
        <line x1={r} y1={r} x2={tipX} y2={tipY} className="knob-pointer" style={{ stroke: accent }} />
      </svg>
      <div className="knob-value" style={{ color: dragging ? accent : undefined }}>{display}</div>
      <div className="knob-label">{label}</div>
    </div>
  );
}
