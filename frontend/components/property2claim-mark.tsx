import Image from "next/image";
import { cn } from "@/lib/utils";

export function Property2ClaimMark({ compact = false, className }: { compact?: boolean; className?: string }) {
  return <span className={cn("brand-mark", compact ? "size-8" : "size-10", className)}>
    <Image src="/brand/property2claim.svg" alt="Property2Claim" width={compact ? 32 : 40} height={compact ? 32 : 40} priority />
  </span>;
}
