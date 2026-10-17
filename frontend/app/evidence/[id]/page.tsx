"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, Download, ExternalLink, FileText, Image as ImageIcon, Play, RefreshCw, Video } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { api, API_URL } from "@/lib/api";
import { formatDate } from "@/lib/utils";

type FactValue = { confidence_label?:string; description?:string; text?:string; [key:string]:unknown };
type Fact = { id:number; fact_type:string; value:FactValue; page_number?:number; timestamp_seconds?:number; evidence_location:string; verified:boolean };
type Evidence = { id:number; claim_id?:number; property_id?:number; filename:string; media_type:string; classification:string; size_bytes:number; source_mode:string; analysis_status:string; created_at:string; page_count?:number; content_url:string; preview_url:string; facts:Fact[] };

function observationText(fact:Fact) { return String(fact.value.description ?? fact.value.text ?? JSON.stringify(fact.value)); }

export default function EvidenceDetailPage() {
  const id=useParams<{id:string}>().id;
  const evidence=useApi<Evidence>(`/documents/${id}`);
  const [page,setPage]=useState(1); const [selectedFact,setSelectedFact]=useState<number>(); const [authorized,setAuthorized]=useState(false); const [busy,setBusy]=useState(false); const [message,setMessage]=useState("");
  const base=API_URL.replace(/\/api$/,"");
  const current=evidence.data;
  const facts=useMemo(()=>current?.facts.filter(f=>!f.fact_type.endsWith("superseded"))??[],[current]);
  async function reprocess(){setBusy(true);setMessage("");try{const form=new FormData();form.set("authorize_external_analysis",String(authorized));await api(`/documents/${id}/reprocess`,{method:"POST",body:form});setMessage("Only media vision and the evidence index were reprocessed. The claim graph was not rerun.");await evidence.refresh();}finally{setBusy(false)}}
  if(evidence.loading)return <LoadingState/>; if(evidence.error||!current)return <ErrorState message={evidence.error??"Evidence unavailable"}/>;
  const content=`${base}${current.content_url}`; const preview=`${base}${current.preview_url}?page=${page}`;
  const selected=facts.find(f=>f.id===selectedFact);
  return <><PageHeader eyebrow="Evidence viewer" title={current.filename} description="Original evidence and structured analysis remain side by side. Every observation is unverified until a qualified reviewer confirms it." actions={<><Link href={current.claim_id?`/claims/${current.claim_id}`:"/audit"} className="inline-flex h-9 items-center gap-2 rounded-md border border-white/15 px-3 text-xs font-semibold text-slate-200"><ArrowLeft size={14}/>Back to case</Link><a href={content} target="_blank" className="inline-flex h-9 items-center gap-2 rounded-md bg-blue-500 px-3 text-xs font-semibold text-white">Original file <Download size={14}/></a></>}/>
    <div className="mb-5 flex flex-wrap items-center gap-2"><StatusPill tone="blue">{current.classification.replaceAll("_"," ")}</StatusPill><StatusPill tone={current.analysis_status.includes("error")?"rose":current.analysis_status.includes("completed")?"teal":"amber"}>{current.analysis_status.replaceAll("_"," ")}</StatusPill><span className="text-xs text-slate-500">{current.media_type} · {(current.size_bytes/1024).toFixed(1)} KB · {formatDate(current.created_at)}</span></div>
    {message&&<div className="mb-5 rounded-md border border-teal-300/20 bg-teal-300/[.07] p-3 text-xs text-teal-200">{message}</div>}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,.65fr)]">
      <Card className="overflow-hidden"><CardHeader className="flex flex-row items-center justify-between"><div><h2 className="text-sm font-semibold">Original evidence</h2><p className="mt-1 text-[11px] text-slate-500">Source retained unchanged; stock site imagery is never shown here as incident proof.</p></div>{current.page_count&&<div className="flex items-center gap-2"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)} className="rounded border border-white/10 px-2 py-1 text-xs disabled:opacity-30">Previous</button><span className="text-xs text-slate-400">Page {page}/{current.page_count}</span><button disabled={page>=current.page_count} onClick={()=>setPage(p=>p+1)} className="rounded border border-white/10 px-2 py-1 text-xs disabled:opacity-30">Next</button></div>}</CardHeader><CardContent className="grid min-h-[630px] place-items-center bg-black/20 p-3">
        {current.media_type==="application/pdf"?<img key={page} src={preview} alt={`Page ${page} of ${current.filename}`} className="max-h-[820px] w-full object-contain"/>:current.media_type.startsWith("image/")?<img src={preview} alt={current.filename} className="max-h-[820px] w-full object-contain"/>:current.media_type.startsWith("video/")?<video src={content} controls className="max-h-[760px] w-full bg-black"/>:<div className="text-center"><FileText size={38} className="mx-auto text-slate-600"/><p className="mt-3 text-sm text-slate-300">Preview is not available for this file type.</p><a href={content} className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-blue-300">Open original <ExternalLink size={13}/></a></div>}
      </CardContent></Card>
      <div className="space-y-5"><Card><CardHeader><div className="flex items-center justify-between"><div><h2 className="text-sm font-semibold">Structured analysis</h2><p className="mt-1 text-[11px] text-slate-500">{facts.length} active source-linked finding{facts.length===1?"":"s"}</p></div>{current.media_type.startsWith("image/")?<ImageIcon size={17} className="text-blue-300"/>:current.media_type.startsWith("video/")?<Video size={17} className="text-blue-300"/>:<FileText size={17} className="text-blue-300"/>}</div></CardHeader><CardContent className="max-h-[570px] space-y-2 overflow-y-auto">{facts.length?facts.map(fact=><button key={fact.id} onClick={()=>{setSelectedFact(fact.id);if(fact.page_number)setPage(fact.page_number)}} className={`w-full rounded-md border p-3 text-left transition ${selected?.id===fact.id?"border-blue-300/35 bg-blue-300/[.07]":"border-white/[.07] hover:bg-white/[.03]"}`}><div className="flex items-center justify-between gap-3"><span className="text-[9px] font-bold uppercase tracking-wide text-blue-300">{fact.fact_type.replaceAll("_"," ")}</span><span className="text-[9px] text-slate-600">{fact.page_number?`Page ${fact.page_number}`:fact.timestamp_seconds!=null?`${fact.timestamp_seconds}s`:fact.evidence_location}</span></div><p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-300">{observationText(fact)}</p><div className="mt-2 flex items-center gap-2"><StatusPill tone={fact.verified?"teal":"amber"}>{fact.verified?"Verified":"Human review"}</StatusPill>{fact.value.confidence_label&&<span className="text-[9px] text-slate-500">Model confidence: {String(fact.value.confidence_label)}</span>}</div></button>):<div className="rounded-md border border-dashed border-white/10 p-6 text-center"><Play size={20} className="mx-auto text-slate-600"/><p className="mt-3 text-xs text-slate-400">No observations were persisted. The status above shows whether analysis was skipped, empty, or failed.</p></div>}</CardContent></Card>
        {(current.media_type.startsWith("image/")||current.media_type.startsWith("video/"))&&<Card><CardContent><label className="flex gap-3 text-xs leading-5 text-slate-400"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)} className="mt-1"/><span>I authorize this file to be sent to the configured Gemini provider. Existing observations will remain in the audit trail as superseded.</span></label><Button onClick={reprocess} disabled={!authorized||busy} variant="secondary" className="mt-4 w-full"><RefreshCw size={14}/>{busy?"Reprocessing…":"Selectively reprocess media"}</Button></CardContent></Card>}
      </div>
    </div>
  </>;
}
