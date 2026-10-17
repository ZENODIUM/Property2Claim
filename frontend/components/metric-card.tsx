import { Card } from "@/components/ui/card";

export function MetricCard({ label, value, note, accent = false }: { label: string; value: string | number; note: string; accent?: boolean }) {
  return <Card className={accent ? "border-blue-400/25 bg-[#202a38]" : ""}><div className="p-5"><div className="text-[10px] font-bold uppercase tracking-[.12em] text-slate-500">{label}</div><div className="mt-3 text-3xl font-semibold tracking-tight text-slate-100">{value}</div><div className="mt-2 text-xs text-slate-500">{note}</div></div></Card>;
}
