"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Activity, ArrowUpRight, BarChart3, CircleGauge, GitBranch, Radar, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export type OverviewProperty = {
  id:number; name:string; city:string; region:string; occupancy:string; construction:string; year_built:number;
  protection:string; risk_score:number; building_value_cents:number; equipment_value_cents:number;
  contents_value_cents:number; business_income_cents:number; tiv_cents:number;
  baseline_hazards:Record<string,string>;
};
export type OverviewHazard = { provider:string; event_type:string; severity:string; source_mode:string; matches?:unknown[] };
export type WorkflowSnapshot = { counts:Record<string,number>; summary:{workflow_types:Record<string,number>} };

const money = (cents:number) => new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",notation:"compact",maximumFractionDigits:1}).format(cents/100);
const short = (value:string,max=17) => value.length>max?`${value.slice(0,max-1)}…`:value;
const riskColor = (score:number) => score>=65?"#fb7185":score>=48?"#fbbf24":"#45d09d";

function PanelTitle({eyebrow,title,description,icon:Icon}:{eyebrow:string;title:string;description:string;icon:typeof Activity}){
  return <div className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl border border-white/[.08] bg-white/[.035]"><Icon size={16} className="text-teal-300"/></span><div><div className="text-[9px] font-bold uppercase tracking-[.15em] text-slate-500">{eyebrow}</div><h2 className="mt-1 text-base font-semibold text-slate-100">{title}</h2><p className="mt-1 text-[11px] leading-5 text-slate-500">{description}</p></div></div>;
}

function ExposureBarChart({properties}:{properties:OverviewProperty[]}){
  const sites=useMemo(()=>[...properties].sort((a,b)=>b.tiv_cents-a.tiv_cents).slice(0,10),[properties]);
  const [selectedId,setSelectedId]=useState(sites[0]?.id);
  const selected=sites.find(site=>site.id===selectedId)??sites[0];
  const max=Math.max(...sites.map(site=>site.tiv_cents),1);
  return <Card className="overflow-hidden xl:col-span-2"><CardHeader className="flex flex-row items-start justify-between gap-4"><PanelTitle eyebrow="Portfolio ranking" title="Declared exposure by site" description="Bar length is declared TIV; tint is the site risk index." icon={BarChart3}/>{selected&&<Link href={`/properties/${selected.id}`} className="hidden items-center gap-1 text-[11px] font-semibold text-teal-200 sm:flex">Open site <ArrowUpRight size={13}/></Link>}</CardHeader><CardContent className="pt-0">
    <div className="space-y-1.5 rounded-2xl border border-white/[.07] bg-[#0b0e0d] p-3 sm:p-4" role="group" aria-label="Interactive declared exposure bar chart">
      {sites.map((site,index)=>{const color=riskColor(site.risk_score);const active=site.id===selected?.id;return <button key={site.id} type="button" aria-label={`${site.name}, ${money(site.tiv_cents)} TIV, risk ${site.risk_score}`} onMouseEnter={()=>setSelectedId(site.id)} onFocus={()=>setSelectedId(site.id)} onClick={()=>setSelectedId(site.id)} className={`grid w-full grid-cols-[minmax(84px,145px)_minmax(0,1fr)_52px] items-center gap-2 rounded-xl border px-2 py-1.5 text-left transition sm:grid-cols-[175px_minmax(0,1fr)_64px] ${active?"border-white/[.13] bg-white/[.035]":"border-transparent hover:bg-white/[.018]"}`}>
        <div className="min-w-0"><div className="flex items-center gap-2"><span className="w-4 text-[9px] tabular-nums text-slate-600">{String(index+1).padStart(2,"0")}</span><span className={`truncate text-[10px] font-semibold sm:text-xs ${active?"text-slate-100":"text-slate-400"}`}>{site.name}</span></div><div className="ml-6 mt-0.5 hidden text-[9px] text-slate-600 sm:block">{site.city}, {site.region}</div></div>
        <span className="relative h-5 overflow-hidden rounded-md border border-white/[.055] bg-white/[.025]"><span className="absolute inset-y-0 left-0 rounded-[5px] transition-[width] duration-300" style={{width:`${Math.max(6,site.tiv_cents/max*100)}%`,background:`linear-gradient(90deg,${color}38,${color}a8)`,boxShadow:active?`0 0 18px ${color}2f`:"none"}}/><span className="absolute inset-y-0 left-1/4 border-l border-white/[.045]"/><span className="absolute inset-y-0 left-1/2 border-l border-white/[.045]"/><span className="absolute inset-y-0 left-3/4 border-l border-white/[.045]"/></span>
        <span className="text-right text-[10px] font-semibold tabular-nums text-slate-300 sm:text-xs">{money(site.tiv_cents)}</span>
      </button>})}
      <div className="grid grid-cols-[minmax(84px,145px)_minmax(0,1fr)_52px] gap-2 px-2 pt-1 text-[8px] uppercase tracking-[.1em] text-slate-700 sm:grid-cols-[175px_minmax(0,1fr)_64px]"><span/><span className="flex justify-between"><span>$0</span><span>{money(max)}</span></span><span/></div>
    </div>
    {selected&&<div className="mt-3 grid gap-2 rounded-2xl border border-white/[.07] bg-white/[.018] p-3 sm:grid-cols-[1fr_auto_auto_auto]"><div><div className="text-xs font-semibold text-slate-100">{selected.name}</div><div className="mt-1 text-[10px] text-slate-500">{selected.city}, {selected.region} · {selected.occupancy}</div></div><div className="rounded-xl border border-teal-300/10 bg-teal-300/[.045] px-3 py-2"><div className="text-[9px] uppercase text-slate-500">Declared TIV</div><div className="mt-1 text-xs font-semibold text-teal-100">{money(selected.tiv_cents)}</div></div><div className="rounded-xl border border-amber-300/10 bg-amber-300/[.045] px-3 py-2"><div className="text-[9px] uppercase text-slate-500">Risk index</div><div className="mt-1 text-xs font-semibold" style={{color:riskColor(selected.risk_score)}}>{selected.risk_score}/100</div></div><Link href={`/properties/${selected.id}`} className="inline-flex items-center justify-center gap-1 rounded-xl border border-white/[.09] bg-white/[.035] px-4 py-2 text-xs font-semibold text-slate-200 hover:border-teal-200/25 hover:text-teal-100">Inspect property <ArrowUpRight size={13}/></Link></div>}
  </CardContent></Card>;
}

function RiskGauge({properties}:{properties:OverviewProperty[]}){
  const avg=Math.round(properties.reduce((sum,p)=>sum+p.risk_score,0)/Math.max(properties.length,1));
  const high=properties.filter(p=>p.risk_score>=65).length;
  const color=riskColor(avg);
  return <Card><CardHeader><PanelTitle eyebrow="Portfolio gauge" title="Risk index" description="Simple average of persisted site risk scores—not a loss forecast." icon={CircleGauge}/></CardHeader><CardContent>
    <div className="relative mx-auto h-40 max-w-[300px]"><svg viewBox="0 0 240 145" className="h-full w-full" aria-label={`Portfolio average risk index ${avg} out of 100`}><path d="M25 125 A95 95 0 0 1 215 125" fill="none" stroke="#ffffff10" strokeWidth="18" pathLength="100" strokeLinecap="round"/><path d="M25 125 A95 95 0 0 1 215 125" fill="none" stroke={color} strokeWidth="18" pathLength="100" strokeDasharray={`${avg} 100`} strokeLinecap="round" className="drop-shadow-[0_0_8px_rgba(69,208,157,.32)]"/><line x1="120" y1="125" x2={120+72*Math.cos(Math.PI-(avg/100)*Math.PI)} y2={125-72*Math.sin((avg/100)*Math.PI)} stroke="#e8f2ed" strokeWidth="3" strokeLinecap="round"/><circle cx="120" cy="125" r="7" fill="#e8f2ed"/><text x="120" y="93" textAnchor="middle" fill="#f1f5f9" fontSize="34" fontWeight="600">{avg}</text><text x="120" y="110" textAnchor="middle" fill="#738078" fontSize="9">OUT OF 100</text></svg></div>
    <div className="grid grid-cols-3 gap-2 border-t border-white/[.07] pt-4 text-center"><div><div className="text-lg font-semibold text-teal-200">{properties.filter(p=>p.risk_score<48).length}</div><div className="text-[9px] uppercase text-slate-500">Controlled</div></div><div><div className="text-lg font-semibold text-amber-200">{properties.filter(p=>p.risk_score>=48&&p.risk_score<65).length}</div><div className="text-[9px] uppercase text-slate-500">Attention</div></div><div><div className="text-lg font-semibold text-rose-200">{high}</div><div className="text-[9px] uppercase text-slate-500">Elevated</div></div></div>
  </CardContent></Card>;
}

function RiskMatrix({properties}:{properties:OverviewProperty[]}){
  const [selectedId,setSelectedId]=useState(properties[0]?.id);const selected=properties.find(p=>p.id===selectedId)??properties[0];
  const max=Math.max(...properties.map(p=>p.tiv_cents),1);
  return <Card className="xl:col-span-2"><CardHeader className="flex flex-row items-start justify-between gap-4"><PanelTitle eyebrow="Interactive matrix" title="Risk × declared value" description="Each bubble is a site; size represents machinery concentration." icon={Radar}/>{selected&&<div className="hidden text-right sm:block"><div className="text-xs font-semibold text-slate-200">{short(selected.name,24)}</div><div className="mt-1 text-[10px] text-slate-500">Risk {selected.risk_score} · {money(selected.tiv_cents)}</div></div>}</CardHeader><CardContent className="pt-0"><div className="rounded-2xl border border-white/[.07] bg-black/10 p-2"><svg viewBox="0 0 700 310" className="h-[285px] w-full" role="img" aria-label="Risk and declared value matrix">
    <rect x="54" y="20" width="606" height="238" rx="12" fill="#0b0e0d"/><rect x="54" y="20" width="303" height="238" fill="#45d09d08"/><rect x="478" y="20" width="182" height="238" fill="#fb71850a"/>
    {[0,25,50,75,100].map(v=><g key={v}><line x1={54+v*6.06} y1="20" x2={54+v*6.06} y2="258" stroke="#ffffff0d"/><text x={54+v*6.06} y="280" textAnchor="middle" fill="#647067" fontSize="9">{v}</text></g>)}
    {[0,.25,.5,.75,1].map(v=><g key={v}><line x1="54" y1={258-v*238} x2="660" y2={258-v*238} stroke="#ffffff0d"/><text x="45" y={261-v*238} textAnchor="end" fill="#647067" fontSize="9">{money(max*v)}</text></g>)}
    {properties.map(p=>{const x=54+p.risk_score*6.06,y=258-(p.tiv_cents/max)*222;const r=6+Math.min(11,(p.equipment_value_cents/Math.max(p.tiv_cents,1))*34);const active=p.id===selected?.id;return <g key={p.id} tabIndex={0} role="button" aria-label={`${p.name}, risk ${p.risk_score}, ${money(p.tiv_cents)}`} onMouseEnter={()=>setSelectedId(p.id)} onFocus={()=>setSelectedId(p.id)} onClick={()=>setSelectedId(p.id)} className="cursor-pointer outline-none"><circle cx={x} cy={y} r={active?r+7:r+3} fill={riskColor(p.risk_score)} opacity={active ? .13 : .05}/><circle cx={x} cy={y} r={r} fill={riskColor(p.risk_score)} opacity={active ? .96 : .68} stroke={active?"#fff":"#ffffff55"}/></g>})}
    <text x="357" y="302" textAnchor="middle" fill="#7b877f" fontSize="10">SITE RISK INDEX →</text><text transform="translate(14 139) rotate(-90)" textAnchor="middle" fill="#7b877f" fontSize="10">DECLARED TIV →</text>
  </svg></div></CardContent></Card>;
}

function ControlRadar({properties}:{properties:OverviewProperty[]}){
  const current=(text:string)=>/current|sprinkler|protected|alarm/i.test(text);
  const facets=[
    ["Protection",properties.filter(p=>current(p.protection)).length/properties.length*100],
    ["Construction",properties.filter(p=>/steel|concrete|masonry|protected/i.test(p.construction)).length/properties.length*100],
    ["Risk control",100-properties.reduce((s,p)=>s+p.risk_score,0)/properties.length],
    ["Modernity",properties.reduce((s,p)=>s+Math.max(0,100-(2026-p.year_built)*2),0)/properties.length],
    ["Value spread",Math.max(25,100-(Math.max(...properties.map(p=>p.tiv_cents))/properties.reduce((s,p)=>s+p.tiv_cents,0))*100)],
    ["BI balance",100-Math.min(80,properties.reduce((s,p)=>s+p.business_income_cents,0)/properties.reduce((s,p)=>s+p.tiv_cents,0)*180)],
  ] as Array<[string,number]>;
  const points=facets.map(([,v],i)=>{const angle=-Math.PI/2+i*Math.PI*2/facets.length,r=82*Math.max(0,Math.min(100,v))/100;return `${120+Math.cos(angle)*r},${112+Math.sin(angle)*r}`}).join(" ");
  return <Card><CardHeader><PanelTitle eyebrow="Control profile" title="Portfolio radar" description="Normalized operational indicators derived from persisted site fields." icon={ShieldCheck}/></CardHeader><CardContent className="pt-0"><svg viewBox="0 0 240 235" className="mx-auto h-[260px] w-full max-w-[340px]" role="img" aria-label="Portfolio control radar chart">
    {[.33,.66,1].map(scale=><polygon key={scale} points={facets.map((_,i)=>{const a=-Math.PI/2+i*Math.PI*2/facets.length;return `${120+Math.cos(a)*82*scale},${112+Math.sin(a)*82*scale}`}).join(" ")} fill="none" stroke="#ffffff14"/>)}
    {facets.map(([label],i)=>{const a=-Math.PI/2+i*Math.PI*2/facets.length;return <g key={label}><line x1="120" y1="112" x2={120+Math.cos(a)*82} y2={112+Math.sin(a)*82} stroke="#ffffff10"/><text x={120+Math.cos(a)*105} y={116+Math.sin(a)*102} textAnchor={Math.cos(a)>.2?"start":Math.cos(a)<-.2?"end":"middle"} fill="#8a968e" fontSize="8">{label.toUpperCase()}</text></g>})}
    <polygon points={points} fill="#45d09d22" stroke="#45d09d" strokeWidth="2"/>{points.split(" ").map((point,i)=>{const [cx,cy]=point.split(",");return <circle key={i} cx={cx} cy={cy} r="3" fill="#9af2cf"/>})}
  </svg></CardContent></Card>;
}

function WorkflowRing({workflow}:{workflow:WorkflowSnapshot}){
  const items=[{key:"needs_evidence",label:"Needs evidence",color:"#fbbf24",fill:"#fbbf2499"},{key:"human_review",label:"Human review",color:"#fb7185",fill:"#fb718599"},{key:"completed",label:"Completed",color:"#45d09d",fill:"#45d09d99"}];
  const total=items.reduce((sum,item)=>sum+(workflow.counts[item.key]??0),0)||1;let cursor=0;const stops=items.map(item=>{const start=cursor;cursor+=(workflow.counts[item.key]??0)/total*100;return `${item.fill} ${start}% ${cursor}%`}).join(",");
  return <Card className="bg-[radial-gradient(circle_at_20%_80%,rgba(251,113,133,.055),transparent_48%),linear-gradient(145deg,#171a18,#121412)]"><CardHeader><PanelTitle eyebrow="Workflow pulse" title="Human checkpoint load" description="Persisted runs by their current queue." icon={GitBranch}/></CardHeader><CardContent><div className="flex flex-col items-center gap-5 sm:flex-row"><div className="relative grid size-40 shrink-0 place-items-center rounded-full border border-white/[.06] p-2" style={{background:`conic-gradient(${stops})`,boxShadow:"inset 0 0 26px #0008"}}><div className="grid size-[112px] place-items-center rounded-full border border-white/[.07] bg-[#121513]"><div className="text-center"><div className="text-3xl font-semibold text-slate-100">{total}</div><div className="text-[9px] uppercase tracking-[.12em] text-slate-500">runs</div></div></div></div><div className="w-full space-y-2">{items.map(item=><div key={item.key} className="flex items-center gap-3 rounded-xl border border-white/[.06] px-3 py-2" style={{background:`linear-gradient(90deg,${item.fill},transparent 38%)`}}><span className="size-2 rounded-full border border-white/30" style={{background:item.color,boxShadow:`0 0 10px ${item.color}55`}}/><span className="flex-1 text-xs text-slate-300">{item.label}</span><span className="text-sm font-semibold text-slate-100">{workflow.counts[item.key]??0}</span></div>)}</div></div></CardContent></Card>;
}

function ExposureMix({properties,hazards}:{properties:OverviewProperty[];hazards:OverviewHazard[]}){
  const totals=[
    ["Building",properties.reduce((s,p)=>s+p.building_value_cents,0),"#45d09d"],
    ["Equipment",properties.reduce((s,p)=>s+p.equipment_value_cents,0),"#fbbf24"],
    ["Contents",properties.reduce((s,p)=>s+p.contents_value_cents,0),"#fb7185"],
    ["Business income",properties.reduce((s,p)=>s+p.business_income_cents,0),"#8de7c4"],
  ] as Array<[string,number,string]>;const total=totals.reduce((s,item)=>s+item[1],0)||1;
  const sources=Object.entries(hazards.reduce<Record<string,number>>((all,h)=>{all[h.provider]=(all[h.provider]??0)+1;return all},{})).sort((a,b)=>b[1]-a[1]);const maxSource=Math.max(...sources.map(([,n])=>n),1);
  return <Card className="bg-[radial-gradient(circle_at_8%_100%,rgba(69,208,157,.06),transparent_42%),linear-gradient(145deg,#171a18,#121412)] xl:col-span-2"><CardHeader><PanelTitle eyebrow="Composition + signals" title="Value mix and hazard feed" description="Declared exposure composition alongside currently persisted event sources." icon={Activity}/></CardHeader><CardContent><div className="grid gap-8 lg:grid-cols-[1.25fr_.75fr]"><div><div className="flex h-5 gap-1 overflow-hidden rounded-full bg-white/[.035] p-1">{totals.map(([label,value,color])=><div key={label} title={`${label}: ${money(value)}`} style={{width:`${value/total*100}%`,background:`linear-gradient(90deg,${color}55,${color}aa)`,boxShadow:`inset 0 0 0 1px ${color}55`}} className="h-full rounded-full"/>)}</div><div className="mt-5 grid gap-3 sm:grid-cols-2">{totals.map(([label,value,color])=><div key={label} className="flex items-center gap-3 rounded-xl border border-white/[.055] p-2.5" style={{background:`linear-gradient(100deg,${color}12,transparent 46%)`}}><span className="size-2.5 rounded-sm border border-white/25" style={{background:`${color}99`}}/><div className="flex-1"><div className="text-xs text-slate-400">{label}</div><div className="mt-0.5 text-sm font-semibold text-slate-100">{money(value)}</div></div><div className="text-[10px] text-slate-500">{Math.round(value/total*100)}%</div></div>)}</div></div><div className="border-t border-white/[.07] pt-5 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0"><div className="mb-4 text-[10px] font-bold uppercase tracking-[.13em] text-slate-500">Events by source</div><div className="space-y-4">{sources.map(([source,count],index)=>{const color=["#45d09d","#fbbf24","#fb7185"][index%3];return <div key={source}><div className="mb-1.5 flex justify-between text-[10px]"><span className="text-slate-400">{source.replaceAll("_"," ")}</span><span className="font-semibold text-slate-200">{count}</span></div><div className="h-2 overflow-hidden rounded-full border border-white/[.05] bg-white/[.025]"><div className="h-full rounded-full" style={{width:`${count/maxSource*100}%`,background:`linear-gradient(90deg,${color}44,${color}aa)`}}/></div></div>})}</div></div></div></CardContent></Card>;
}

export function ExecutiveVisuals({properties,hazards,workflow}:{properties:OverviewProperty[];hazards:OverviewHazard[];workflow:WorkflowSnapshot}){
  if(!properties.length)return null;
  return <section className="mt-6" aria-labelledby="portfolio-intelligence-heading"><div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><div className="text-[10px] font-bold uppercase tracking-[.15em] text-teal-300">Live portfolio intelligence</div><h2 id="portfolio-intelligence-heading" className="mt-1 text-2xl font-semibold tracking-tight text-slate-100">One portfolio, six decision lenses</h2></div><p className="max-w-xl text-xs leading-5 text-slate-500">Every visual uses persisted portfolio, workflow, or hazard records. Exposure is declared value; risk indicators are operational signals, not actuarial loss predictions.</p></div><div className="grid gap-4 xl:grid-cols-3"><ExposureBarChart properties={properties}/><RiskGauge properties={properties}/><RiskMatrix properties={properties}/><ControlRadar properties={properties}/><WorkflowRing workflow={workflow}/><ExposureMix properties={properties} hazards={hazards}/></div></section>;
}
