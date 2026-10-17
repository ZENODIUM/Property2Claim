"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowUpRight, Bot, CheckCircle2, GitBranch, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

type NodeId =
  | "accounts" | "documents" | "alerts" | "fnol" | "photos" | "plans"
  | "groq" | "cope" | "uwJev" | "uwAsk" | "premium" | "uwHuman"
  | "match" | "hzTask" | "hzHuman"
  | "reconcile" | "gemini" | "spatial" | "clmJev" | "quote" | "specialist" | "estimate" | "clmHuman"
  | "terms" | "exposure" | "audit";

type Kind = "source" | "ai" | "rules" | "jev" | "human" | "record";

type NodeDef = {
  id: NodeId;
  label: string;
  sub: string;
  kind: Kind;
  detail: string;
  decides: string;
  x: number;
  y: number;
};

const kindStyle: Record<Kind, { color: string; tech: string; icon: typeof Bot }> = {
  source: { color: "#60a5fa", tech: "Input", icon: GitBranch },
  ai: { color: "#c084fc", tech: "Proposes only", icon: Bot },
  rules: { color: "#2dd4bf", tech: "Calculated", icon: SlidersHorizontal },
  jev: { color: "#fbbf24", tech: "Names a queue", icon: GitBranch },
  human: { color: "#fb7185", tech: "Person decides", icon: ShieldCheck },
  record: { color: "#34d399", tech: "Written record", icon: CheckCircle2 },
};

const W = 108;
const H = 36;

const nodes: NodeDef[] = [
  { id: "accounts", label: "Accounts", sub: "SOV · values", kind: "source", x: 16, y: 58, decides: "Nothing is decided on intake.", detail: "Company, site, and schedule-of-values rows enter as versioned records." },
  { id: "documents", label: "Documents", sub: "PDF text", kind: "source", x: 16, y: 108, decides: "The file is stored with its pages.", detail: "Inspection reports and quotes keep the page each fact came from. Groq may summarize the text later." },
  { id: "alerts", label: "Alerts", sub: "NASA · NOAA", kind: "source", x: 16, y: 198, decides: "An alert is not a loss.", detail: "Live alerts or the deterministic replay become GeoJSON. The replay matches Houston Factory A and Tulsa Factory B." },
  { id: "fnol", label: "FNOL", sub: "Reported loss", kind: "source", x: 16, y: 384, decides: "A reported loss opens the claim. Weather does not.", detail: "The notice links the property, the synthetic policy, and the reported exposures." },
  { id: "photos", label: "Photos", sub: "Image · video", kind: "source", x: 16, y: 328, decides: "Media is retained. Analysis is optional.", detail: "Gemini runs only after explicit authorization. Otherwise the file stays on record with no invented findings." },
  { id: "plans", label: "Floor plans", sub: "Original 2D", kind: "source", x: 16, y: 436, decides: "The drawing is the source layer.", detail: "Architectural, machinery, and fire sheets stay aligned. Boxes are proposals until a person verifies them." },

  { id: "groq", label: "Groq", sub: "Summarizes", kind: "ai", x: 214, y: 52, decides: "Groq summarizes supplied text. It does not choose a route or a price.", detail: "A missing or failed call stays a labeled fallback." },
  { id: "cope", label: "COPE", sub: "Rules", kind: "rules", x: 348, y: 78, decides: "Rules flag a missing certificate or a protection conflict.", detail: "Construction, occupancy, protection, and exposure are checked in code. This does not approve the account." },
  { id: "uwJev", label: "Jev", sub: "Names queue", kind: "jev", x: 482, y: 78, decides: "Jev may answer only: incomplete, engineering specialist, manual review, or standard.", detail: "The label is a work queue. The graph then splits on whether evidence is actually missing." },
  { id: "uwAsk", label: "Ask files", sub: "If missing", kind: "record", x: 616, y: 46, decides: "This branch runs when required evidence is absent.", detail: "The submission waits as needs info. No terms are issued." },
  { id: "premium", label: "Premium", sub: "If complete", kind: "rules", x: 616, y: 110, decides: "Rules draft an illustrative premium from value and risk score.", detail: "This is not a quote and not a bound policy." },
  { id: "uwHuman", label: "Reviewer", sub: "Person", kind: "human", x: 750, y: 78, decides: "Only an underwriter or supervisor can approve demo terms.", detail: "Both branches stop here. A model cannot bind coverage." },

  { id: "match", label: "Site match", sub: "GIS rules", kind: "rules", x: 214, y: 198, decides: "Rules decide which sites meet the footprint or radius.", detail: "No model chooses the match. Declared value here is exposure, not damage." },
  { id: "hzTask", label: "Draft task", sub: "No claim", kind: "record", x: 400, y: 198, decides: "The graph drafts a review task and does not contact anyone.", detail: "A weather match never creates a claim." },
  { id: "hzHuman", label: "Reviewer", sub: "Person", kind: "human", x: 586, y: 198, decides: "A person accepts the exposure review.", detail: "Jev is not in this workflow." },

  { id: "gemini", label: "Gemini", sub: "Proposes", kind: "ai", x: 214, y: 328, decides: "Gemini proposes observations on authorized images, frames, and plans.", detail: "It does not choose the queue or the dollar amount." },
  { id: "spatial", label: "Intersect", sub: "Plan rules", kind: "rules", x: 214, y: 436, decides: "Rules list objects whose boxes meet the drawn region.", detail: "The result is possibly affected, not confirmed damaged." },
  { id: "reconcile", label: "Reconcile", sub: "Policy rules", kind: "rules", x: 348, y: 384, decides: "Rules compare the policy, dates, and contradictions.", detail: "The Factory A file has a maintenance-date conflict. Coverage is not decided here." },
  { id: "clmJev", label: "Jev", sub: "Names queue", kind: "jev", x: 482, y: 384, decides: "Jev may answer only: needs information, equipment specialist, business-income specialist, or standard adjuster.", detail: "The graph follows that label into one of three branches. Jev cannot deny the claim or set a payment." },
  { id: "quote", label: "Ask quote", sub: "If missing", kind: "record", x: 616, y: 328, decides: "A missing repair quote stops the case.", detail: "Uploading a quote resumes only this claim and keeps the previous estimate." },
  { id: "specialist", label: "Specialist", sub: "Referral", kind: "human", x: 616, y: 384, decides: "Equipment or business-income is a referral, not a coverage answer.", detail: "A person still has to act." },
  { id: "estimate", label: "Estimate", sub: "Rules math", kind: "rules", x: 616, y: 440, decides: "Rules set gross loss from a quote sum, or the median of synthetic history.", detail: "Deductible and limit are applied in the open. Payment fields stay empty." },
  { id: "clmHuman", label: "Reviewer", sub: "Person", kind: "human", x: 750, y: 384, decides: "A claims reviewer can review the reserve or record a simulated settlement.", detail: "Neither action moves money." },

  { id: "terms", label: "Terms", sub: "Not binding", kind: "record", x: 900, y: 78, decides: "The authorized demo outcome is stored apart from the recommendation.", detail: "Approving terms in this demo does not bind a policy." },
  { id: "exposure", label: "Exposure", sub: "Not a loss", kind: "record", x: 900, y: 198, decides: "The matched sites and declared values are recorded.", detail: "The audit states that zero claims were created." },
  { id: "audit", label: "Audit", sub: "Full record", kind: "record", x: 900, y: 384, decides: "Every branch, provider, and estimate version stays searchable.", detail: "The human outcome is stored separately from the model recommendation." },
];

const nodeById = Object.fromEntries(nodes.map((node) => [node.id, node])) as Record<NodeId, NodeDef>;

const groups: Array<{ title: string; color: string; ids: NodeId[] }> = [
  { title: "Underwriting review", color: "#60a5fa", ids: ["groq", "cope", "uwJev", "uwAsk", "premium", "uwHuman"] },
  { title: "Hazard exposure", color: "#2dd4bf", ids: ["match", "hzTask", "hzHuman"] },
  { title: "Claims investigation", color: "#fbbf24", ids: ["reconcile", "clmJev", "quote", "specialist", "estimate", "gemini", "spatial", "clmHuman"] },
];

const flows: Array<{ from: NodeId; to: NodeId; width: number }> = [
  { from: "accounts", to: "cope", width: 8 },
  { from: "documents", to: "groq", width: 7 },
  { from: "groq", to: "cope", width: 6 },
  { from: "cope", to: "uwJev", width: 8 },
  { from: "uwJev", to: "uwAsk", width: 6 },
  { from: "uwJev", to: "premium", width: 6 },
  { from: "uwAsk", to: "uwHuman", width: 6 },
  { from: "premium", to: "uwHuman", width: 6 },
  { from: "uwHuman", to: "terms", width: 7 },
  { from: "alerts", to: "match", width: 8 },
  { from: "match", to: "hzTask", width: 7 },
  { from: "hzTask", to: "hzHuman", width: 7 },
  { from: "hzHuman", to: "exposure", width: 7 },
  { from: "fnol", to: "reconcile", width: 8 },
  { from: "documents", to: "reconcile", width: 5 },
  { from: "photos", to: "gemini", width: 6 },
  { from: "plans", to: "gemini", width: 5 },
  { from: "plans", to: "spatial", width: 6 },
  { from: "gemini", to: "reconcile", width: 5 },
  { from: "spatial", to: "reconcile", width: 5 },
  { from: "reconcile", to: "clmJev", width: 8 },
  { from: "clmJev", to: "quote", width: 5 },
  { from: "clmJev", to: "specialist", width: 5 },
  { from: "clmJev", to: "estimate", width: 6 },
  { from: "quote", to: "clmHuman", width: 5 },
  { from: "specialist", to: "clmHuman", width: 5 },
  { from: "estimate", to: "clmHuman", width: 6 },
  { from: "clmHuman", to: "audit", width: 7 },
];

function pathFor(from: NodeId, to: NodeId) {
  const a = nodeById[from];
  const b = nodeById[to];
  const x1 = a.x + W;
  const y1 = a.y + H / 2;
  const x2 = b.x;
  const y2 = b.y + H / 2;
  const crossesBands = a.x < 150 && Math.abs(y1 - y2) > 70;
  if (crossesBands) {
    const gutter = 168;
    return `M ${x1} ${y1} C ${gutter} ${y1}, ${gutter} ${y2}, ${x2} ${y2}`;
  }
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

function frameFor(ids: NodeId[]) {
  const members = ids.map((id) => nodeById[id]);
  const x = Math.min(...members.map((node) => node.x)) - 16;
  const y = Math.min(...members.map((node) => node.y)) - 18;
  const right = Math.max(...members.map((node) => node.x + W)) + 16;
  const bottom = Math.max(...members.map((node) => node.y + H)) + 14;
  return { x, y, w: right - x, h: bottom - y };
}

export function WorkflowSankey() {
  const [active, setActive] = useState<NodeId>("clmJev");
  const selected = nodeById[active];
  const style = kindStyle[selected.kind];
  const SelectedIcon = style.icon;
  const connected = useMemo(() => new Set(flows.filter((flow) => flow.from === active || flow.to === active).map((flow) => `${flow.from}-${flow.to}`)), [active]);
  const frames = groups.map((group) => ({ ...group, ...frameFor(group.ids) }));
  return <Card className="overflow-hidden">
    <CardHeader className="flex flex-row items-start justify-between gap-4">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[.15em] text-blue-300">Insurance workflow</div>
        <h2 className="mt-1 text-base font-semibold text-slate-100">From source evidence to authorized outcome</h2>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">Inputs feed the three workflows. Each box is one real step. Select it to see what that step is allowed to decide.</p>
      </div>
      <Link href="/audit" className="inline-flex shrink-0 items-center gap-1.5 text-xs font-semibold text-blue-300 hover:text-blue-200">Workflow results <ArrowUpRight size={13} /></Link>
    </CardHeader>
    <CardContent className="p-0">
      <div className="overflow-x-auto px-3 pb-2 pt-3">
        <svg viewBox="0 0 1024 510" role="img" aria-label="Inputs flowing through underwriting, hazard, and claims into written outcomes" className="min-w-[960px]">
          <text x={16} y={28} fill="#8b97a8" fontSize="10" fontWeight="700" letterSpacing="1.2">INPUT</text>
          <text x={900} y={28} fill="#8b97a8" fontSize="10" fontWeight="700" letterSpacing="1.2">OUTPUT</text>
          {frames.map((frame) => <rect key={frame.title} x={frame.x} y={frame.y} width={frame.w} height={frame.h} rx="12" fill="#ffffff" fillOpacity="0.015" stroke={frame.color} strokeOpacity="0.4" />)}
          {flows.map((flow) => {
            const hot = connected.has(`${flow.from}-${flow.to}`);
            const color = kindStyle[nodeById[flow.from].kind].color;
            return <path key={`${flow.from}-${flow.to}`} d={pathFor(flow.from, flow.to)} fill="none" stroke={color} strokeOpacity={hot ? 0.85 : 0.22} strokeWidth={flow.width} strokeLinecap="round"><title>{nodeById[flow.from].label} to {nodeById[flow.to].label}</title></path>;
          })}
          {nodes.map((node) => {
            const on = node.id === active;
            const color = kindStyle[node.kind].color;
            return <g key={node.id} tabIndex={0} role="button" aria-label={`${node.label}. ${node.decides}`} onMouseEnter={() => setActive(node.id)} onFocus={() => setActive(node.id)} onClick={() => setActive(node.id)} className="cursor-pointer outline-none">
              <rect x={node.x} y={node.y} width={W} height={H} rx="8" fill={on ? `${color}26` : "#1b222b"} stroke={color} strokeOpacity={on ? 1 : 0.4} strokeWidth={on ? 2 : 1} />
              <text x={node.x + 8} y={node.y + 15} fill="#edf1f6" fontSize="10.5" fontWeight="700">{node.label}</text>
              <text x={node.x + 8} y={node.y + 28} fill={color} fontSize="8">{node.sub}</text>
            </g>;
          })}
          {frames.map((frame) => {
            const chipWidth = frame.title.length * 6.6 + 16;
            return <g key={`${frame.title}-label`}>
              <rect x={frame.x + 14} y={frame.y - 8} width={chipWidth} height={16} rx="4" fill="#1b1b1b" />
              <text x={frame.x + 22} y={frame.y + 4} fill={frame.color} fontSize="10" fontWeight="700">{frame.title}</text>
            </g>;
          })}
        </svg>
      </div>
      <div className="grid gap-4 border-t border-white/[.07] bg-black/[.1] p-4 sm:grid-cols-[auto_1fr] sm:items-center">
        <div className="grid size-10 place-items-center rounded-lg border" style={{ color: style.color, borderColor: `${style.color}44`, background: `${style.color}14` }}><SelectedIcon size={18} /></div>
        <div>
          <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold text-slate-100">{selected.label}</span><span className="text-[10px] font-semibold uppercase tracking-[.12em]" style={{ color: style.color }}>{style.tech}</span></div>
          <p className="mt-1 text-[12px] font-medium leading-5 text-slate-200">{selected.decides}</p>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-slate-500">{selected.detail}</p>
        </div>
      </div>
    </CardContent>
  </Card>;
}
