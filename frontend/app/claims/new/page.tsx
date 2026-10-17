"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Property } from "@/lib/types";

type Policy = { id:number; property_id:number; policy_number:string };

export default function NewClaimPage() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [propertyId, setPropertyId] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    void api<{items:Property[]}>("/properties").then((result) => { setProperties(result.items); setPropertyId(result.items[0]?.id ?? 1); });
    void api<{items:Policy[]}>("/policies").then((result) => setPolicies(result.items));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const property = properties.find((item) => item.id === propertyId);
    const policy = policies.find((item) => item.property_id === propertyId);
    if (!property || !policy) return setError("No active policy record is available for this property.");
    try {
      const claim = await api<{id:number}>("/claims/fnol", { method:"POST", body:JSON.stringify({ company_id:property.company_id, property_id:property.id, policy_id:policy.id, loss_at:new Date(String(form.get("loss_at"))).toISOString(), peril:form.get("peril"), narrative:form.get("narrative"), reported_exposures:["building","equipment","business_income"] }) });
      router.push(`/claims/${claim.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create FNOL"); }
  }

  return <><PageHeader eyebrow="First notice of loss" title="Report an incident" description="An authorized report creates a claim. Hazard proximity alone never does."/>
    <Card className="max-w-3xl surface-rose"><CardContent><form onSubmit={submit} className="grid gap-5 sm:grid-cols-2">
      <div className="sm:col-span-2"><label className="label">Property</label><select className="input" value={propertyId} onChange={(event) => setPropertyId(Number(event.target.value))}>{properties.map((property) => <option value={property.id} key={property.id}>{property.name} — {property.city}, {property.region}</option>)}</select></div>
      <div><label className="label">Loss date and time</label><input className="input" name="loss_at" type="datetime-local" required defaultValue="2026-10-16T09:30"/></div>
      <div><label className="label">Reported peril</label><select className="input" name="peril"><option value="water">Water</option><option value="fire">Fire</option><option value="wind">Wind</option><option value="hail">Hail</option><option value="theft">Theft</option><option value="other">Other</option></select></div>
      <div className="sm:col-span-2"><label className="label">Incident narrative</label><textarea className="input" name="narrative" required minLength={12} defaultValue="Water release reported near the production line; equipment condition and repair scope require inspection."/></div>
      {error && <div className="sm:col-span-2 rounded-2xl bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}
      <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-4 border-t border-white/[.07] pt-5"><p className="max-w-md text-xs leading-5 text-slate-500">Creates a reported incident and evidence-review workflow. This does not make a coverage conclusion or authorize payment.</p><Button type="submit">Create FNOL</Button></div>
    </form></CardContent></Card>
  </>;
}
