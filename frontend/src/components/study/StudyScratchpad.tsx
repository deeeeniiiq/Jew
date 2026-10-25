import React, { useEffect, useRef, useState } from "react";
import type { StudyPoint, StudyStroke } from "../../lib/types";

type Tool = "pen" | "highlighter" | "eraser";

function pathFor(points: StudyPoint[]): string {
  if (!points.length) return "";
  if (points.length === 1) {
    const { x, y } = points[0];
    // SVG treats a move-only path as invisible: a tap must leave a dot.
    return `M ${x * 1000} ${y * 700} l .01 0`;
  }
  const [first, ...rest] = points;
  return `M ${first.x * 1000} ${first.y * 700} ${rest.map(point => `L ${point.x * 1000} ${point.y * 700}`).join(" ")}`;
}

function distanceToStroke(point: StudyPoint, stroke: StudyStroke): number {
  let distance = Infinity;
  for (let i = 0; i < stroke.points.length; i++) {
    const a = stroke.points[i];
    const b = stroke.points[i + 1] ?? a;
    const dx = b.x - a.x;
    const dy = (b.y - a.y) * .7;
    const lengthSq = dx * dx + dy * dy;
    const along = lengthSq ? Math.max(0, Math.min(1,
      ((point.x - a.x) * dx + (point.y - a.y) * .7 * dy) / lengthSq)) : 0;
    distance = Math.min(distance, Math.hypot(a.x + along * dx - point.x,
      (a.y - point.y) * .7 + along * dy));
  }
  return distance;
}

export function StudyScratchpad({ questionId, strokes, onChange, disabled }: {
  questionId: string;
  strokes: StudyStroke[];
  onChange: (strokes: StudyStroke[]) => void;
  disabled: boolean;
}): React.JSX.Element {
  const canvasRef = useRef<SVGSVGElement>(null);
  const pendingRef = useRef<StudyPoint[]>([]);
  const [pending, setPending] = useState<StudyPoint[]>([]);
  const [tool, setTool] = useState<Tool>("pen");
  const [color, setColor] = useState("#e2a077");
  const [width, setWidth] = useState(3);
  const [redo, setRedo] = useState<StudyStroke[]>([]);

  useEffect(() => { setRedo([]); setPending([]); pendingRef.current = []; }, [questionId]);

  function pointFor(event: React.PointerEvent<SVGSVGElement>): StudyPoint | null {
    const matrix = canvasRef.current?.getScreenCTM();
    if (!matrix) return null;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    return { x: Math.max(0, Math.min(1, point.x / 1000)), y: Math.max(0, Math.min(1, point.y / 700)) };
  }

  function pointerDown(event: React.PointerEvent<SVGSVGElement>): void {
    if (disabled || event.button !== 0) return;
    const point = pointFor(event);
    if (!point) return;
    if (tool === "eraser") {
      const nearest = strokes.map((stroke, index) => ({ index, distance: distanceToStroke(point, stroke) }))
        .sort((a, b) => a.distance - b.distance)[0];
      if (nearest && nearest.distance < .035) { onChange(strokes.filter((_, i) => i !== nearest.index)); setRedo([]); }
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    pendingRef.current = [point];
    setPending([point]);
  }

  function pointerMove(event: React.PointerEvent<SVGSVGElement>): void {
    if (disabled || !event.currentTarget.hasPointerCapture(event.pointerId) || !pendingRef.current.length) return;
    const point = pointFor(event);
    if (!point || pendingRef.current.length >= 1200) return;
    pendingRef.current = [...pendingRef.current, point];
    setPending(pendingRef.current);
  }

  function pointerEnd(event: React.PointerEvent<SVGSVGElement>): void {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    const points = pendingRef.current;
    pendingRef.current = [];
    setPending([]);
    if (disabled || !points.length || strokes.length >= 600) return;
    onChange([...strokes, {
      id: globalThis.crypto?.randomUUID?.() ?? `stroke-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      tool: tool === "highlighter" ? "highlighter" : "pen", color, width, points,
    }]);
    setRedo([]);
  }

  function pointerCancel(event: React.PointerEvent<SVGSVGElement>): void {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    pendingRef.current = [];
    setPending([]);
  }

  function undo(): void {
    const last = strokes.at(-1);
    if (!last) return;
    setRedo(current => [...current, last]);
    onChange(strokes.slice(0, -1));
  }

  function redoStroke(): void {
    const last = redo.at(-1);
    if (!last) return;
    onChange([...strokes, last]);
    setRedo(current => current.slice(0, -1));
  }

  return <section className="studyPad" aria-label="Caderno digital para cálculos e rabiscos">
    <div className="studyPadTools" role="toolbar" aria-label="Ferramentas de desenho">
      {(["pen", "highlighter", "eraser"] as Tool[]).map(item => <button key={item}
        type="button" disabled={disabled} aria-pressed={tool === item}
        className={tool === item ? "studyTool studyToolActive" : "studyTool"} onClick={() => setTool(item)}>
        {{ pen: "Caneta", highlighter: "Marca-texto", eraser: "Borracha" }[item]}
      </button>)}
      <label className="studyColor">Cor <input aria-label="Cor do traço" type="color" value={color}
        onChange={event => setColor(event.target.value)} disabled={disabled} /></label>
      <label className="studyWidth">Traço <input aria-label="Espessura do traço" type="range" min={1} max={18}
        value={width} onChange={event => setWidth(Number(event.target.value))} disabled={disabled} /></label>
      <button type="button" className="studyTool" onClick={undo} disabled={disabled || !strokes.length}>Desfazer</button>
      <button type="button" className="studyTool" onClick={redoStroke} disabled={disabled || !redo.length}>Refazer</button>
      <button type="button" className="studyTool" disabled={disabled || !strokes.length}
        onClick={() => { if (window.confirm("Limpar os desenhos desta questão?")) { onChange([]); setRedo([]); } }}>Limpar</button>
    </div>
    <svg ref={canvasRef} viewBox="0 0 1000 700" className="studyPadCanvas"
      aria-label="Área de desenho" role="img" onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={pointerEnd} onPointerCancel={pointerCancel}>
      <title>Rascunho da questão</title>
      {strokes.map(stroke => <path key={stroke.id} d={pathFor(stroke.points)} fill="none"
        stroke={stroke.color} strokeWidth={stroke.width} strokeLinecap="round" strokeLinejoin="round"
        opacity={stroke.tool === "highlighter" ? .38 : 1} />)}
      {pending.length ? <path d={pathFor(pending)} fill="none" stroke={color} strokeWidth={width}
        opacity={tool === "highlighter" ? .38 : 1} strokeLinecap="round" strokeLinejoin="round" /> : null}
    </svg>
    <div className="studyPadHint">Mouse, toque ou caneta digital. Os traços são ligados à questão e salvos como vetores.</div>
  </section>;
}
