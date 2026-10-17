"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Building2, MapPin, MapPinned, Radar, ShieldAlert, X } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { PortfolioMap } from "@/components/portfolio-map";
import { StatusPill } from "@/components/status-pill";
import { Card } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Company, Hazard, Property } from "@/lib/types";
import { currency } from "@/lib/utils";

type RiskFilter = "all" | "high" | "elevated" | "lower";
type SiteProfileImage = { src: string; alt: string; credit: string; source: string };
const COMPANY_COLORS = ["#38bdf8", "#a78bfa", "#2dd4bf", "#f472b6", "#fb923c", "#a3e635", "#facc15", "#818cf8"];

const profileImages = {
  warehouse: { src: "/site-profiles/warehouse.jpg", alt: "Representative warehouse loading docks", credit: "Matthew Jackson", source: "https://unsplash.com/photos/SJGC3NNOqU4" },
  logistics: { src: "/site-profiles/forklift-warehouse.jpg", alt: "Representative forklift warehouse operation", credit: "U.S. Department of Agriculture / Lance Cheung", source: "https://commons.wikimedia.org/wiki/File:Workers_drive_Forklifts_laden_with_USAID_goods_inside_a_large_warehouse_-_20110826-FS-LSC-0425_-_Flickr_-_USDAgov.jpg" },
  manufacturing: { src: "/site-profiles/manufacturing.jpg", alt: "Representative automated manufacturing line", credit: "Simon Kadula", source: "https://unsplash.com/photos/8gr6bObQLOI" },
  molding: { src: "/site-profiles/injection-molding.jpg", alt: "Representative injection-molding production floor", credit: "Orionpenindia", source: "https://commons.wikimedia.org/wiki/File:Inside_the_factory.jpg" },
  machining: { src: "/site-profiles/machining.jpg", alt: "Representative precision machining equipment", credit: "hosein fayton", source: "https://unsplash.com/photos/NL-ugfz7zSw" },
  food: { src: "/site-profiles/food-processing.jpg", alt: "Representative food processing equipment", credit: "Aitokhuehi", source: "https://commons.wikimedia.org/wiki/File:A_public_food_processing_factory.jpg" },
  textile: { src: "/site-profiles/textile-machinery.jpg", alt: "Representative textile machinery", credit: "Wikimedia Commons contributor", source: "https://commons.wikimedia.org/wiki/File:Slater_Mill_-_textile_machines.jpg" },
  retail: { src: "/site-profiles/retail.jpg", alt: "Representative urban retail storefront", credit: "Cameron J.", source: "https://unsplash.com/photos/D7QlNXWruNg" },
} satisfies Record<string, SiteProfileImage>;

function siteProfileImage(property: Property): SiteProfileImage {
  const occupancy = property.occupancy.toLowerCase();
  if (occupancy.includes("retail")) return profileImages.retail;
  if (occupancy.includes("food")) return profileImages.food;
  if (occupancy.includes("textile")) return profileImages.textile;
  if (occupancy.includes("heavy manufacturing")) return profileImages.molding;
  if (occupancy.includes("machin")) return profileImages.machining;
  if (occupancy.includes("cross-dock") || occupancy.includes("warehouse")) return profileImages.logistics;
  if (occupancy.includes("manufactur")) return profileImages.manufacturing;
  return profileImages.warehouse;
}

function PortfolioContent() {
  const search = useSearchParams();
  const initial = search.get("company") ?? "all";
  const [company, setCompany] = useState(initial);
  const [risk, setRisk] = useState<RiskFilter>("all");
  const [hazardProvider, setHazardProvider] = useState("all");
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [timelineAnchor] = useState(() => Date.now());
  const [selected, setSelected] = useState<Property>();
  const props = useApi<{ items: Property[] }>("/properties");
  const companies = useApi<{ items: Company[] }>("/companies");
  const hazards = useApi<{ items: Hazard[] }>("/hazards");

  const filtered = useMemo(() => props.data?.items.filter((property) => {
    if (company !== "all" && property.company_id !== Number(company)) return false;
    if (risk === "high") return property.risk_score >= 70;
    if (risk === "elevated") return property.risk_score >= 45 && property.risk_score < 70;
    if (risk === "lower") return property.risk_score < 45;
    return true;
  }) ?? [], [props.data, company, risk]);
  const onSelect = useCallback((property: Property) => setSelected(property), []);

  if (props.loading || companies.loading || hazards.loading) return <LoadingState label="Loading portfolio geography…" />;
  const error = props.error ?? companies.error ?? hazards.error;
  if (error || !props.data || !companies.data || !hazards.data) return <ErrorState message={error ?? "No data"} />;

  const timelineCenter = timelineAnchor + timelineOffset * 86_400_000;
  const visibleHazards = hazards.data.items.filter((hazard) => (hazardProvider === "all" || hazard.provider === hazardProvider) && (timelineOffset === 14 || Math.abs(new Date(hazard.valid_at).getTime() - timelineCenter) <= 14 * 86_400_000));
  const hazardProviders = [...new Set(hazards.data.items.map((hazard) => hazard.provider))];
  const visibleIds = new Set(filtered.map((property) => property.id));
  const matchedIds = new Set(visibleHazards.flatMap((hazard) => hazard.matches.map((match) => match.property_id)).filter((id) => visibleIds.has(id)));
  const totalTiv = filtered.reduce((total, property) => total + property.tiv_cents, 0);
  const selectedCompany = selected ? companies.data.items.find((item) => item.id === selected.company_id) : undefined;
  const selectedImage = selected ? siteProfileImage(selected) : undefined;

  return <>
    <PageHeader eyebrow="Geographic portfolio" title="Portfolio map" description="Review insured locations with live NOAA/NASA events and controlled hazard scenarios in either globe or flat-map view. Declared values are exposure—not modeled or confirmed losses." />

    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="metric-strip"><Building2 size={17} /><div><strong>{filtered.length}</strong><span>visible insured sites</span></div></div>
      <div className="metric-strip"><Radar size={17} /><div><strong>{matchedIds.size}</strong><span>sites in replay areas</span></div></div>
      <div className="metric-strip"><ShieldAlert size={17} /><div><strong>{currency(totalTiv, true)}</strong><span>declared visible TIV</span></div></div>
    </div>

    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-white/[.07] px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
        <div className="flex min-w-0 items-center gap-3"><label className="shrink-0 text-[10px] font-bold uppercase tracking-[.14em] text-slate-500">Company</label><select className="input min-w-0 sm:w-64" value={company} onChange={(event) => setCompany(event.target.value)}><option value="all">All portfolio companies</option>{companies.data.items.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></div>
        <div className="flex min-w-0 items-center gap-3"><label className="shrink-0 text-[10px] font-bold uppercase tracking-[.14em] text-slate-500">Risk</label><select className="input min-w-0 sm:w-40" value={risk} onChange={(event) => setRisk(event.target.value as RiskFilter)}><option value="all">All scores</option><option value="high">High · 70+</option><option value="elevated">Elevated · 45–69</option><option value="lower">Lower · under 45</option></select></div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-slate-500 sm:ml-auto">
          <span className="flex items-center gap-2"><i className="size-2.5 rounded-full border-2 border-white bg-teal-300" />Company colour</span>
          <span className="flex items-center gap-2"><i className="size-3 rounded-full border border-amber-300 bg-amber-400/15" />Elevated attention</span>
          <span className="flex items-center gap-2"><i className="size-3 rounded-full border border-rose-300 bg-rose-400/20" />High / hazard matched</span>
          <span className="flex items-center gap-2"><i className="size-3 border border-amber-400 bg-amber-400/20" />Environmental footprint</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-white/[.07] px-4 py-2.5 sm:px-5">{companies.data.items.map((item, index) => <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.025] px-2.5 py-1 text-[10px] text-slate-300" key={item.id}><i className="size-2 rounded-full" style={{backgroundColor:COMPANY_COLORS[index % COMPANY_COLORS.length]}} />{item.name}</span>)}</div>
      <div className="grid gap-3 border-b border-white/[.07] px-4 py-3 lg:grid-cols-[210px_minmax(0,1fr)_120px] lg:items-center sm:px-5"><select className="input" value={hazardProvider} onChange={event=>setHazardProvider(event.target.value)}><option value="all">All hazard sources</option>{hazardProviders.map(item=><option key={item}>{item}</option>)}</select><div className="flex items-center gap-3"><span className="text-[10px] font-bold uppercase tracking-[.1em] text-slate-500">Timeline</span><input aria-label="Map hazard timeline" type="range" min="-365" max="14" value={timelineOffset} onChange={event=>setTimelineOffset(Number(event.target.value))} className="w-full accent-teal-400"/></div><div className="text-right text-xs text-slate-400">{timelineOffset>0?`+${timelineOffset}d scenario`:timelineOffset===0?"Current":`${Math.abs(timelineOffset)}d history`}</div></div>
      <div className="relative">
        <PortfolioMap properties={filtered} hazards={visibleHazards} companies={companies.data.items} onSelect={onSelect} />
        {selected && selectedImage && <div className="absolute bottom-4 left-4 z-30 max-h-[calc(100%-32px)] w-[min(420px,calc(100%-32px))] overflow-y-auto rounded-lg border border-white/15 bg-[#1b222c] shadow-xl sm:bottom-5 sm:left-5">
          <div className="relative h-36 overflow-hidden rounded-t-lg bg-slate-800">
            <Image src={selectedImage.src} alt={selectedImage.alt} fill sizes="(max-width: 640px) calc(100vw - 32px), 420px" className="object-cover" />
            <button type="button" aria-label="Close property details" onClick={() => setSelected(undefined)} className="absolute right-3 top-3 grid size-8 place-items-center rounded-md border border-white/20 bg-slate-950/80 text-slate-200 transition hover:bg-slate-900"><X size={16} /></button>
          </div>
          <div className="border-b border-white/10 px-5 py-2 text-[10px] text-slate-400">Illustrative stock image—not the insured site · <a href={selectedImage.source} target="_blank" rel="noreferrer" className="text-blue-300 hover:underline">Photo by {selectedImage.credit}</a></div>
          <div className="p-5">
            <div><StatusPill tone="blue">Insured property</StatusPill><h2 className="mt-3 text-lg font-semibold text-slate-100">{selected.name}</h2><div className="mt-1 flex items-center gap-1 text-xs text-slate-500"><MapPin size={13} />{selected.city}, {selected.region}</div>{selectedCompany && <div className="mt-1 text-xs text-slate-400">{selectedCompany.name} · {selected.occupancy}</div>}</div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md border border-white/10 bg-white/[.04] p-3"><div className="font-semibold text-slate-100">{currency(selected.tiv_cents, true)}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">Declared TIV</div></div>
              <div className="rounded-md border border-white/10 bg-white/[.04] p-3"><div className={selected.risk_score >= 70 ? "font-semibold text-rose-300" : selected.risk_score >= 45 ? "font-semibold text-amber-300" : "font-semibold text-blue-300"}>{selected.risk_score}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">Risk index</div></div>
              <div className="rounded-md border border-white/10 bg-white/[.04] p-3"><div className="font-semibold text-slate-100">{selected.area_sqft.toLocaleString()} sq ft</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">Area</div></div>
              <div className="rounded-md border border-white/10 bg-white/[.04] p-3"><div className="font-semibold text-slate-100">{selected.year_built}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">Year built</div></div>
            </div>
            <Link href={`/properties/${selected.id}/floorplan`} className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-blue-500 px-4 text-sm font-semibold text-white transition hover:bg-blue-400"><MapPinned size={16} />Open site detailed map (2D)</Link>
            <Link href={`/properties/${selected.id}`} className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-blue-300 transition hover:text-blue-200">Open full property record <ArrowRight size={14} /></Link>
          </div>
        </div>}
      </div>
    </Card>
    <p className="mt-3 text-[11px] leading-5 text-slate-600">Satellite imagery: Esri World Imagery with NASA EOSDIS GIBS fallback. Site profile photos are representative stock imagery and are not evidence from the insured properties. Hazard areas are deterministic scenario replays or configured source adapters; they are not live emergency guidance.</p>
  </>;
}

export default function PortfolioPage() { return <Suspense fallback={<LoadingState />}><PortfolioContent /></Suspense>; }
