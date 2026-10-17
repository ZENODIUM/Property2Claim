"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FileImage, ShieldCheck } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Property } from "@/lib/types";
import { currency, formatDate } from "@/lib/utils";

type Detail = Property & { company: {id:number;name:string}; risk_categories: Array<{category:number;name:string;data:Record<string,unknown>;source_type:string;verification_status:string;observed_at:string;last_verified_at:string}>; assets:Array<{id:number;asset_code:string;name:string;asset_type:string;insured_value_cents:number;criticality:string}>; inspections:Array<{id:number;type:string;status:string;expires_at:string;findings:Array<{id:number;finding:string;severity:string;status:string}>}>; floorplans:Array<{id:number;state:string}> };

export default function PropertyPage() {
  const id = useParams<{id:string}>().id; const { data, loading, error } = useApi<Detail>(`/properties/${id}`);
  if (loading) return <LoadingState />; if (error || !data) return <ErrorState message={error ?? "No data"}/>;
  return <><PageHeader eyebrow={`${data.company.name} · ${data.site_code}`} title={data.name} description={`${data.address}, ${data.city}, ${data.region} · Original source timestamps and verification status shown below.`} actions={<Link href={`/properties/${data.id}/floorplan`} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white"><FileImage size={16}/>2D floor plan</Link>}/>
    <div className="grid gap-4 md:grid-cols-4"><Card><CardContent><div className="text-xs text-slate-500">Declared TIV</div><div className="mt-2 text-2xl font-semibold">{currency(data.tiv_cents, true)}</div></CardContent></Card><Card><CardContent><div className="text-xs text-slate-500">Construction</div><div className="mt-2 text-sm font-semibold capitalize">{data.construction}</div></CardContent></Card><Card><CardContent><div className="text-xs text-slate-500">Protection</div><div className="mt-2 text-sm font-semibold">{data.protection}</div></CardContent></Card><Card><CardContent><div className="text-xs text-slate-500">Risk score</div><div className="mt-2 text-2xl font-semibold">{data.risk_score}<span className="text-sm text-slate-400">/100</span></div></CardContent></Card></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_.85fr]"><Card><CardHeader><h2 className="font-semibold">15 locked insurance datasets</h2><p className="mt-1 text-xs text-slate-500">Versioned source records, not inferred UI-only values.</p></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2">{data.risk_categories.map(r => <div key={r.category} className="rounded-lg border border-slate-100 bg-slate-50 p-3"><div className="flex items-start gap-2"><span className="grid size-6 shrink-0 place-items-center rounded bg-slate-800 text-[10px] font-bold text-white">{r.category}</span><div className="min-w-0"><div className="text-xs font-semibold">{r.name}</div><div className="mt-1 text-[11px] text-slate-500">{r.source_type} · {formatDate(r.last_verified_at)}</div></div><StatusPill tone={r.verification_status === "verified" ? "teal" : "amber"}>{r.verification_status}</StatusPill></div></div>)}</CardContent></Card><div className="space-y-6"><Card><CardHeader><h2 className="font-semibold">Inspections & findings</h2></CardHeader><CardContent className="space-y-3">{data.inspections.map(i => <div key={i.id} className="rounded-lg border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-2"><ShieldCheck size={16} className="text-amber-700"/><span className="text-sm font-semibold">{i.type.replaceAll("_", " ")}</span><StatusPill tone="amber">{i.status}</StatusPill></div>{i.findings.map(f => <p key={f.id} className="mt-2 text-xs leading-5 text-amber-900">{f.finding}</p>)}</div>)}</CardContent></Card><Card><CardHeader><h2 className="font-semibold">Asset schedule</h2></CardHeader><CardContent className="space-y-2">{data.assets.map(a => <div key={a.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"><div><div className="text-xs font-semibold">{a.name}</div><div className="text-[11px] text-slate-500">{a.asset_code} · {a.asset_type}</div></div><div className="text-xs font-semibold">{currency(a.insured_value_cents, true)}</div></div>)}</CardContent></Card></div></div>
  </>;
}
