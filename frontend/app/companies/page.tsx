"use client";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { CompanyLogo } from "@/components/company-logo";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Company } from "@/lib/types";
import { currency } from "@/lib/utils";

const tones = ["surface-teal", "surface-blue", "surface-rose", "surface-amber", "surface-violet", "surface-teal"];

export default function CompaniesPage() {
  const { data, loading, error } = useApi<{items: Company[]}>("/companies");
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "No data"} />;
  return <><PageHeader eyebrow="Accounts" title="Companies & properties" description="Managed accounts with connected locations, declared values, COPE evidence, policies, and work history." />
    <div className="grid gap-4 lg:grid-cols-2">{data.items.map((company, index) => <Card key={company.id} className={`group overflow-hidden p-5 hover:-translate-y-0.5 ${tones[index % tones.length]}`}><div className="flex items-start gap-4"><CompanyLogo name={company.name}/><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h2 className="font-semibold tracking-[-.015em] text-slate-100">{company.name}</h2><span className="size-1.5 rounded-full bg-teal-300 shadow-[0_0_9px_rgba(94,234,212,.65)]"/></div><p className="mt-1 text-sm text-slate-400">{company.industry}</p><div className="mt-5 flex gap-10"><div><div className="text-xl font-medium text-slate-100">{company.property_count}</div><div className="mt-1 text-[10px] uppercase tracking-[.12em] text-slate-500">Properties</div></div><div><div className="text-xl font-medium text-slate-100">{currency(company.tiv_cents, true)}</div><div className="mt-1 text-[10px] uppercase tracking-[.12em] text-slate-500">Declared TIV</div></div></div></div><Link href={`/companies/${company.id}`} aria-label={`Open ${company.name}`} className="grid size-10 place-items-center rounded-full border border-white/[.09] bg-white/[.025] text-slate-400 transition group-hover:border-teal-200/25 group-hover:bg-teal-300/[.07] group-hover:text-teal-200"><ArrowUpRight size={17}/></Link></div></Card>)}</div>
  </>;
}
