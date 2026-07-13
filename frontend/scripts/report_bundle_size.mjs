import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const distRoot = new URL("../dist/", import.meta.url);
const maxBytes = Number(process.env.MAX_BUNDLE_BYTES || 0);

async function collect(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory.pathname, entry.name);
    if (entry.isDirectory()) files.push(...(await collect(new URL(`file://${path}/`))));
    else files.push({ path, size: (await stat(path)).size });
  }
  return files;
}

try {
  const files = await collect(distRoot);
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const largest = [...files].sort((a, b) => b.size - a.size).slice(0, 10);
  console.log(`Bundle total: ${(total / 1024 / 1024).toFixed(2)} MiB`);
  for (const file of largest) {
    console.log(`- ${(file.size / 1024).toFixed(1)} KiB ${file.path.replace(`${distRoot.pathname}`, "")}`);
  }
  if (maxBytes > 0 && total > maxBytes) {
    console.error(`Bundle limit exceeded: ${total} > ${maxBytes} bytes`);
    process.exitCode = 1;
  }
} catch (error) {
  console.error("Bundle report unavailable. Run npm run build first.", error.message);
  process.exitCode = 1;
}
