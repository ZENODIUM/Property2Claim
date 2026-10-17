import type { Metadata } from "next";
import "./globals.css";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export const metadata: Metadata = { title: "Property2Claim — Commercial Property Intelligence", description: "Commercial property intelligence and claims operations" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Sidebar /><div className="min-h-screen lg:pl-64"><Topbar /><main className="mx-auto w-full max-w-[1920px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main></div></body></html>;
}
