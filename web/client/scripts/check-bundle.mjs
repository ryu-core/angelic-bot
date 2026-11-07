import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

const dist = resolve("dist");
const manifest = JSON.parse(await readFile(resolve(dist, ".vite", "manifest.json"), "utf8"));

function findChunk(predicate, label) {
  const entry = Object.entries(manifest).find(predicate);
  if (!entry) throw new Error(`Could not find ${label} in the Vite manifest.`);
  return entry[1].file;
}

const mainFile = findChunk(([, value]) => value.isEntry, "main entry");

if (Object.entries(manifest).some(([key, value]) => key.includes("CrystalScene") || value.name === "CrystalScene")) {
  throw new Error("The retired CrystalScene is still present in the production manifest.");
}

const gzipLimits = [
  ["main entry", mainFile, 125_000],
];

const assetLimits = [
  ["Saturn video", "media/xiel-saturn-clean.mp4", 5_500_000],
  ["Saturn poster", "media/xiel-saturn-poster-clean.jpg", 350_000],
  ["Social preview", "og.png", 750_000],
  ["Favicon", "favicon.png", 25_000],
];

let failed = false;
for (const [label, file, limit] of gzipLimits) {
  const source = await readFile(resolve(dist, file));
  const size = gzipSync(source, { level: 9 }).byteLength;
  const result = size <= limit ? "PASS" : "FAIL";
  console.log(`${result} ${label}: ${size.toLocaleString()} / ${limit.toLocaleString()} gzip bytes (${file})`);
  failed ||= size > limit;
}

for (const [label, file, limit] of assetLimits) {
  const { size } = await stat(resolve(dist, file));
  const result = size <= limit ? "PASS" : "FAIL";
  console.log(`${result} ${label}: ${size.toLocaleString()} / ${limit.toLocaleString()} bytes (${file})`);
  failed ||= size > limit;
}

if (failed) process.exitCode = 1;
