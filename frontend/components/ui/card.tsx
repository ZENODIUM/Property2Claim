import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("min-w-0 rounded-[1.15rem] border border-white/[.085] bg-[linear-gradient(145deg,rgba(28,29,28,.98),rgba(20,21,20,.98))] shadow-[inset_0_1px_rgba(255,255,255,.025),0_16px_46px_rgba(0,0,0,.16)] transition-[border-color,box-shadow,transform] duration-200 hover:border-teal-200/[.16] hover:shadow-[inset_0_1px_rgba(255,255,255,.035),0_20px_54px_rgba(0,0,0,.22),0_0_40px_rgba(69,208,157,.025)]", className)} {...props} />; }
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("border-b border-white/[.07] px-5 py-4", className)} {...props} />; }
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("min-w-0 p-5", className)} {...props} />; }
