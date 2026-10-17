"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, CircleDot, Database, Play, Route, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { currency } from "@/lib/utils";

type Submission = { id:number; company_id:number; property_id:number; status:string; completeness:number; missing_items:string[]; exceptions:Array<{type:string;source:string;requires_human_review:boolean}>; route:string; decision_source:string; premium_scenario_cents:number; disclaimer:string };
type WorkflowTrace = { id:number; status:string; steps:string[]; route?:string; missing_items:string[]; provider?:string; decision_source?:string; created_at:string };
type ExplainTab = "process" | "checks" | "sources";

const processStages = [
  ["01", "Collect", "Account, site, SOV, policy, inspections and loss history are linked to one case."],
  ["02", "Parse", "Structured fields and page-linked document facts are normalized with provenance."],
  ["03", "Validate", "Required fields, types, dates, identifiers and source consistency are checked."],
  ["04", "COPE", "Construction, occupancy, protection and external exposure signals are evaluated."],
  ["05", "Reconcile", "Conflicting values, stale certificates and missing evidence become explicit exceptions."],
  ["06", "AI assist", "Source-bound summaries can organize supplied evidence; they do not make the decision."],
  ["07", "Jev route", "A typed bounded judgment selects needs-evidence, specialist or underwriter review."],
  ["08", "Scenario", "Transparent rules calculate a non-binding premium scenario and record assumptions."],
  ["09", "Human gate", "An authorized underwriter reviews evidence and records the final workflow action."],
] as const;

const checks = [
  ["Identity & schedule", "Company/property IDs, site code uniqueness, occupancy and declared values", "SOV + account record"],
  ["Construction", "Frame, wall, roof age/material and renovation evidence", "Inspection + COPE record"],
  ["Fire protection", "Sprinkler coverage, certificate dates, fire pump and alarm evidence", "Certificates + inspection"],
  ["Occupancy hazards", "Operations, process heat, combustible load, storage and critical equipment", "SOV + site evidence"],
  ["Natural hazards", "Flood, wildfire, wind and active NASA/NOAA proximity signals", "Geographic adapters"],
  ["Loss history", "Prior incidents, chronology, open maintenance and repeated causes", "Claims + maintenance"],
  ["Financial consistency", "Building, equipment, stock, BI and total-insured-value arithmetic", "Declared schedules"],
  ["Authority boundary", "Missing coverage questions, recommendation-only state and required reviewer role", "Rules + role policy"],
] as const;

export default function UnderwritingPage() {
  const { data, loading, error, refresh } = useApi<{items:Submission[]}>("/underwriting");
  const [running, setRunning] = useState<number>();
  const [notice, setNotice] = useState("");
  const [runError, setRunError] = useState("");
  const [trace, setTrace] = useState<Record<number, WorkflowTrace>>({});
  const [explainTab, setExplainTab] = useState<ExplainTab>("process");

  async function run(id:number) {
    setRunning(id); setNotice(""); setRunError("");
    try {
      const outcome = await api<Submission>(`/underwriting/${id}/run`, { method:"POST" });
      const detail = await api<{workflow?:WorkflowTrace}>(`/underwriting/${id}`);
      if (detail.workflow) setTrace((current) => ({...current, [id]: detail.workflow!}));
      const missing = outcome.missing_items.length ? outcome.missing_items.join(", ") : "none";
      setNotice(`Workflow finished at ${new Date().toLocaleTimeString()}. Submission #${outcome.id} is ${outcome.status.replaceAll("_", " ")}, routed to ${outcome.route || "pending"} by ${outcome.decision_source || "rules"}. Missing evidence: ${missing}. This is a recommendation, not an approval.`);
      await refresh();
    } catch (reason) { setRunError(reason instanceof Error ? reason.message : "The workflow request failed."); }
    finally { setRunning(undefined); }
  }

  if (loading) return <LoadingState/>;
  if (error || !data) return <ErrorState message={error ?? "No data"}/>;
  return <>
    <PageHeader eyebrow="Underwriting workbench" title="Evidence before judgment" description="Completeness and reconciliation precede bounded Jev routing. Every proposed term awaits an authorized underwriter." />
    <Card className="mb-5 overflow-hidden"><CardHeader><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-base font-semibold text-slate-100">Underwriting decision system</h2><p className="mt-1 max-w-3xl text-xs leading-5 text-slate-400">Nine persisted stages combine deterministic validation, COPE checks, external hazard context, optional source-bound AI, typed Jev routing, transparent calculations, and a mandatory human authority gate.</p></div><Link href="/demo#workflow-explorer" className="rounded-full border border-white/[.09] px-3 py-2 text-xs font-semibold text-teal-200">Open architecture</Link></div><div className="mt-4 flex gap-1 overflow-x-auto border-t border-white/[.07] pt-3">{[["process","Granular process"],["checks","Rules & comparisons"],["sources","Policy & supporting data"]].map(([id,label])=><button key={id} onClick={()=>setExplainTab(id as ExplainTab)} className={`shrink-0 rounded-full px-3 py-2 text-xs font-semibold ${explainTab===id?"bg-teal-300/[.1] text-teal-100":"text-slate-500 hover:text-slate-200"}`}>{label}</button>)}</div></CardHeader><CardContent className="max-h-[430px] overflow-y-auto">
      {explainTab==="process"&&<div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{processStages.map(([number,title,detail])=><div key={number} className="rounded-2xl border border-white/[.08] bg-black/10 p-3"><div className="flex items-center gap-3"><span className="grid size-7 place-items-center rounded-full bg-teal-300/[.09] text-[10px] font-bold text-teal-200">{number}</span><div className="text-xs font-semibold text-slate-100">{title}</div></div><p className="mt-2 text-[11px] leading-5 text-slate-400">{detail}</p></div>)}</div>}
      {explainTab==="checks"&&<div className="table-shell"><table className="data-table"><thead><tr><th>Control family</th><th>What is compared</th><th>Primary support</th></tr></thead><tbody>{checks.map(([name,comparison,source])=><tr key={name}><td className="font-semibold text-slate-200">{name}</td><td className="text-xs text-slate-400">{comparison}</td><td className="text-xs text-teal-200">{source}</td></tr>)}</tbody></table></div>}
      {explainTab==="sources"&&<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[[Database,"Account & SOV","Declared values, locations, occupancy, construction and operations."],[ShieldCheck,"Policy context","Limits, deductibles and authority boundaries; no autonomous coverage conclusion."],[Bot,"Evidence layer","Inspection reports, certificates, floor plans, images and linked extracted facts."],[SlidersHorizontal,"External signals","NASA/NOAA event proximity and baseline hazards as exposure context, not confirmed damage."],[Route,"Decision controls","Required fields, conflict rules, completeness thresholds and permitted route labels."],[ShieldCheck,"Human authority","Role gates determine who may request evidence or record a reviewed outcome."]].map(([Icon,title,detail])=>{const SourceIcon=Icon as typeof Database;return <div key={String(title)} className="rounded-2xl border border-white/[.08] bg-black/10 p-4"><SourceIcon size={16} className="text-teal-300"/><div className="mt-3 text-xs font-semibold text-slate-100">{String(title)}</div><p className="mt-2 text-[11px] leading-5 text-slate-400">{String(detail)}</p></div>})}</div>}
    </CardContent></Card>
    {notice && <div className="mb-5 rounded-lg border border-teal-300/25 bg-teal-300/[.08] px-4 py-3 text-sm leading-6 text-teal-100">{notice} <Link href="/tasks" className="font-semibold text-teal-200 underline underline-offset-2">Open the review task</Link></div>}
    {runError && <div className="mb-5 rounded-lg border border-rose-300/25 bg-rose-300/[.08] px-4 py-3 text-sm text-rose-100">{runError}</div>}
    <div className="space-y-5">{data.items.map((item) => <Card key={item.id}>
      <CardHeader className="flex flex-row items-center gap-4"><div className="grid size-11 place-items-center rounded-xl bg-slate-900 text-white">{item.completeness}</div><div className="flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">Submission #{item.id} · Property #{item.property_id}</h2><StatusPill tone={item.status === "needs_info" ? "amber" : "teal"}>{item.status}</StatusPill><StatusPill tone="blue">{item.decision_source || "not run"}</StatusPill></div><div className="mt-1 text-xs text-slate-500">Completeness {item.completeness}% · route {item.route || "pending"}</div></div><Button onClick={() => run(item.id)} disabled={running === item.id} size="sm"><Play size={14}/>{running === item.id ? "Running…" : "Run workflow"}</Button></CardHeader>
      <CardContent><div className="grid gap-5 lg:grid-cols-3"><div><div className="text-xs font-bold uppercase tracking-wide text-slate-500">Missing evidence</div><div className="mt-3 space-y-2">{item.missing_items.length ? item.missing_items.map((missing) => <div key={missing} className="flex gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-900"><AlertTriangle size={15} className="shrink-0"/>{missing}</div>) : <div className="flex gap-2 text-xs text-teal-700"><CheckCircle2 size={15}/>No deterministic gaps</div>}</div></div><div><div className="text-xs font-bold uppercase tracking-wide text-slate-500">Source-backed exceptions</div><div className="mt-3 space-y-2">{item.exceptions.map((exception,index) => <div key={index} className="rounded-lg border border-slate-100 p-3"><div className="text-xs font-semibold">{exception.type.replaceAll("_", " ")}</div><div className="mt-1 text-[11px] text-slate-500">Source: {exception.source}</div></div>)}</div></div><div className="rounded-xl bg-slate-50 p-4"><div className="text-xs font-bold uppercase tracking-wide text-slate-500">Illustrative premium scenario</div><div className="mt-3 text-2xl font-semibold">{currency(item.premium_scenario_cents)}</div><p className="mt-2 text-xs leading-5 text-slate-500">{item.disclaimer}</p></div></div>
      {trace[item.id] && <div className="mt-6 rounded-xl border border-teal-300/15 bg-teal-300/[.035] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2 text-sm font-semibold text-slate-100"><Route size={15} className="text-teal-300"/>Latest workflow route</div><span className="text-[10px] text-slate-500">{trace[item.id].provider ?? "rules"} · {new Date(trace[item.id].created_at).toLocaleTimeString()}</span></div><div className="mt-4 flex flex-wrap items-center gap-2">{trace[item.id].steps.map((step, index) => <div key={step} className="flex items-center gap-2"><span className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[.035] px-2.5 py-1.5 text-[11px] text-slate-300"><CircleDot size={12} className={step === "jev_route" ? "text-teal-300" : "text-blue-300"}/>{step.replaceAll("_", " ")}</span>{index < trace[item.id].steps.length - 1 && <span className="text-slate-600">→</span>}</div>)}</div><p className="mt-3 text-xs text-slate-400">Route: <span className="font-semibold text-teal-200">{trace[item.id].route ?? item.route}</span>{trace[item.id].missing_items.length ? ` · Evidence requested: ${trace[item.id].missing_items.join(", ")}` : " · Evidence completeness checks passed"}. Awaiting the appropriate human review action.</p></div>}
      </CardContent>
    </Card>)}</div>
  </>;
}
