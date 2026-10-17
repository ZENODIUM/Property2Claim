import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const sourceRoot = join(projectRoot, "node_modules", "cesium", "Build", "Cesium");
const destinationRoot = join(projectRoot, "public", "cesium");
const assetDirectories = ["Assets", "ThirdParty", "Widgets", "Workers"];

await mkdir(destinationRoot, { recursive: true });
for (const directory of assetDirectories) {
  const destination = join(destinationRoot, directory);
  await rm(destination, { recursive: true, force: true });
  await cp(join(sourceRoot, directory), destination, { recursive: true });
}

console.log("Cesium runtime assets copied to public/cesium");
