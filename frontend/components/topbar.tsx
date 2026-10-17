"use client";
import Link from "next/link";
import { Bell, CircleHelp, Menu, Search } from "lucide-react";
import { navigation } from "@/components/sidebar";
import { Property2ClaimMark } from "@/components/property2claim-mark";

export function Topbar() {
  return <header className="sticky top-0 z-20 flex h-16 items-center border-b border-white/[.07] bg-[#121512]/95 px-4 backdrop-blur-xl sm:px-5 lg:px-8">
    <details className="group relative mr-3 lg:hidden"><summary className="grid size-9 cursor-pointer list-none place-items-center rounded-full border border-white/[.1] text-slate-400 transition hover:bg-white/5 hover:text-slate-100"><Menu size={18} /></summary><nav className="absolute left-0 top-12 w-64 space-y-1 rounded-2xl border border-white/[.1] bg-[#131713] p-2 shadow-2xl">{navigation.map(([href, label, Icon]) => <Link key={href} href={href} className="flex items-center gap-3 rounded-full px-3 py-2.5 text-sm text-slate-300 transition hover:bg-teal-300/[.07] hover:text-teal-100"><Icon size={16} />{label}</Link>)}</nav></details>
    <Link href="/" className="mr-4 flex items-center gap-2 lg:hidden"><Property2ClaimMark compact /><span className="hidden text-sm font-semibold text-slate-100 sm:block">Property2Claim</span></Link>
    <div className="hidden max-w-lg flex-1 items-center gap-2 rounded-full border border-white/[.08] bg-black/20 px-4 py-2 text-sm text-slate-500 transition focus-within:border-teal-300/25 sm:flex"><Search size={14} /><span>Search accounts, sites, claims…</span><kbd className="ml-auto rounded-full border border-white/[.08] bg-white/[.025] px-2 py-0.5 text-[9px] text-slate-500">Ctrl K</kbd></div>
    <div className="ml-auto flex items-center gap-1"><button className="grid size-9 place-items-center rounded-full border border-transparent text-slate-500 transition hover:border-white/[.07] hover:bg-white/[.04] hover:text-slate-200" aria-label="Help"><CircleHelp size={17} /></button><button className="relative grid size-9 place-items-center rounded-full border border-transparent text-slate-500 transition hover:border-white/[.07] hover:bg-white/[.04] hover:text-slate-200" aria-label="Notifications"><Bell size={17} /><span className="absolute right-2 top-2 size-1.5 rounded-full bg-amber-400 ring-2 ring-[#121512]" /></button><div className="ml-2 grid size-9 place-items-center rounded-full border border-teal-200/15 bg-teal-300/[.07] text-[10px] font-bold text-teal-100">AR</div></div>
  </header>;
}
