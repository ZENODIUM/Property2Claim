"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, Factory, MapPin } from "lucide-react";
import { CompanyLogo } from "@/components/company-logo";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Company, Property } from "@/lib/types";
import { currency } from "@/lib/utils";

export default function CompanyPage() {
  const id = useParams<{id:string}>().id;
  const { data, loading, error } = useApi<Company & { properties: Property[]; tiv_cents: number }>(`/companies/${id}`);
  if (loading) return <LoadingState />; if (error || !data) return <ErrorState message={error ?? "No data"}/>;
  return <><PageHeader eyebrow="Managed account" title={data.name} description={`${data.industry} · ${data.properties.length} locations · ${currency(data.tiv_cents, true)} declared total insured value.`} actions={<div className="flex items-center gap-3"><CompanyLogo name={data.name} className="size-10"/><Link href={`/portfolio?company=${data.id}`} className="inline-flex h-10 items-center rounded-full border border-white/[.1] bg-white/[.035] px-4 text-sm font-semibold text-slate-200 hover:border-teal-200/25 hover:text-teal-100">View on map</Link></div>}/><div className="space-y-4">{data.properties.map(property => <Card key={property.id} className={property.risk_score > 65 ? "surface-amber" : "surface-teal"}><CardContent className="flex flex-wrap items-center gap-5"><div className="grid size-12 place-items-center rounded-2xl border border-white/[.08] bg-black/15 text-teal-300"><Factory size={21}/></div><div className="min-w-[220px] flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-slate-100">{property.name}</h2><StatusPill tone={property.risk_score > 65 ? "amber" : "teal"}>Risk {property.risk_score}</StatusPill></div><div className="mt-1 flex items-center gap-1 text-xs text-slate-500"><MapPin size={13}/>{property.address}, {property.city}, {property.region}</div></div><div className="grid grid-cols-3 gap-8 text-sm"><div><div className="font-semibold text-slate-100">{currency(property.tiv_cents, true)}</div><div className="text-xs text-slate-500">Declared TIV</div></div><div><div className="font-semibold capitalize text-slate-100">{property.occupancy}</div><div className="text-xs text-slate-500">Occupancy</div></div><div><div className="font-semibold text-slate-100">{property.year_built}</div><div className="text-xs text-slate-500">Year built</div></div></div><Link href={`/properties/${property.id}`} className="inline-flex items-center gap-2 rounded-full border border-teal-200/20 bg-teal-300/[.08] px-4 py-2 text-xs font-semibold text-teal-100 hover:bg-teal-300/[.13]">Open site <ArrowRight size={14}/></Link></CardContent></Card>)}</div></>;
}
