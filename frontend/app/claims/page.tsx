"use client";

import Link from "next/link";
import { AlertCircle, ArrowRight, FilePlus2 } from "lucide-react";
import { CompanyLogo } from "@/components/company-logo";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Claim } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ClaimsPage() {
  const { data, loading, error } = useApi<{items:Claim[]}>("/claims");
  if (loading) return <LoadingState/>;
  if (error || !data) return <ErrorState message={error ?? "No data"}/>;
  return <>
    <PageHeader eyebrow="Claims desk" title="Evidence-led claim investigation" description="FNOL, policy context, chronology, exposure-specific investigation, estimate versions, and human review—without autonomous payment or denial." actions={<Link href="/claims/new" className="inline-flex items-center gap-2 rounded-full border border-teal-200/25 bg-teal-300 px-5 py-2.5 text-sm font-semibold text-[#10201b]"><FilePlus2 size={16}/>Create FNOL</Link>}/>
    <div className="space-y-4">{data.items.map(claim => <Card key={claim.id} className={claim.status === "waiting_evidence" ? "surface-amber" : "surface-teal"}><CardContent className="flex flex-wrap items-center gap-5">
      {claim.company_name?<CompanyLogo name={claim.company_name} className="size-11"/>:<div className="grid size-11 place-items-center rounded-2xl border border-white/[.08] bg-black/20 text-xs font-bold text-slate-200">{claim.peril.slice(0,2).toUpperCase()}</div>}
      <div className="min-w-[260px] flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-slate-100">{claim.claim_number}</h2><StatusPill tone={claim.status === "waiting_evidence" ? "amber" : "teal"}>{claim.status}</StatusPill>{claim.has_condition_pair&&<StatusPill tone="blue">Paired machine media</StatusPill>}</div><p className="mt-2 line-clamp-1 text-sm text-slate-400">{claim.narrative}</p><div className="mt-2 text-xs text-slate-500">{claim.company_name} · {claim.property_name} · loss {formatDate(claim.loss_at)}</div></div>
      {claim.contradiction_summary && <div className="flex max-w-xs gap-2 rounded-2xl border border-amber-300/15 bg-amber-300/[.06] p-3 text-xs text-amber-200"><AlertCircle size={15} className="shrink-0"/>{claim.contradiction_summary}</div>}
      <Link href={`/claims/${claim.id}`} className="inline-flex items-center gap-2 rounded-full border border-teal-200/15 bg-teal-300/[.06] px-4 py-2 text-sm font-semibold text-teal-200">Investigate <ArrowRight size={15}/></Link>
    </CardContent></Card>)}</div>
  </>;
}
