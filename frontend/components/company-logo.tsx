import Image from "next/image";
import { cn } from "@/lib/utils";

const marks: Record<string, string> = {
  "NorthStar Manufacturing": "/brand/northstar.svg",
  "Harborline Logistics": "/brand/harborline.svg",
  "Redwood Components": "/brand/redwood.svg",
  "Beacon Retail Group": "/brand/beacon.svg",
  "Meridian Food Systems": "/brand/meridian.svg",
  "LoomWorks Textiles": "/brand/loomworks.svg",
  "Apex Precision Systems": "/brand/apex.svg",
  "Cobalt Distribution": "/brand/cobalt.svg",
};

export function CompanyLogo({ name, className }: { name: string; className?: string }) {
  return <span className={cn("company-logo", className)}><Image src={marks[name] ?? "/brand/property2claim.svg"} alt={`${name} logo`} width={52} height={52} /></span>;
}
