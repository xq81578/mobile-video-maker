import { readdir, mkdir, writeFile } from "node:fs/promises";
import { extname, join, parse } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const musicDir = join(root, "music");
const manifestPath = join(musicDir, "manifest.json");
const audioExtensions = new Set([".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"]);

await mkdir(musicDir, { recursive: true });

const entries = await readdir(musicDir, { withFileTypes: true });
const songs = entries
  .filter((entry) => entry.isFile() && audioExtensions.has(extname(entry.name).toLowerCase()))
  .map((entry) => ({
    name: parse(entry.name).name,
    file: entry.name,
  }))
  .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));

await writeFile(manifestPath, `${JSON.stringify(songs, null, 2)}\n`, "utf8");
console.log(`Wrote ${songs.length} songs to ${manifestPath}`);
