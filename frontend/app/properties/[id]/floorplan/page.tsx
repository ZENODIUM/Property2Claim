"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { FileImage, Images, Plus, Upload, X } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { FloorplanEditor, type FloorPlan } from "@/components/floorplan-editor";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";

type PlanSummary = { id: number; name: string; plan_type: string; is_base: boolean; state: string; analysis_status: string; preview_url: string };
type PropertyPlan = { id: number; name: string; site_code: string; floorplans: PlanSummary[] };
type PendingPlan = { file: File; role: "base" | "machinery" | "emergency" | "reference"; name: string; preview: string };

function PlanLoader({ id }: { id: number }) {
  const { data, loading, error } = useApi<FloorPlan>(`/floorplans/${id}`);
  if (loading) return <LoadingState label="Loading original drawings and saved overlays…" />;
  if (error || !data) return <ErrorState message={error ?? "No plan"} />;
  return <FloorplanEditor initialPlan={data} />;
}

function UploadPanel({ propertyId, onUploaded, compact = false }: { propertyId: string; onUploaded: (id: number) => void; compact?: boolean }) {
  const [plans, setPlans] = useState<PendingPlan[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => () => plans.forEach((plan) => URL.revokeObjectURL(plan.preview)), [plans]);

  function choose(files: FileList | null) {
    if (!files?.length) return;
    plans.forEach((plan) => URL.revokeObjectURL(plan.preview));
    const next = Array.from(files).slice(0, 8).map((file, index) => ({
      file,
      role: (index === 0 ? "base" : index === 1 ? "machinery" : index === 2 ? "emergency" : "reference") as PendingPlan["role"],
      name: index === 0 ? "General arrangement" : index === 1 ? "Machinery and equipment" : index === 2 ? "Emergency and fire safety" : file.name.replace(/\.[^.]+$/, ""),
      preview: URL.createObjectURL(file),
    }));
    setPlans(next);
  }

  function update(index: number, patch: Partial<PendingPlan>) {
    setPlans((items) => items.map((item, itemIndex) => {
      if (patch.role === "base" && itemIndex !== index && item.role === "base") return { ...item, role: "reference" };
      return itemIndex === index ? { ...item, ...patch } : item;
    }));
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!plans.length || plans.filter((plan) => plan.role === "base").length !== 1) {
      setError("Choose exactly one base drawing.");
      return;
    }
    setUploading(true);
    setError(undefined);
    try {
      const form = new FormData();
      form.append("floor_name", "Ground Floor");
      form.append("plan_types", JSON.stringify(plans.map((plan) => plan.role)));
      form.append("plan_names", JSON.stringify(plans.map((plan) => plan.name)));
      plans.forEach((plan) => form.append("files", plan.file));
      const result = await api<{ base_plan_id: number }>(`/properties/${propertyId}/floorplans/batch`, { method: "POST", body: form });
      onUploaded(result.base_plan_id);
      setPlans([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally { setUploading(false); }
  }

  return <Card className={compact ? "bg-[#202833]" : "mx-auto max-w-4xl border-dashed"}><CardContent className={compact ? "p-4" : "py-10"}>
    <div className={`flex gap-4 ${compact ? "items-center" : "flex-col items-center text-center"}`}>
      <div className="grid size-11 shrink-0 place-items-center rounded-lg border border-white/10 bg-black/10 text-blue-300"><Images size={20} /></div>
      <div className={compact ? "flex-1" : ""}><h2 className="text-sm font-semibold">Upload a coordinated plan set</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">Preview every drawing first, assign one general layout as the base, then add machinery, emergency, or reference sheets. Originals are retained unchanged.</p></div>
      <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-blue-500 px-3 text-xs font-semibold text-white hover:bg-blue-400"><Plus size={14} />Choose drawings<input className="hidden" type="file" multiple accept=".png,.jpg,.jpeg,.pdf" onChange={(event) => choose(event.target.files)} /></label>
    </div>
    {plans.length > 0 && <form onSubmit={upload} className="mt-5 border-t border-white/[.07] pt-5"><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{plans.map((plan, index) => <div key={plan.preview} className="overflow-hidden rounded-md border border-white/[.09] bg-black/10"><div className="relative h-36 bg-white"><img src={plan.preview} alt={`Preview of ${plan.file.name}`} className="h-full w-full object-contain" /><button type="button" onClick={() => setPlans((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="absolute right-2 top-2 grid size-7 place-items-center rounded bg-slate-950/80 text-slate-300"><X size={13} /></button></div><div className="space-y-2 p-3"><input aria-label="Plan name" className="input" value={plan.name} onChange={(event) => update(index, { name: event.target.value })} /><select aria-label="Plan role" className="input" value={plan.role} onChange={(event) => update(index, { role: event.target.value as PendingPlan["role"] })}><option value="base">Base / general layout</option><option value="machinery">Machinery layout</option><option value="emergency">Emergency / fire safety</option><option value="reference">Other reference</option></select><div className="truncate text-[10px] text-slate-600">{plan.file.name}</div></div></div>)}</div>{error && <div className="mt-3 rounded-md border border-rose-400/20 bg-rose-400/[.07] p-3 text-xs text-rose-200">{error}</div>}<div className="mt-4 flex items-center justify-between gap-4"><p className="text-[10px] leading-4 text-slate-500">Gemini analysis is a separate, explicit action after upload. Its result is saved and requires human verification.</p><Button type="submit" disabled={uploading}><Upload size={14} />{uploading ? "Uploading…" : `Upload ${plans.length} drawing${plans.length === 1 ? "" : "s"}`}</Button></div></form>}
  </CardContent></Card>;
}

export default function FloorplanPage() {
  const propertyId = useParams<{ id: string }>().id;
  const property = useApi<PropertyPlan>(`/properties/${propertyId}`);
  const [newPlan, setNewPlan] = useState<number>();
  const [showUpload, setShowUpload] = useState(false);
  const basePlan = useMemo(() => property.data?.floorplans.find((plan) => plan.is_base) ?? property.data?.floorplans.at(-1), [property.data]);
  const planId = newPlan ?? basePlan?.id;
  if (property.loading) return <LoadingState />;
  if (property.error || !property.data) return <ErrorState message={property.error ?? "No property"} />;
  return <>
    <PageHeader eyebrow={`${property.data.name} · spatial intelligence`} title="Factory floor-plan workspace" description="The original 2D drawing remains the source layer. Saved AI proposals, manual annotations, evidence, and incident regions stay separate from underwriting and claim decisions." actions={planId ? <Button variant="secondary" onClick={() => setShowUpload((value) => !value)}><FileImage size={15} />Upload plan set</Button> : undefined} />
    {planId ? <div className="space-y-4">{showUpload && <UploadPanel compact propertyId={propertyId} onUploaded={(id) => { setNewPlan(id); setShowUpload(false); property.refresh(); }} />}<PlanLoader id={planId} /></div> : <UploadPanel propertyId={propertyId} onUploaded={(id) => { setNewPlan(id); property.refresh(); }} />}
  </>;
}
