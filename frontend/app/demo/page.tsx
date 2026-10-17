"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check, CircleDot, Play, ShieldCheck } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { WorkflowSankey } from "@/components/workflow-sankey";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";

type Phase = { phase:string; title:string; description:string; status:string; metric:string; href:string };
type Journey = { scenario:string; synthetic:boolean; prepared:boolean; phases:Phase[]; guardrails:string[] };

const tone = (status:string) => status === "complete" ? "teal" : status === "human_review" || status === "needs_evidence" ? "amber" : "blue";

export default function DemoPage() {
  const { data, loading, error, refresh } = useApi<Journey>("/demo/journey");
  const [preparing, setPreparing] = useState(false);
  const [message, setMessage] = useState("");
  async function prepare() {
    setPreparing(true); setMessage("");
    try { await api<Journey>("/demo/prepare", { method:"POST" }); setMessage("The persisted review trail is ready. No human decisions were created automatically."); await refresh(); }
    finally { setPreparing(false); }
  }
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "Journey unavailable"} />;
  const completed = data.phases.filter(x => x.status === "complete").length;
  return <>
    <PageHeader eyebrow="Guided lifecycle" title="One lifecycle, every handoff visible" description="Follow NorthStar from structured intake through underwriting, hazard monitoring, claim investigation, and an auditable human outcome. Each phase opens the connected working screen and persisted records." actions={<Button onClick={prepare} disabled={preparing}><Play size={15}/>{preparing ? "Preparing…" : "Prepare review trail"}</Button>} />
    {message && <div className="mb-5 rounded-lg border border-teal-300/20 bg-teal-300/[.08] px-4 py-3 text-sm text-teal-200">{message}</div>}
    <div className="mb-6 grid gap-4 md:grid-cols-[1fr_auto]">
      <Card className="surface-teal"><CardContent><div className="flex flex-wrap items-center justify-between gap-4"><div><div className="text-xs font-bold uppercase tracking-[.15em] text-slate-500">Scenario</div><div className="mt-2 text-xl font-semibold text-slate-100">{data.scenario}</div><p className="mt-2 text-sm text-slate-400">A persisted record set with connected evidence, workflow state, and audit history.</p></div><div className="min-w-40"><div className="text-3xl font-semibold text-slate-100">{completed}<span className="text-lg text-slate-500"> / 9</span></div><div className="mt-1 text-xs text-slate-400">phases currently complete</div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[.07]"><div className="h-full rounded-full bg-teal-400" style={{width:`${completed/9*100}%`}} /></div></div></div></CardContent></Card>
      <Card className="md:w-80"><CardContent><div className="flex items-center gap-2 text-sm font-semibold text-slate-100"><ShieldCheck size={17} className="text-amber-300"/>Operating guardrails</div><div className="mt-3 space-y-2">{data.guardrails.map(item => <div key={item} className="flex gap-2 text-xs leading-5 text-slate-400"><span className="mt-2 size-1 shrink-0 rounded-full bg-amber-300"/>{item}</div>)}</div></CardContent></Card>
    </div>
    <div className="relative grid gap-3 xl:grid-cols-3">
      {data.phases.map((phase, index) => <Link href={phase.href} key={phase.phase} className="group relative rounded-lg border border-white/[.09] bg-[linear-gradient(145deg,rgba(38,42,48,.96),rgba(31,34,38,.96))] p-5 transition duration-200 hover:-translate-y-0.5 hover:border-blue-300/30 hover:shadow-[0_16px_44px_rgba(0,0,0,.22)]">
        <div className="flex items-start gap-4"><div className={`grid size-10 shrink-0 place-items-center rounded-full border text-sm font-bold ${phase.status === "complete" ? "border-teal-300/30 bg-teal-300/10 text-teal-200" : "border-blue-300/25 bg-blue-300/10 text-blue-200"}`}>{phase.status === "complete" ? <Check size={17}/> : phase.phase}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="text-[10px] font-bold uppercase tracking-[.18em] text-slate-500">Phase {phase.phase}</span><StatusPill tone={tone(phase.status)}>{phase.status.replaceAll("_", " ")}</StatusPill></div><h2 className="mt-2 font-semibold text-slate-100">{phase.title}</h2><p className="mt-2 text-xs leading-5 text-slate-400">{phase.description}</p><div className="mt-4 flex items-center justify-between border-t border-white/[.07] pt-3"><span className="flex items-center gap-2 text-xs font-medium text-slate-300"><CircleDot size={13} className="text-blue-300"/>{phase.metric}</span><ArrowRight size={15} className="text-slate-500 transition group-hover:translate-x-1 group-hover:text-blue-300"/></div></div></div>
        {index < data.phases.length - 1 && <span className="pointer-events-none absolute -bottom-3 left-10 z-10 h-3 w-px bg-white/10 xl:hidden"/>}
      </Link>)}
    </div>
    <div id="workflow-explorer" className="mt-8 scroll-mt-24"><WorkflowSankey /></div>
  </>;
}
