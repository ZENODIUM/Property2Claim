import { cn } from "@/lib/utils";

export function StatusPill({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "teal" | "amber" | "rose" | "blue" }) {
  const tones = { slate: "bg-slate-400/10 text-slate-300 ring-slate-400/20", teal: "bg-teal-400/10 text-teal-300 ring-teal-400/20", amber: "bg-amber-400/10 text-amber-300 ring-amber-400/20", rose: "bg-rose-400/10 text-rose-300 ring-rose-400/20", blue: "bg-blue-400/10 text-blue-300 ring-blue-400/20" };
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[.08em] ring-1 ring-inset shadow-[inset_0_1px_rgba(255,255,255,.025)]", tones[tone])}>{children}</span>;
}
