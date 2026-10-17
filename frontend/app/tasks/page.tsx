"use client";

import { useState } from "react";
import { CheckCircle2, UserCheck } from "lucide-react";
import { ErrorState } from "@/components/error-state";
import { LoadingState } from "@/components/loading-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const actionsFor = (task:Task) => {
  if (task.subject_type === "underwriting" && task.kind === "underwriter_review") return ["approve_demo_terms", "request_evidence", "assign_specialist"];
  if (["claim", "claims"].includes(task.subject_type) && task.kind === "estimate_review") return ["approve_reserve_review", "authorize_settlement_simulation", "close_demo"];
  if (["claim", "claims"].includes(task.subject_type)) return ["approve_request", "assign_specialist", "request_evidence"];
  return ["approve_request", "assign_specialist"];
};

export default function TasksPage() {
  const {data,loading,error,refresh}=useApi<{items:Task[]}>("/tasks");
  const [message,setMessage]=useState("");
  const [choices,setChoices]=useState<Record<number,string>>({});
  const [busy,setBusy]=useState<number>();
  async function decide(task:Task) {
    const action=choices[task.id] ?? actionsFor(task)[0];
    setBusy(task.id); setMessage("");
    try {
      await api(`/tasks/${task.id}/decision`,{method:"POST",body:JSON.stringify({actor:"Demo Reviewer",actor_role:task.required_role === "underwriter" ? "underwriter" : "claims_reviewer",action,rationale:"Reviewed the source evidence and authorized this synthetic workflow action."})});
      setMessage(`Task #${task.id}: ${action.replaceAll("_"," ")} recorded with human provenance.`); await refresh();
    } finally { setBusy(undefined); }
  }
  if(loading)return <LoadingState/>;
  if(error||!data)return <ErrorState message={error??"No data"}/>;
  return <><PageHeader eyebrow="Human approval queue" title="Agent tasks and checkpoints" description="Agents assemble and recommend. Role-gated humans choose the action, provide rationale, and create the authorized audit record."/>
    {message&&<div className="mb-5 rounded-lg border border-teal-300/20 bg-teal-300/[.08] p-3 text-sm text-teal-200">{message}</div>}
    <div className="space-y-3">{data.items.map(task => {
      const actions=actionsFor(task); const active=["queued","waiting"].includes(task.status);
      return <Card key={task.id} className={active?"border-amber-300/20":""}><CardContent className="flex flex-wrap items-center gap-4"><div className={`grid size-10 place-items-center rounded-lg ${active?"bg-amber-300/10 text-amber-300":"bg-teal-300/10 text-teal-300"}`}>{active?<UserCheck size={18}/>:<CheckCircle2 size={18}/>}</div><div className="min-w-[250px] flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="text-sm font-semibold text-slate-100">{task.title}</h2><StatusPill tone={task.priority==="high"?"amber":"slate"}>{task.priority}</StatusPill><StatusPill tone={active?"amber":"teal"}>{task.status}</StatusPill></div><div className="mt-1 text-xs text-slate-500">{task.subject_type} #{task.subject_id} · role: {task.required_role.replaceAll("_"," ")} · {formatDate(task.created_at)}</div></div>{active&&<div className="flex gap-2"><select aria-label={`Action for task ${task.id}`} value={choices[task.id] ?? actions[0]} onChange={event=>setChoices(current=>({...current,[task.id]:event.target.value}))} className="rounded-md border border-white/10 bg-[#1b1f24] px-3 text-xs text-slate-200 outline-none focus:border-blue-300/40">{actions.map(action=><option key={action} value={action}>{action.replaceAll("_"," ")}</option>)}</select><Button size="sm" disabled={busy===task.id} onClick={()=>decide(task)}>{busy===task.id?"Recording…":"Review & authorize"}</Button></div>}</CardContent></Card>;
    })}</div>
  </>;
}
