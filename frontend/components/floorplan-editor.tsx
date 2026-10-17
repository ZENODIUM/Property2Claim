"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, Image as KonvaImage, Layer, Line, Rect, Stage, Text } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";
import {
  AlertTriangle,
  Bot,
  Boxes,
  Check,
  ChevronRight,
  ClipboardCheck,
  Crosshair,
  DollarSign,
  Eye,
  EyeOff,
  FileSearch,
  Flame,
  Gauge,
  ImageIcon,
  Layers3,
  MousePointer2,
  Pencil,
  PlusSquare,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Wrench,
  Zap,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { API_URL, api } from "@/lib/api";
import { currency } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/status-pill";

type Geometry = { x?: number; y?: number; w?: number; h?: number; points?: number[][] };
type MediaItem = { type: string; title: string; url: string; source: string; illustrative: boolean };
type TimelineItem = { date: string; label: string; state: string };
type ObjectDetails = {
  asset?: { name: string; id: string; type: string; location: string; condition: string; operational_status: string; declared_insured_value_cents: number; criticality: string };
  inspection?: { last_inspection_date: string; result: string; next_due_date: string; issues: string[] };
  media?: MediaItem[];
  documents?: Array<{ title: string; type: string; source: string; status?: string }>;
  evidence_summary?: string;
  evidence_summary_source?: string;
  incidents?: Array<{ date: string; status: string; summary: string; claim_id: number; claim_number: string; preliminary_repair_estimate_cents?: number }>;
  ai_insights?: { concerns: string[]; missing_or_conflicting_evidence: string[]; recommended_next_action: string; decision_boundary: string };
  financial_exposure?: { declared_value_cents: number; potential_damage_cost_cents?: number; estimate_state: string };
  timelines?: { inspection: TimelineItem[]; incidents: TimelineItem[] };
  status_indicator?: "green" | "amber" | "red" | "blue" | "grey";
};

export type FloorObject = {
  id: number;
  floor_plan_id: number;
  asset_id?: number;
  object_type: string;
  label: string;
  geometry_type: "point" | "rect" | "polygon";
  geometry: Geometry;
  layer: string;
  human_verified: boolean;
  details: ObjectDetails;
  source_mode: string;
  analysis_model?: string;
  confidence_label?: string;
};

type RelatedPlan = { id: number; name: string; plan_type: string; is_base: boolean; preview_url: string; analysis_status: string; analysis_model?: string };
export type FloorPlan = {
  id: number;
  property_id: number;
  property_name: string;
  name: string;
  preview_url: string;
  width?: number;
  height?: number;
  state: string;
  revision: number;
  analysis_status: string;
  analysis_model?: string;
  objects: FloorObject[];
  related_plans: RelatedPlan[];
  related_claims: Array<{ id: number; claim_number: string; status: string }>;
  validation: string;
};

type RegionResult = {
  possibly_affected_object_ids: number[];
  objects: FloorObject[];
  summary: { asset_count: number; human_verified_count: number; total_declared_asset_value_cents: number; reported_or_confirmed_damaged_assets: number; linked_incident_count: number; linked_evidence_count: number; preliminary_potential_loss_estimate_cents?: number };
  disclaimer: string;
};

type Tool = "select" | "pan" | "annotate" | "region_polygon" | "region_rectangle";

const LAYERS = [
  { id: "machinery", label: "Machinery", icon: Boxes, color: "#52a8ff" },
  { id: "fire_safety", label: "Fire safety", icon: Flame, color: "#fb7185" },
  { id: "utilities", label: "Utilities", icon: Zap, color: "#a78bfa" },
  { id: "building_zones", label: "Building zones", icon: Layers3, color: "#2dd4bf" },
  { id: "inspections", label: "Inspections", icon: ClipboardCheck, color: "#fbbf24", derived: true },
  { id: "evidence", label: "Evidence", icon: FileSearch, color: "#60a5fa", derived: true },
  { id: "incidents", label: "Incidents", icon: AlertTriangle, color: "#fb7185", derived: true },
  { id: "financial_exposure", label: "Financial exposure", icon: DollarSign, color: "#34d399", derived: true },
  { id: "ai_findings", label: "AI findings", icon: Sparkles, color: "#c084fc", derived: true },
] as const;

const STATUS_COLORS: Record<string, string> = { green: "#34d399", amber: "#fbbf24", red: "#fb7185", blue: "#60a5fa", grey: "#94a3b8" };

function useImage(url: string) {
  const [image, setImage] = useState<HTMLImageElement>();
  useEffect(() => {
    const next = new window.Image();
    next.onload = () => setImage(next);
    next.src = url;
  }, [url]);
  return image;
}

function MiniTimeline({ items, empty }: { items: TimelineItem[]; empty: string }) {
  if (!items.length) return <p className="text-[11px] text-slate-500">{empty}</p>;
  return <div className="relative space-y-3 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-white/10">
    {items.map((item, index) => <div className="relative flex gap-3" key={`${item.date}-${index}`}><span className={`mt-1 size-[11px] shrink-0 rounded-full border-2 border-[#202833] ${item.state === "due" || item.state === "reported" ? "bg-amber-400" : "bg-teal-400"}`} /><div><div className="text-[11px] font-semibold text-slate-200">{item.label}</div><div className="text-[10px] text-slate-500">{item.date.slice(0, 10)} · {item.state}</div></div></div>)}
  </div>;
}

function DetailSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return <section className="border-t border-white/[.07] py-4 first:border-0 first:pt-0"><div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.12em] text-slate-400">{icon}{title}</div>{children}</section>;
}

export function FloorplanEditor({ initialPlan }: { initialPlan: FloorPlan }) {
  const [plan, setPlan] = useState(initialPlan);
  const [selected, setSelected] = useState<FloorObject>();
  const [tool, setTool] = useState<Tool>("select");
  const [activePlan, setActivePlan] = useState(initialPlan.id);
  const [region, setRegion] = useState<number[][]>([]);
  const [regionResult, setRegionResult] = useState<RegionResult>();
  const [hidden, setHidden] = useState<string[]>([]);
  const [width, setWidth] = useState(860);
  const [zoom, setZoom] = useState(1);
  const [stagePosition, setStagePosition] = useState({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const [editing, setEditing] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const base = API_URL.replace(/\/api$/, "");
  const selectedPlan = plan.related_plans.find((item) => item.id === activePlan) ?? plan.related_plans[0];
  const background = useImage(`${base}${selectedPlan?.preview_url ?? plan.preview_url}`);
  const ratio = plan.width && plan.height ? plan.height / plan.width : 1;
  const height = Math.max(480, Math.round(width * ratio));

  useEffect(() => {
    if (!wrap.current) return;
    const observer = new ResizeObserver((entries) => setWidth(Math.max(620, entries[0].contentRect.width)));
    observer.observe(wrap.current);
    return () => observer.disconnect();
  }, []);

  const layerCounts = useMemo(() => Object.fromEntries(LAYERS.map((layer) => {
    let count = plan.objects.filter((object) => object.layer === layer.id).length;
    if (layer.id === "inspections") count = plan.objects.filter((object) => (object.details.inspection?.issues.length ?? 0) > 0).length;
    if (layer.id === "evidence") count = plan.objects.filter((object) => (object.details.media?.length ?? 0) > 0).length;
    if (layer.id === "incidents") count = plan.objects.filter((object) => (object.details.incidents?.length ?? 0) > 0).length;
    if (layer.id === "financial_exposure") count = plan.objects.filter((object) => (object.details.asset?.declared_insured_value_cents ?? 0) > 0).length;
    if (layer.id === "ai_findings") count = plan.objects.filter((object) => !object.human_verified).length;
    return [layer.id, count];
  })), [plan.objects]);

  const visibleObjects = useMemo(() => plan.objects.filter((object) => !hidden.includes(object.layer)), [plan.objects, hidden]);

  async function refresh(preselectId?: number) {
    const next = await api<FloorPlan>(`/floorplans/${plan.id}`);
    setPlan(next);
    if (preselectId) setSelected(next.objects.find((item) => item.id === preselectId));
  }

  function resetView() {
    setZoom(1);
    setStagePosition({ x: 0, y: 0 });
  }

  function pointerNormalized(event: KonvaEventObject<MouseEvent>) {
    const stage = event.target.getStage();
    const point = stage?.getRelativePointerPosition();
    if (!point) return;
    return { x: Math.max(0, Math.min(1, point.x / width)), y: Math.max(0, Math.min(1, point.y / height)) };
  }

  async function stageClick(event: KonvaEventObject<MouseEvent>) {
    if (event.target !== event.target.getStage() && event.target.name() !== "background") return;
    const point = pointerNormalized(event);
    if (!point) return;
    if (tool === "annotate") {
      const created = await api<FloorObject>(`/floorplans/${plan.id}/objects`, { method: "POST", body: JSON.stringify({ object_type: "equipment", label: `New annotation ${plan.objects.length + 1}`, geometry_type: "rect", geometry: { x: Math.min(point.x, .9), y: Math.min(point.y, .92), w: .08, h: .06 }, layer: "machinery", human_verified: false, details: {}, source_mode: "human" }) });
      setTool("select");
      await refresh(created.id);
      setEditing(true);
    } else if (tool === "region_polygon") {
      setRegion((points) => [...points, [point.x, point.y]]);
    } else if (tool === "region_rectangle") {
      if (!region.length) setRegion([[point.x, point.y]]);
      else {
        const [start] = region;
        setRegion([[start[0], start[1]], [point.x, start[1]], [point.x, point.y], [start[0], point.y]]);
      }
    } else {
      setSelected(undefined);
      setRegionResult(undefined);
    }
  }

  async function updateRect(object: FloorObject, event: KonvaEventObject<DragEvent>) {
    const node = event.target;
    await api(`/floor-objects/${object.id}`, { method: "PATCH", body: JSON.stringify({ asset_id: object.asset_id ?? null, object_type: object.object_type, label: object.label, geometry_type: object.geometry_type, geometry: { ...object.geometry, x: node.x() / width, y: node.y() / height }, layer: object.layer, human_verified: object.human_verified, details: object.details, source_mode: object.source_mode, analysis_model: object.analysis_model ?? null, confidence_label: object.confidence_label ?? null }) });
    await refresh(object.id);
  }

  async function verify() {
    if (!selected) return;
    await api(`/floorplans/${plan.id}/verify-objects`, { method: "POST", body: JSON.stringify([selected.id]) });
    await refresh(selected.id);
  }

  async function intersect() {
    if (region.length < 3) return;
    const result = await api<RegionResult>(`/floorplans/${plan.id}/intersections`, { method: "POST", body: JSON.stringify({ polygon: region }) });
    setRegionResult(result);
    setSelected(undefined);
    setTool("select");
  }

  async function runAnalysis(force = false) {
    setBusy(true);
    setMessage(undefined);
    try {
      const result = await api<{ cached: boolean; created: FloorObject[] }>(`/floorplans/${plan.id}/propose-annotations?authorize_external_analysis=true&include_group=true&force=${force}`, { method: "POST" });
      setMessage(result.cached ? "Loaded the saved Gemini analysis. No provider call was made." : `Saved ${result.created.length} new proposals for review.`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Analysis failed");
    } finally { setBusy(false); }
  }

  async function saveEdit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    const payload = { asset_id: selected.asset_id ?? null, object_type: String(data.get("object_type")), label: String(data.get("label")), geometry_type: selected.geometry_type, geometry: selected.geometry, layer: String(data.get("layer")), human_verified: selected.human_verified, details: selected.details, source_mode: selected.source_mode, analysis_model: selected.analysis_model ?? null, confidence_label: selected.confidence_label ?? null };
    await api(`/floor-objects/${selected.id}`, { method: "PATCH", body: JSON.stringify(payload) });
    setEditing(false);
    await refresh(selected.id);
  }

  async function requestInspection() {
    if (!selected) return;
    const task = await api<{ id: number }>(`/properties/${plan.property_id}/inspection-request?object_id=${selected.id}`, { method: "POST" });
    setMessage(`Inspection review task #${task.id} is queued.`);
  }

  const selectedDetails = selected?.details;
  const claim = selectedDetails?.incidents?.[0] ? plan.related_claims.find((item) => item.id === selectedDetails.incidents?.[0].claim_id) : plan.related_claims[0];

  return <div className="space-y-4">
    <div className="rounded-lg border border-white/[.1] bg-[#202833] p-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto">
          {plan.related_plans.map((item) => <button key={item.id} onClick={() => { setActivePlan(item.id); resetView(); }} className={`flex min-w-[190px] items-center gap-3 rounded-md border p-2 text-left transition ${activePlan === item.id ? "border-blue-400/50 bg-blue-400/10" : "border-white/[.08] bg-black/10 hover:border-white/20"}`}>
            <div className="h-11 w-14 overflow-hidden rounded bg-white"><img alt="" src={`${base}${item.preview_url}`} className="h-full w-full object-cover" /></div>
            <div className="min-w-0"><div className="truncate text-xs font-semibold text-slate-200">{item.name}</div><div className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">{item.plan_type} · {item.analysis_status}</div></div>
          </button>)}
        </div>
        <div className="flex items-center gap-2"><StatusPill tone={plan.analysis_status === "complete" ? "teal" : "amber"}>{plan.analysis_status}</StatusPill><Button size="sm" variant="secondary" disabled={busy} onClick={() => runAnalysis(false)}><Sparkles size={14} />{busy ? "Analyzing…" : plan.analysis_status === "complete" ? "Use saved analysis" : "Analyze plans"}</Button></div>
      </div>
      {message && <div className="mt-3 rounded-md border border-blue-400/20 bg-blue-400/[.08] px-3 py-2 text-xs text-blue-200">{message}</div>}
    </div>

    <div className="grid min-h-[720px] gap-4 2xl:grid-cols-[220px_minmax(620px,1fr)_340px]">
      <aside className="rounded-lg border border-white/[.1] bg-[#1f2731] p-3">
        <div className="flex items-center gap-2 px-1 pb-3 text-xs font-semibold text-slate-200"><Layers3 size={15} className="text-blue-300" />Map layers</div>
        <div className="space-y-1">{LAYERS.map((layer) => {
          const Icon = layer.icon;
          const off = hidden.includes(layer.id);
          return <button key={layer.id} onClick={() => setHidden((items) => off ? items.filter((item) => item !== layer.id) : [...items, layer.id])} className={`group flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition ${off ? "text-slate-600" : "text-slate-300 hover:bg-white/[.05]"}`}>
            <Icon size={14} style={{ color: off ? undefined : layer.color }} /><span className="flex-1 text-xs">{layer.label}</span><span className="text-[10px] tabular-nums text-slate-500">{layerCounts[layer.id] ?? 0}</span>{off ? <EyeOff size={12} /> : <Eye size={12} className="opacity-0 group-hover:opacity-100" />}
          </button>;
        })}</div>
        <div className="mt-5 border-t border-white/[.07] pt-4"><div className="px-1 text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">Status key</div><div className="mt-3 space-y-2 text-[11px] text-slate-400">{[["#34d399", "Verified / no finding"], ["#fbbf24", "Review or inspection due"], ["#fb7185", "Reported incident / critical"], ["#60a5fa", "Evidence available"], ["#94a3b8", "Unknown / unverified"]].map(([color, label]) => <div className="flex items-center gap-2" key={label}><span className="size-2 rounded-full" style={{ background: color }} />{label}</div>)}</div></div>
        <div className="mt-5 rounded-md border border-purple-400/15 bg-purple-400/[.06] p-3"><div className="flex items-center gap-2 text-[11px] font-semibold text-purple-200"><Bot size={13} />Saved AI layer</div><p className="mt-2 text-[10px] leading-4 text-slate-500">{plan.objects.filter((item) => item.source_mode === "gemini_live").length} proposals · {plan.analysis_model ?? "not analyzed"}. Human verification remains required.</p></div>
      </aside>

      <main className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant={tool === "select" ? "default" : "secondary"} onClick={() => setTool("select")}><MousePointer2 size={14} />Select</Button>
          <Button size="sm" variant={tool === "pan" ? "default" : "secondary"} onClick={() => setTool("pan")}><Crosshair size={14} />Pan</Button>
          <Button size="sm" variant={tool === "annotate" ? "default" : "secondary"} onClick={() => setTool("annotate")}><PlusSquare size={14} />Add annotation</Button>
          <Button size="sm" variant={tool === "region_rectangle" ? "default" : "secondary"} onClick={() => { setTool("region_rectangle"); setRegion([]); setRegionResult(undefined); }}><Crosshair size={14} />Select rectangle</Button>
          <Button size="sm" variant={tool === "region_polygon" ? "default" : "secondary"} onClick={() => { setTool("region_polygon"); setRegion([]); setRegionResult(undefined); }}><Pencil size={14} />Select polygon</Button>
          {region.length >= 3 && <Button size="sm" onClick={intersect}><Gauge size={14} />Calculate region</Button>}
          <div className="ml-auto flex gap-1"><Button size="sm" variant="secondary" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(1, value - .25))}><ZoomOut size={14} /></Button><span className="grid min-w-12 place-items-center text-[10px] tabular-nums text-slate-500">{Math.round(zoom * 100)}%</span><Button size="sm" variant="secondary" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(3, value + .25))}><ZoomIn size={14} /></Button><Button size="sm" variant="secondary" aria-label="Reset view" onClick={resetView}><RotateCcw size={14} /></Button></div>
        </div>
        <div ref={wrap} className="relative h-[680px] overflow-hidden rounded-lg border border-white/[.12] bg-[#11161d] shadow-[0_20px_50px_rgba(0,0,0,.22)]">
          <Stage width={width} height={height} scaleX={zoom} scaleY={zoom} x={stagePosition.x} y={stagePosition.y} draggable={tool === "pan"} onDragEnd={(event) => setStagePosition({ x: event.target.x(), y: event.target.y() })} onClick={stageClick} onWheel={(event) => { event.evt.preventDefault(); setZoom((value) => Math.max(1, Math.min(3, value + (event.evt.deltaY > 0 ? -.12 : .12)))); }}>
            <Layer>{background ? <KonvaImage name="background" image={background} width={width} height={height} /> : <><Rect name="background" width={width} height={height} fill="#e5e7eb" /><Text text="Loading original uploaded plan…" x={30} y={30} fill="#475569" /></>}</Layer>
            <Layer>{visibleObjects.map((object) => {
              const active = selected?.id === object.id;
              const status = object.human_verified ? "green" : object.details.status_indicator ?? "grey";
              const color = STATUS_COLORS[status] ?? STATUS_COLORS.grey;
              const onSelect = (event: KonvaEventObject<MouseEvent>) => { event.cancelBubble = true; setSelected(object); setRegionResult(undefined); };
              if (object.geometry_type === "rect") return <Rect key={object.id} x={(object.geometry.x ?? 0) * width} y={(object.geometry.y ?? 0) * height} width={(object.geometry.w ?? .05) * width} height={(object.geometry.h ?? .05) * height} fill={`${color}${active ? "3d" : "20"}`} stroke={active ? "#ffffff" : color} strokeWidth={(active ? 3 : 1.5) / zoom} draggable={tool === "select"} onClick={onSelect} onDragEnd={(event) => updateRect(object, event)} shadowColor={color} shadowBlur={active ? 12 : 4} shadowOpacity={.55} />;
              if (object.geometry_type === "point") return <Circle key={object.id} x={(object.geometry.x ?? 0) * width} y={(object.geometry.y ?? 0) * height} radius={7 / zoom} fill={color} stroke="#fff" strokeWidth={1.5 / zoom} onClick={onSelect} />;
              return <Line key={object.id} points={(object.geometry.points ?? []).flatMap((point) => [point[0] * width, point[1] * height])} closed fill={`${color}22`} stroke={color} strokeWidth={2 / zoom} onClick={onSelect} />;
            })}{region.length > 0 && <Line points={region.flatMap((point) => [point[0] * width, point[1] * height])} closed={region.length >= 3} fill="#60a5fa22" stroke="#60a5fa" strokeWidth={2 / zoom} dash={[7 / zoom, 5 / zoom]} />}</Layer>
            <Layer>{visibleObjects.filter((object) => zoom >= 1.4 || selected?.id === object.id).map((object) => <Text key={`label-${object.id}`} text={object.label} x={(object.geometry.x ?? 0) * width} y={Math.max(0, (object.geometry.y ?? 0) * height - 17 / zoom)} fontSize={10 / zoom} fontStyle="bold" fill="#111827" padding={3 / zoom} listening={false} />)}</Layer>
          </Stage>
          <div className="pointer-events-none absolute bottom-3 left-3 rounded border border-white/10 bg-[#151b23]/90 px-2.5 py-1.5 text-[10px] text-slate-400">Original drawing · normalized overlay · {visibleObjects.length} visible objects</div>
        </div>
      </main>

      <aside className="max-h-[750px] overflow-y-auto rounded-lg border border-white/[.1] bg-[#1f2731] p-4">
        {regionResult ? <div>
          <div className="flex items-center justify-between"><div><div className="text-[10px] font-bold uppercase tracking-[.12em] text-blue-300">Selected region</div><h3 className="mt-1 text-base font-semibold">Exposure summary</h3></div><StatusPill tone="blue">Spatial candidate</StatusPill></div>
          <div className="mt-5 grid grid-cols-2 gap-2">{[["Assets", regionResult.summary.asset_count], ["Declared value", currency(regionResult.summary.total_declared_asset_value_cents, true)], ["Incidents", regionResult.summary.linked_incident_count], ["Evidence", regionResult.summary.linked_evidence_count]].map(([label, value]) => <div key={label} className="rounded-md border border-white/[.08] bg-black/10 p-3"><div className="text-lg font-semibold text-slate-100">{value}</div><div className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">{label}</div></div>)}</div>
          <div className="mt-4 space-y-2">{regionResult.objects.slice(0, 8).map((object) => <button key={object.id} onClick={() => { setSelected(object); setRegionResult(undefined); }} className="flex w-full items-center gap-2 rounded-md border border-white/[.07] px-3 py-2 text-left hover:bg-white/[.04]"><span className="size-2 rounded-full" style={{ background: STATUS_COLORS[object.details.status_indicator ?? "grey"] }} /><span className="flex-1 truncate text-xs">{object.label}</span><ChevronRight size={13} className="text-slate-600" /></button>)}</div>
          <p className="mt-4 text-[10px] leading-4 text-slate-500">{regionResult.disclaimer}</p>
          {claim && <Link href={`/claims/${claim.id}`} className="mt-4 flex h-9 items-center justify-center gap-2 rounded-md bg-blue-500 text-xs font-semibold text-white hover:bg-blue-400">Open relevant claim <ChevronRight size={13} /></Link>}
        </div> : selected ? <div>
          <div className="flex items-start justify-between gap-3"><div><div className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">{selected.layer.replaceAll("_", " ")}</div><h3 className="mt-1 text-base font-semibold leading-5 text-slate-100">{selected.label}</h3></div><span className="mt-1 size-2.5 shrink-0 rounded-full" title={selectedDetails?.status_indicator} style={{ background: STATUS_COLORS[selected.human_verified ? "green" : selectedDetails?.status_indicator ?? "grey"] }} /></div>
          <div className="mt-3 flex gap-2"><StatusPill tone={selected.human_verified ? "teal" : "amber"}>{selected.human_verified ? "Verified" : "Review required"}</StatusPill>{selected.source_mode === "gemini_live" && <StatusPill tone="blue">Gemini · {selected.confidence_label}</StatusPill>}</div>
          {editing ? <form onSubmit={saveEdit} className="mt-4 space-y-3 rounded-md border border-white/[.08] bg-black/10 p-3"><div><label className="label">Label</label><input name="label" defaultValue={selected.label} className="input" /></div><div><label className="label">Object type</label><input name="object_type" defaultValue={selected.object_type} className="input" /></div><div><label className="label">Layer</label><select name="layer" defaultValue={selected.layer} className="input">{LAYERS.filter((item) => !("derived" in item && item.derived)).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></div><div className="flex gap-2"><Button size="sm" type="submit">Save</Button><Button size="sm" type="button" variant="secondary" onClick={() => setEditing(false)}>Cancel</Button></div></form> : <button className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-semibold text-blue-300" onClick={() => setEditing(true)}><Pencil size={12} />Edit annotation</button>}

          <div className="mt-4">
            <DetailSection title="Asset information" icon={<Boxes size={13} />}><div className="grid grid-cols-2 gap-x-3 gap-y-3 text-xs"><div className="col-span-2"><div className="text-slate-500">Name / ID</div><div className="mt-1 font-semibold">{selectedDetails?.asset?.name ?? selected.label} · {selectedDetails?.asset?.id ?? `OBJ-${selected.id}`}</div></div><div><div className="text-slate-500">Condition</div><div className="mt-1 font-medium">{selectedDetails?.asset?.condition ?? "Unverified"}</div></div><div><div className="text-slate-500">Status</div><div className="mt-1 font-medium capitalize">{selectedDetails?.asset?.operational_status ?? "Unknown"}</div></div><div className="col-span-2"><div className="text-slate-500">Declared insured value</div><div className="mt-1 text-base font-semibold">{selectedDetails?.asset?.declared_insured_value_cents ? currency(selectedDetails.asset.declared_insured_value_cents) : "Not linked"}</div></div></div></DetailSection>
            <DetailSection title="Inspection & maintenance" icon={<Wrench size={13} />}><div className="grid grid-cols-2 gap-3 text-xs"><div><div className="text-slate-500">Last inspection</div><div className="mt-1 font-medium">{selectedDetails?.inspection?.last_inspection_date ?? "Not recorded"}</div></div><div><div className="text-slate-500">Next due</div><div className="mt-1 font-medium">{selectedDetails?.inspection?.next_due_date ?? "Not recorded"}</div></div></div>{selectedDetails?.inspection?.issues.map((issue) => <div key={issue} className="mt-3 rounded border border-amber-400/20 bg-amber-400/[.07] p-2 text-[11px] leading-4 text-amber-200">{issue}</div>)}</DetailSection>
            <DetailSection title="Photos, videos & documents" icon={<ImageIcon size={13} />}><div className="grid grid-cols-2 gap-2">{selectedDetails?.media?.map((item) => <a href={item.url} target="_blank" key={item.url} className="group overflow-hidden rounded-md border border-white/[.08]"><img src={item.url} alt={item.title} className="h-20 w-full object-cover transition group-hover:scale-[1.03]" /><div className="p-2 text-[9px] leading-3 text-slate-500">Illustrative · {item.source}</div></a>)}</div><div className="mt-3 space-y-2">{selectedDetails?.documents?.map((document) => <div key={document.title} className="flex items-center gap-2 text-[11px]"><FileSearch size={12} className="text-blue-300" /><span className="flex-1">{document.title}</span><span className="text-slate-600">{document.type}</span></div>)}</div><div className="mt-3 rounded-md bg-purple-400/[.06] p-3"><div className="text-[10px] font-bold uppercase tracking-wide text-purple-200">AI evidence summary</div><p className="mt-1 text-[11px] leading-4 text-slate-400">{selectedDetails?.evidence_summary ?? "No evidence summary saved."}</p></div></DetailSection>
            <DetailSection title="Incident & claim history" icon={<AlertTriangle size={13} />}>{selectedDetails?.incidents?.length ? <div className="space-y-2">{selectedDetails.incidents.map((incident) => <div key={incident.claim_id} className="rounded-md border border-rose-400/15 bg-rose-400/[.05] p-3"><div className="flex justify-between text-[11px] font-semibold"><span>{incident.claim_number}</span><span className="text-rose-300">{incident.status}</span></div><p className="mt-2 text-[10px] leading-4 text-slate-500">{incident.summary}</p></div>)}</div> : <p className="text-[11px] text-slate-500">No object-linked incident in the synthetic record.</p>}</DetailSection>
            <DetailSection title="AI insights" icon={<Sparkles size={13} />}><div className="space-y-2 text-[11px] leading-4">{selectedDetails?.ai_insights?.concerns.map((item) => <div className="flex gap-2" key={item}><AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-300" />{item}</div>)}<div className="rounded-md border border-white/[.08] p-2.5"><span className="text-slate-500">Recommended next action</span><div className="mt-1 font-semibold text-slate-200">{selectedDetails?.ai_insights?.recommended_next_action ?? "Human review"}</div></div></div></DetailSection>
            <DetailSection title="Inspection timeline" icon={<ClipboardCheck size={13} />}><MiniTimeline items={selectedDetails?.timelines?.inspection ?? []} empty="No inspection history" /></DetailSection>
            <DetailSection title="Incident timeline" icon={<AlertTriangle size={13} />}><MiniTimeline items={selectedDetails?.timelines?.incidents ?? []} empty="No linked incidents" /></DetailSection>
          </div>
          <div className="grid grid-cols-2 gap-2 border-t border-white/[.07] pt-4">{!selected.human_verified && <Button size="sm" onClick={verify}><Check size={13} />Verify</Button>}<Button size="sm" variant="secondary" onClick={requestInspection}><ShieldCheck size={13} />Request inspection</Button><Link href={`/properties/${plan.property_id}`} className="flex h-8 items-center justify-center gap-1 rounded-md border border-white/15 text-[11px] font-semibold text-slate-300 hover:bg-white/[.05]">View evidence</Link>{claim && <Link href={`/claims/${claim.id}`} className="flex h-8 items-center justify-center gap-1 rounded-md border border-white/15 text-[11px] font-semibold text-slate-300 hover:bg-white/[.05]">Open claim</Link>}</div>
        </div> : <div className="grid h-full min-h-[520px] place-items-center text-center"><div><div className="mx-auto grid size-12 place-items-center rounded-xl border border-white/[.08] bg-black/10 text-slate-500"><MousePointer2 size={20} /></div><h3 className="mt-4 text-sm font-semibold">Select an object or region</h3><p className="mx-auto mt-2 max-w-[240px] text-[11px] leading-5 text-slate-500">Click an overlay for asset, inspection, evidence, incident, and AI context. Draw a region to total the spatial candidates inside it.</p></div></div>}
      </aside>
    </div>
  </div>;
}
