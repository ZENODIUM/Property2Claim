"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, ClipboardCheck, FileClock, Gauge, Layers3, Map, Radar, Route, Settings, ShieldCheck, UserPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import { Property2ClaimMark } from "@/components/property2claim-mark";

export const navigation = [
  ["/", "Overview", Gauge], ["/demo", "Guided lifecycle", Route], ["/onboarding", "Account onboarding", UserPlus],
  ["/portfolio", "Portfolio globe", Map], ["/companies", "Companies & properties", Building2], ["/underwriting", "Underwriting", ShieldCheck],
  ["/hazards", "Hazard intelligence", Radar], ["/claims", "Claims desk", ClipboardCheck], ["/tasks", "Agent tasks", FileClock],
  ["/audit", "Workflow results", Layers3], ["/settings", "Settings", Settings],
] as const;

export function Sidebar() {
  const pathname = usePathname();
  return <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-white/[.07] bg-[#101110] text-slate-400 shadow-[18px_0_55px_rgba(0,0,0,.13)] lg:flex lg:flex-col">
    <div className="flex h-20 items-center gap-3 border-b border-white/[.07] px-5"><Property2ClaimMark /><div><div className="font-semibold tracking-[-.025em] text-slate-100">Property2Claim</div><div className="text-[9px] font-bold uppercase tracking-[.16em] text-slate-500">Property intelligence</div></div></div>
    <div className="mx-4 mt-5 flex items-center gap-2 rounded-full border border-teal-300/15 bg-teal-300/[.045] px-3 py-2 text-[10px] font-semibold text-teal-100/80"><span className="size-1.5 rounded-full bg-teal-300 shadow-[0_0_9px_rgba(94,234,212,.85)]"/>Human review controls active</div>
    <nav className="mt-5 space-y-1 px-3">{navigation.map(([href, label, Icon]) => { const active = href === "/" ? pathname === "/" : pathname.startsWith(href); return <Link key={href} href={href} className={cn("group flex items-center gap-3 rounded-full border border-transparent px-3 py-2.5 text-[12px] transition", active ? "border-teal-200/15 bg-teal-300/[.09] font-semibold text-teal-100 shadow-[inset_0_1px_rgba(255,255,255,.025),0_0_24px_rgba(70,205,156,.04)]" : "hover:border-white/[.06] hover:bg-white/[.035] hover:text-slate-100")}><Icon size={16} className={active ? "text-teal-200" : "text-slate-500 transition group-hover:text-slate-200"} /><span>{label}</span>{active && <span className="ml-auto size-1 rounded-full bg-teal-300 shadow-[0_0_8px_rgba(94,234,212,.8)]"/>}</Link>; })}</nav>
    <div className="mt-auto border-t border-white/[.07] p-4"><div className="rounded-2xl border border-white/[.07] bg-white/[.025] p-3"><div className="flex items-center gap-2.5"><span className="grid size-8 place-items-center rounded-full border border-teal-200/15 bg-teal-300/[.08] text-[9px] font-bold text-teal-100">AR</span><div><div className="text-xs font-semibold text-slate-200">Alex Rivera</div><div className="text-[10px] text-slate-500">Senior property reviewer</div></div></div></div></div>
  </aside>;
}
