import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.PROPERTY2CLAIM_URL ?? "http://localhost:3000";
const apiUrl = process.env.PROPERTY2CLAIM_API_URL ?? "http://localhost:8000/api";
const executablePath = process.env.BROWSER_PATH ?? "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputDir = path.resolve("..", "docs", "screenshots");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ executablePath, headless: true, args: ["--use-angle=swiftshader", "--enable-webgl", "--disable-gpu-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1800, height: 1100 }, deviceScaleFactor: 1 });
const consoleErrors = [];
const failedResponses = [];
page.on("console", (message) => {
  if (message.type() === "error") {
    const location = message.location();
    consoleErrors.push(`${message.text()}${location.url ? ` (${location.url}:${location.lineNumber ?? 0})` : ""}`);
  }
});
page.on("pageerror", (error) => consoleErrors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
});

const checks = [
  { path: "/", marker: "Property intelligence. Evidence-driven insurance.", shot: "overview.png" },
  { path: "/demo", marker: "One lifecycle, every handoff visible", shot: "guided-demo.png" },
  { path: "/onboarding", marker: "From source files to a review-ready property record", shot: "onboarding.png" },
  { path: "/companies", marker: "Companies & properties", shot: "companies.png" },
  { path: "/claims", marker: "Evidence-led claim investigation", shot: "claims.png" },
  { path: "/underwriting", marker: "Evidence before judgment", shot: "underwriting.png" },
  { path: "/audit", marker: "Every route, source and authorized outcome", shot: "workflow-results.png" },
  { path: "/claims/1", marker: "Multimodal evidence", shot: "claim-evidence.png" },
  { path: "/evidence/1", marker: "Original evidence", shot: "evidence-viewer.png" },
  { path: "/portfolio", marker: "Portfolio map", shot: "portfolio.png" },
  { path: "/hazards", marker: "Industrial exposure across time", shot: "hazard-intelligence.png" },
  { path: "/properties/1/floorplan", marker: "Factory floor-plan workspace", shot: "floorplan.png" },
  { path: "/properties/11/floorplan", marker: "Factory floor-plan workspace", shot: "meridian-floorplan.png" },
];

const results = [];
for (const check of checks) {
  await page.goto(`${baseUrl}${check.path}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  try {
    await page.locator("main").getByText(check.marker, { exact: false }).first().waitFor({ state: "visible", timeout: 20_000 });
  } catch (error) {
    await page.screenshot({ path: path.join(outputDir, `failed-${check.shot}`), fullPage: true });
    const body = (await page.locator("body").innerText()).slice(0, 1500);
    throw new Error(`${check.path} did not show marker '${check.marker}'. Body:\n${body}\nConsole:\n${consoleErrors.join("\n")}`, { cause: error });
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 2) throw new Error(`${check.path} has ${overflow}px horizontal overflow`);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outputDir, check.shot), fullPage: true });
  results.push({ path: check.path, marker: check.marker, horizontalOverflow: overflow });
}

await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 45_000 });
await page.getByText("Declared exposure by site", { exact: true }).waitFor({ state: "visible" });
await page.getByText("Risk × declared value", { exact: true }).waitFor({ state: "visible" });
await page.getByText("Portfolio radar", { exact: true }).waitFor({ state: "visible" });
const exposureBars = page.locator('[aria-label="Interactive declared exposure bar chart"] button');
const matrixBubbles = page.locator('svg[aria-label="Risk and declared value matrix"] g[role="button"]');
if (await exposureBars.count() !== 10) throw new Error("Overview exposure ranking did not render ten site bars");
if (await matrixBubbles.count() !== 19) throw new Error("Overview risk matrix did not render all nineteen sites");
await exposureBars.nth(1).focus();
const focusedSite = (await exposureBars.nth(1).getAttribute("aria-label"))?.split(",")[0];
if (!focusedSite) throw new Error("Focused exposure bar had no site label");
await page.getByText(focusedSite, { exact: true }).last().waitFor({ state: "visible" });
const inspectPropertyHref = await page.getByRole("link", { name: "Inspect property" }).getAttribute("href");
if (!inspectPropertyHref?.startsWith("/properties/")) throw new Error("Skyline selection did not expose a property drill-down");
results.push({ path: "/", exposureBars: 10, riskMatrixSites: 19, keyboardInteraction: true, propertyDrilldown: true });

await page.goto(`${baseUrl}/audit`, { waitUntil: "domcontentloaded", timeout: 45_000 });
await page.getByRole("button", { name: /Source evidence/ }).click();
const evidencePreview = page.locator('img[alt^="Preview of"]').first();
await evidencePreview.waitFor({ state: "visible", timeout: 20_000 });
results.push({ path: "/audit", sourceEvidenceTab: true, previewRendered: true });

await page.goto(`${baseUrl}/underwriting`, { waitUntil: "domcontentloaded", timeout: 45_000 });
await page.getByRole("button", { name: "Rules & comparisons" }).click();
await page.getByText("Control family", { exact: true }).waitFor({ state: "visible" });
await page.getByRole("button", { name: "Policy & supporting data" }).click();
await page.getByText("Human authority", { exact: true }).waitFor({ state: "visible" });
results.push({ path: "/underwriting", rulesTab: true, supportingDataTab: true });

const claimResponse = await fetch(`${apiUrl}/claims`);
if (!claimResponse.ok) throw new Error(`Claim API returned ${claimResponse.status}`);
const claimItems = (await claimResponse.json()).items;
const pairedNumbers = ["AR-CLM-1001", "PC-CLM-2001", "PC-CLM-2002", "PC-CLM-2003", "PC-CLM-2004"];
for (const claimNumber of pairedNumbers) {
  const claim = claimItems.find((item) => item.claim_number === claimNumber);
  if (!claim?.has_condition_pair) throw new Error(`${claimNumber} has no paired condition media`);
  await page.goto(`${baseUrl}/claims/${claim.id}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await page.getByText("Paired source image", { exact: true }).first().waitFor({ state: "visible", timeout: 20_000 });
  if (await page.getByText("Paired source image", { exact: true }).count() !== 2) throw new Error(`${claimNumber} did not render both condition images`);
}
await page.screenshot({ path: path.join(outputDir, "machine-claim-evidence.png"), fullPage: true });
results.push({ path: "/claims/[id]", pairedMachineClaims: pairedNumbers.length, renderedConditionImages: pairedNumbers.length * 2 });

await page.goto(`${baseUrl}/properties/1/floorplan`, { waitUntil: "domcontentloaded", timeout: 45_000 });
await page.getByText("71 visible objects", { exact: false }).waitFor({ state: "visible", timeout: 20_000 });
await page.getByText("Machinery and equipment", { exact: true }).first().click();
await page.getByText("machinery · complete", { exact: false }).first().waitFor({ state: "visible" });
const canvasCount = await page.locator("canvas").count();
if (canvasCount < 1) throw new Error("Floor-plan canvas did not render");
results.push({ path: "/properties/1/floorplan", canvasCount, persistedObjects: 71, alternatePlanSelected: true });

const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
for (const check of [checks[0], checks[2], checks[3], checks[5], checks[6]]) {
  await mobile.goto(`${baseUrl}${check.path}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await mobile.locator("main").getByText(check.marker, { exact: false }).first().waitFor({ state: "visible", timeout: 20_000 });
  const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 2) throw new Error(`${check.path} has ${overflow}px horizontal overflow at 390px`);
  results.push({ path: check.path, viewport: "390x844", horizontalOverflow: overflow });
  if (check.path === "/") await mobile.screenshot({ path: path.join(outputDir, "mobile-overview.png"), fullPage: true });
}
await mobile.screenshot({ path: path.join(outputDir, "mobile-floorplan.png"), fullPage: false });

await browser.close();
const actionableErrors = consoleErrors.filter((message) => !/favicon|Download the React DevTools/i.test(message));
if (actionableErrors.length) {
  throw new Error(`Browser console errors:\n${actionableErrors.join("\n")}\nFailed responses:\n${failedResponses.join("\n")}`);
}
console.log(JSON.stringify({ ok: true, results }, null, 2));
