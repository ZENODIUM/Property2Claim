"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Bot, GitBranch, ScanSearch, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Card, CardContent } from "@/components/ui/card";
import { ExecutiveVisuals, type OverviewHazard, type OverviewProperty, type WorkflowSnapshot } from "@/components/executive-visuals";
import { useApi } from "@/hooks/use-api";

type PriorityCase = { property_name: string; claim_id: number; claim_number: string; summary: string; queue: string; status: string; href: string };
type Overview = { properties: number; pending_human_tasks: number; active_hazard_reviews: number; priority_case: PriorityCase | null };

const steps = [
  { id: "intake", label: "Intake", icon: ScanSearch, detail: "Forms, schedules of values, documents, media, and original 2D plans enter as versioned source evidence." },
  { id: "ai", label: "AI Analysis", icon: Bot, detail: "Gemini reads authorized images and plans. Groq can summarize supplied text. Findings stay source-linked proposals." },
  { id: "routing", label: "Routing", icon: SlidersHorizontal, detail: "Deterministic rules and Jev select a work queue. LangGraph keeps the case state and its branches." },
  { id: "review", label: "Review", icon: ShieldCheck, detail: "A person checks the evidence. Models cannot bind coverage, deny a claim, or authorize payment." },
  { id: "result", label: "Result", icon: GitBranch, detail: "The authorized outcome, estimate versions, and every transition stay searchable in the audit." },
] as const;

export default function OverviewPage() {
  const { data, loading, error } = useApi<Overview>("/overview");
  const properties = useApi<{items:OverviewProperty[]}>("/properties");
  const hazards = useApi<{items:OverviewHazard[]}>("/hazards");
  const workflows = useApi<WorkflowSnapshot>("/workflows/results");
  const [active, setActive] = useState<(typeof steps)[number]["id"]>("routing");
  if (loading || properties.loading || hazards.loading || workflows.loading) return <LoadingState />;
  if (error || properties.error || hazards.error || workflows.error || !data || !properties.data || !hazards.data || !workflows.data) return <ErrorState message={error ?? properties.error ?? hazards.error ?? workflows.error ?? "No data"} />;
  const selected = steps.find((step) => step.id === active) ?? steps[2];
  const metrics = [
    { label: "Insured sites", value: data.properties, note: "Active portfolio" },
    { label: "Open reviews", value: data.pending_human_tasks, note: "Waiting on a person" },
    { label: "Hazard alerts", value: data.active_hazard_reviews, note: "Exposure review, not loss" },
  ];
  return <>
    <PageHeader eyebrow="Property2Claim / overview" title="Property intelligence. Evidence-driven insurance." description="From commercial property onboarding to human-reviewed claims." actions={<Link href="/demo" className="rounded-full border border-teal-200/25 bg-teal-300 px-5 py-2.5 text-sm font-semibold text-[#10201b] shadow-[0_10px_30px_rgba(69,208,157,.12)] hover:bg-teal-200">Explore lifecycle</Link>} />
    <div className="grid gap-4 md:grid-cols-3">
      {metrics.map((metric, index) => <Card key={metric.label} className={["surface-teal","surface-violet","surface-amber"][index]}><CardContent className="py-5"><div className="text-[10px] font-bold uppercase tracking-[.14em] text-slate-500">{metric.label}</div><div className="mt-3 text-5xl font-medium tracking-[-.04em] text-slate-100">{metric.value}</div><div className="mt-2 text-xs text-slate-500">{metric.note}</div></CardContent></Card>)}
    </div>
    <ExecutiveVisuals properties={properties.data.items} hazards={hazards.data.items} workflow={workflows.data}/>
    <Card className="mt-6">
      <CardContent>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[.15em] text-blue-300">Insurance workflow</div>
            <h2 className="mt-1 text-lg font-semibold text-slate-100">Simplified overview</h2>
          </div>
          <Link href="/demo#workflow-explorer" className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-300 hover:text-blue-200">Open the detailed Workflow Explorer <ArrowRight size={14} /></Link>
        </div>
        <div className="mt-6 grid gap-2 sm:grid-cols-5">
          {steps.map((step, index) => {
            const Icon = step.icon;
            const on = step.id === active;
            return <button key={step.id} type="button" onMouseEnter={() => setActive(step.id)} onFocus={() => setActive(step.id)} onClick={() => setActive(step.id)} className={`relative rounded-lg border px-3 py-4 text-left transition ${on ? "border-blue-300/40 bg-blue-400/[.08]" : "border-white/[.08] hover:border-white/20"}`}>
              <Icon size={16} className={on ? "text-blue-300" : "text-slate-500"} />
              <div className="mt-3 text-sm font-semibold text-slate-100">{step.label}</div>
              {index < steps.length - 1 && <span className="absolute -right-2 top-1/2 hidden size-2 -translate-y-1/2 rotate-45 border-r border-t border-white/20 sm:block" />}
            </button>;
          })}
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-400">{selected.detail}</p>
        <p className="mt-2 text-xs text-slate-500">The detailed explorer shows all nine lifecycle phases, the AI and Jev branches, and the approval gates.</p>
      </CardContent>
    </Card>
    {data.priority_case && <Link href={data.priority_case.href} className="mt-6 block">
      <Card className="border-amber-300/20 transition hover:border-amber-300/40">
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[.14em] text-amber-200">Active priority — {data.priority_case.property_name}</div>
            <h2 className="mt-2 text-xl font-semibold text-slate-100">{data.priority_case.summary}</h2>
            <p className="mt-1 text-xs text-slate-500">{data.priority_case.claim_number} · {data.priority_case.status.replaceAll("_", " ")}</p>
          </div>
          <StatusPill tone="amber">{data.priority_case.queue}</StatusPill>
        </CardContent>
      </Card>
    </Link>}
  </>;
}
