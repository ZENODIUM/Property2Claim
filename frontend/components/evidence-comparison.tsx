"use client";

import Link from "next/link";
import Image from "next/image";
import { FileSearch } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { StatusPill } from "@/components/status-pill";
import { API_URL } from "@/lib/api";
import type { EvidenceDocument } from "@/lib/types";

export function EvidenceComparison({ documents, narrative }: { documents: EvidenceDocument[]; narrative: string }) {
  const base = API_URL.replace(/\/api$/, "");
  const before = documents.find((document) => document.classification === "condition_before") ?? documents.find((document) => document.classification === "inspection_report");
  const after = documents.find((document) => document.classification === "condition_after") ?? documents.find((document) => document.claim_id && document.media_type.startsWith("image/") && document.id !== before?.id);
  const pairedScenario = before?.classification === "condition_before" && after?.classification === "condition_after";
  return <Card>
    <CardHeader>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Before and after</h2>
          <p className="mt-1 text-xs text-slate-500">Paired machine condition media beside the reported incident context. Human verification is still required.</p>
        </div>
        <StatusPill tone="amber">Not a damage determination</StatusPill>
      </div>
    </CardHeader>
    <CardContent>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-white/[.08]">
          <div className="flex items-center justify-between border-b border-white/[.07] px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400"><span>Before incident</span><span>{pairedScenario ? "Paired source image" : before ? "Inspection record" : "Reference condition"}</span></div>
          <div className="grid h-52 place-items-center bg-black/25">
            {before ? <img src={`${base}/api/documents/${before.id}/preview?page=1`} alt={`Preview of ${before.filename}`} className="h-full w-full object-contain" /> : <Image src="/incident-media/baseline-inspection.jpg" alt="Reference photograph of machinery inspection" width={700} height={470} className="h-full w-full object-cover" />}
          </div>
          <div className="px-3 py-3 text-xs text-slate-400">{before ? <Link href={`/evidence/${before.id}`} className="inline-flex items-center gap-2 font-semibold text-blue-300 hover:text-blue-200"><FileSearch size={13} />{before.filename}</Link> : "Machinery-inspection reference · not linked claim evidence"}</div>
        </div>
        <div className="overflow-hidden rounded-lg border border-white/[.08]">
          <div className="flex items-center justify-between border-b border-white/[.07] px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400"><span>Reported afterward</span><span>{pairedScenario ? "Paired source image" : after ? "Submitted image" : "Incident reference"}</span></div>
          <div className="grid h-52 place-items-center bg-black/25">
            {after ? <img src={`${base}/api/documents/${after.id}/preview?page=1`} alt={`Submitted image ${after.filename}`} className="h-full w-full object-contain" /> : <Image src="/incident-media/flood-condition.jpg" alt="Reference photograph of a flooded industrial interior" width={700} height={470} className="h-full w-full object-cover" />}
          </div>
          <div className="px-3 py-3 text-xs leading-5 text-slate-400">{after ? <Link href={`/evidence/${after.id}`} className="font-semibold text-blue-300 hover:text-blue-200">{after.filename}</Link> : "Flood-condition reference · replace with submitted site media"}</div>
        </div>
      </div>
      <p className="mt-4 text-[11px] leading-5 text-slate-500">{pairedScenario ? "User-supplied scenario pair retained as source media. No vision finding has been asserted; a reviewer must verify condition, sequence, cause, and claim relevance." : after ? `Analysis status: ${after.analysis_status.replaceAll("_", " ")}. Observations are proposals until a reviewer verifies them.` : `Representative comparison imagery is shown because no claim photograph is attached. Reported narrative: ${narrative}`}</p>
    </CardContent>
  </Card>;
}
