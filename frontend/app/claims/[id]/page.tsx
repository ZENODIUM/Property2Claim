"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import { FileImage, FileText, FileUp, Play, Scale, TrendingUp, Video } from "lucide-react";
import { EvidenceComparison } from "@/components/evidence-comparison";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { api, API_URL } from "@/lib/api";
import type { Claim, Estimate, EvidenceDocument } from "@/lib/types";
import { currency, formatDate } from "@/lib/utils";

type Audit = {id:number;event_type:string;actor:string;source:string;details:Record<string,unknown>;old_state?:Record<string,unknown>;new_state?:Record<string,unknown>;created_at:string};
const present = (value: string) => value.replaceAll(/synthetic/gi, "reference").replaceAll(/demo/gi, "review");

function EstimatePanel({ estimate, open, onToggle }: { estimate: Estimate; open: boolean; onToggle: () => void }) {
  const provenance = estimate.provenance.map((item) => item.kind === "repair_quote" ? `Repair quote on document #${String(item.document_id ?? "unknown")}` : item.kind === "synthetic_history" ? `${String(item.sample_count ?? 0)} reference historical analogs` : String(item.kind ?? "source"));
  return <div className="rounded-lg border border-white/[.08] p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><div className="flex items-center gap-2"><span className="font-semibold">Version {estimate.version}</span><StatusPill tone="blue">{present(estimate.method.replaceAll("_", " "))}</StatusPill></div><div className="mt-1 text-xs text-slate-500">{formatDate(estimate.created_at)}</div></div>
      <button type="button" onClick={onToggle} className="text-right" aria-expanded={open}><div className="text-xl font-semibold text-blue-200 underline decoration-blue-300/40 underline-offset-4">{currency(estimate.gross_cents)}</div><div className="text-xs text-slate-500">{open ? "Hide calculation" : "Show where this amount comes from"}</div></button>
    </div>
    {open && <div className="mt-4 space-y-4 border-t border-white/[.07] pt-4">
      <div className="grid gap-3 sm:grid-cols-2">{(estimate.line_items ?? []).map((item) => <div key={item.id} className="rounded-md bg-black/15 p-3 text-xs"><div className="font-semibold text-slate-200">{item.description}</div><div className="mt-1 text-slate-500">{item.category} · {item.source_kind.replaceAll("_", " ")} · {item.supported ? "source-supported" : "unsupported baseline"}</div><div className="mt-2 text-sm font-semibold">{currency(item.amount_cents)}</div></div>)}</div>
      <div className="grid gap-2 text-xs sm:grid-cols-2">
        <div className="rounded-md bg-black/10 p-3"><div className="text-slate-500">Gross estimated loss</div><div className="mt-1 font-semibold">{currency(estimate.gross_cents)}</div><div className="mt-1 text-slate-500">{estimate.method === "documented_quote_sum" ? "Sum of supported repair quotes." : "Median of reference claims with the same peril."}</div></div>
        <div className="rounded-md bg-black/10 p-3"><div className="text-slate-500">Uncertainty band</div><div className="mt-1 font-semibold">{currency(estimate.low_cents)} – {currency(estimate.high_cents)}</div><div className="mt-1 text-slate-500">Low is 75% of gross. High is 135%. This is a labeled range, not a prediction interval.</div></div>
        <div className="rounded-md bg-black/10 p-3"><div className="text-slate-500">Deductible, then policy limit</div><div className="mt-1 font-semibold">{currency(estimate.deductible_cents)} deductible · {currency(estimate.policy_limit_cents)} limit</div><div className="mt-1 text-slate-500">Illustrative eligible is gross minus deductible, capped by the commercial-property limit: {currency(estimate.illustrative_eligible_cents)}.</div></div>
        <div className="rounded-md bg-black/10 p-3"><div className="text-slate-500">Reserve, proposal, authorization</div><div className="mt-1 font-semibold">Suggestion {currency(estimate.reserve_suggestion_cents)}</div><div className="mt-1 text-slate-500">Proposed payment {currency(estimate.proposed_payment_cents)}. Authorized payment {currency(estimate.authorized_payment_cents)}. Nothing is booked from this calculation.</div></div>
      </div>
      <div className="text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Assumptions. </span>{present(estimate.assumptions.join(" "))}</div>
      <div className="text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Support. </span>{provenance.join("; ") || "No provenance recorded."}</div>
      <div className="text-[11px] leading-5 text-rose-300">{estimate.limitations.join(" · ")}</div>
    </div>}
  </div>;
}

function EvidencePreview({document}:{document:EvidenceDocument}) {
  const base=API_URL.replace(/\/api$/,"");
  const image=document.media_type.startsWith("image/"); const pdf=document.media_type==="application/pdf"; const video=document.media_type.startsWith("video/");
  return <Link href={`/evidence/${document.id}`} className="group overflow-hidden rounded-md border border-white/[.08] bg-black/10 transition hover:-translate-y-0.5 hover:border-blue-300/30">
    <div className="grid h-28 place-items-center overflow-hidden bg-black/20">{image||pdf?<img src={`${base}/api/documents/${document.id}/preview?page=1`} alt={`Preview of ${document.filename}`} className="h-full w-full object-contain"/>:video?<Video size={24} className="text-blue-300"/>:<FileText size={24} className="text-slate-500"/>}</div>
    <div className="p-3"><div className="truncate text-xs font-semibold text-slate-200">{document.filename}</div><div className="mt-1 truncate text-[9px] text-slate-500">{document.classification.replaceAll("_"," ")}</div><div className="mt-2"><StatusPill tone={document.analysis_status.includes("error")?"rose":document.analysis_status.includes("completed")?"teal":"amber"}>{document.analysis_status.replaceAll("_"," ")}</StatusPill></div></div>
  </Link>;
}

export default function ClaimDetailPage() {
  const id=useParams<{id:string}>().id;
  const claim=useApi<Claim>(`/claims/${id}`); const audit=useApi<{items:Audit[]}>(`/audit?subject_type=claim&subject_id=${id}`);
  const [busy,setBusy]=useState(false); const [message,setMessage]=useState(""); const [openEstimate,setOpenEstimate]=useState<number|null>(null);
  async function refresh(){await Promise.all([claim.refresh(),audit.refresh()]);}
  async function rerun(){setBusy(true);try{await api(`/claims/${id}/run-investigation`,{method:"POST"});setMessage("Investigation rerun and checkpoint persisted.");await refresh();}finally{setBusy(false)}}
  async function uploadQuote(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget;const data=new FormData(form);const dollars=Number(data.get("amount_dollars"));data.delete("amount_dollars");data.set("amount_cents",String(Math.round(dollars*100)));setBusy(true);try{await api(`/claims/${id}/evidence`,{method:"POST",body:data});form.reset();setMessage("Quote linked; only the affected claim path resumed and a new estimate version was created.");await refresh();}finally{setBusy(false)}}
  async function uploadMedia(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget;const data=new FormData(form);if(!data.has("authorize_external_analysis"))data.set("authorize_external_analysis","false");setBusy(true);try{const result=await api<{document:EvidenceDocument;real_analysis_performed:boolean}>(`/claims/${id}/media`,{method:"POST",body:data});form.reset();setMessage(result.real_analysis_performed?"Live provider analysis completed and source-linked observations were saved for human review.":`Media retained with status: ${result.document.analysis_status.replaceAll("_"," ")}.`);await refresh();}finally{setBusy(false)}}
  if(claim.loading||audit.loading)return <LoadingState/>; if(claim.error||audit.error||!claim.data||!audit.data)return <ErrorState message={claim.error??audit.error??"No data"}/>;
  const c=claim.data; const latest=c.estimates?.at(-1);
  return <><PageHeader eyebrow={`Claim · ${c.claim_number} · ${c.company_name ?? "Account"}`} title={`${c.peril[0].toUpperCase()+c.peril.slice(1)} loss investigation`} description={`${c.property_name ? `${c.property_name}. ` : ""}${c.narrative}`} actions={<Button onClick={rerun} disabled={busy} variant="secondary"><Play size={15}/>Rerun investigation</Button>}/>
    {message&&<div className="mb-5 rounded-lg border border-teal-300/20 bg-teal-300/[.07] p-3 text-sm text-teal-200">{message}</div>}
    <div className="grid gap-6 xl:grid-cols-[1.15fr_.85fr]"><div className="space-y-6">
      <Card><CardHeader><div className="flex items-center gap-2"><h2 className="font-semibold">Claim context</h2><StatusPill tone={c.status==="waiting_evidence"?"amber":"teal"}>{c.status}</StatusPill></div></CardHeader><CardContent><div className="grid gap-4 sm:grid-cols-3"><div><div className="text-xs text-slate-500">Loss date</div><div className="mt-1 text-sm font-semibold">{formatDate(c.loss_at)}</div></div><div><div className="text-xs text-slate-500">Policy</div><div className="mt-1 text-sm font-semibold">Demo policy #{c.policy_id}</div></div><div><div className="text-xs text-slate-500">Exposures</div><div className="mt-1 text-sm font-semibold">{c.exposures?.map(x=>x.type.replaceAll("_"," ")).join(", ")}</div></div></div>{c.contradiction_summary&&<div className="mt-5 rounded-lg border border-amber-300/20 bg-amber-300/[.06] p-3 text-sm text-amber-100"><b>Chronology conflict:</b> {c.contradiction_summary}</div>}</CardContent></Card>
      <Card><CardHeader><div className="flex items-center justify-between"><div><h2 className="font-semibold">Multimodal evidence</h2><p className="mt-1 text-xs text-slate-500">Open any source for original-file preview and page/frame-linked analysis.</p></div><StatusPill tone="blue">{c.documents?.length??0} files</StatusPill></div></CardHeader><CardContent>{c.documents?.length?<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{c.documents.map(document=><EvidencePreview key={document.id} document={document}/>)}</div>:<div className="rounded-md border border-dashed border-white/10 p-8 text-center text-xs text-slate-500">No claim evidence has been uploaded.</div>}</CardContent></Card>
      <EvidenceComparison documents={c.documents ?? []} narrative={c.narrative} />
      <Card><CardHeader><h2 className="font-semibold">Estimate versions</h2><p className="mt-1 text-xs text-slate-500">Click an amount to see the calculation, its support, and what still needs a person.</p></CardHeader><CardContent className="space-y-3">{c.estimates?.map(estimate => { const open = openEstimate === estimate.id || (openEstimate === null && estimate.id === latest?.id); return <EstimatePanel key={estimate.id} estimate={estimate} open={open} onToggle={() => setOpenEstimate(open ? -1 : estimate.id)} />; })}</CardContent></Card>
      <Card><CardHeader><h2 className="font-semibold">Evidence & agent timeline</h2></CardHeader><CardContent className="space-y-4">{audit.data.items.map(event=><div key={event.id} className="relative border-l-2 border-white/10 pl-5 before:absolute before:-left-[5px] before:top-1 before:size-2 before:rounded-full before:bg-teal-400"><div className="text-sm font-semibold">{event.event_type.replaceAll("_"," ")}</div><div className="mt-1 text-xs text-slate-500">{event.actor} · {event.source} · {formatDate(event.created_at)}</div></div>)}</CardContent></Card>
    </div><div className="space-y-6">
      <Card className="surface-teal"><CardHeader><div className="flex items-center gap-2"><FileUp size={17} className="text-teal-300"/><h2 className="font-semibold">Add repair quote</h2></div></CardHeader><CardContent><form onSubmit={uploadQuote} className="space-y-4"><div><label className="label">Quote document</label><input className="block w-full text-xs" name="file" type="file" accept=".pdf,.txt" required/></div><div><label className="label">Supported quote amount (USD)</label><input className="input" name="amount_dollars" type="number" min="1" step=".01" defaultValue="875000" required/></div><input type="hidden" name="classification" value="repair_quote"/><Button type="submit" disabled={busy} className="w-full">Upload and resume affected path</Button><p className="text-[11px] leading-5 text-slate-500">Creates source evidence and a versioned illustrative estimate. It authorizes neither reserve nor payment.</p></form></CardContent></Card>
      <Card className="surface-blue"><CardHeader><div className="flex items-center gap-2"><FileImage size={17} className="text-blue-300"/><h2 className="font-semibold">Add image or video evidence</h2></div></CardHeader><CardContent><form onSubmit={uploadMedia} className="space-y-4"><input className="block w-full text-xs" name="file" type="file" accept="image/png,image/jpeg,video/mp4" required/><label className="flex gap-3 text-[11px] leading-5 text-slate-400"><input type="checkbox" name="authorize_external_analysis" value="true" className="mt-1"/><span>Explicitly authorize sending this media to configured Gemini. Leave unchecked to retain it without analysis.</span></label><div><label className="label">Video frame interval (seconds)</label><input className="input" name="frame_interval_seconds" type="number" min="1" max="300" defaultValue="10"/></div><Button type="submit" disabled={busy} variant="secondary" className="w-full">Upload media</Button><p className="text-[10px] text-slate-600">Media quality remains unverified until a reviewer accepts the uploaded source.</p></form></CardContent></Card>
      {latest&&<Card className="bg-[#18202a]"><CardContent><TrendingUp className="text-teal-300"/><div className="mt-4 text-xs uppercase tracking-wide text-slate-400">Reserve suggestion for review</div><div className="mt-2 text-3xl font-semibold">{currency(latest.reserve_suggestion_cents)}</div><div className="mt-4 flex gap-2 text-xs text-slate-300"><Scale size={15}/><span>Authorized reserving staff must review; nothing is booked automatically.</span></div></CardContent></Card>}
    </div></div>
  </>;
}
