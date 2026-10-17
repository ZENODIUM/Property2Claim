import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva("inline-flex items-center justify-center gap-2 rounded-full border text-sm font-semibold transition duration-200 hover:-translate-y-px disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-300/40", {
  variants: {
    variant: { default: "border-teal-200/25 bg-[linear-gradient(180deg,#7ae5bd,#52c99f)] text-[#10201b] shadow-[inset_0_1px_rgba(255,255,255,.35),0_8px_24px_rgba(55,198,145,.12)] hover:shadow-[inset_0_1px_rgba(255,255,255,.4),0_10px_30px_rgba(55,198,145,.22)]", secondary: "border-white/12 bg-white/[.045] text-slate-200 shadow-[inset_0_1px_rgba(255,255,255,.035)] hover:border-teal-200/25 hover:bg-teal-300/[.055]", danger: "border-rose-300/25 bg-rose-500/85 text-white shadow-[0_8px_24px_rgba(244,63,94,.12)] hover:bg-rose-500", ghost: "border-transparent text-slate-400 hover:bg-white/[.05] hover:text-slate-100" },
    size: { default: "h-10 px-4", sm: "h-8 px-3 text-xs", lg: "h-12 px-5" },
  },
  defaultVariants: { variant: "default", size: "default" },
});

export function Button({ className, variant, size, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
