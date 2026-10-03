// Готовые отчёты на каждого провайдера: data/reports/<address>.json.
// Нужны для варианта без ACP Serve — LLM-агент Second просто скачивает файл по адресу и отдаёт его покупателю.
//   node serve/build_reports.ts
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const indexFile = new URL("../data/provider_index.json", import.meta.url);
const outDir = new URL("../data/reports/", import.meta.url);

process.env.PROVIDER_INDEX_URL ??= "local://index";
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: any, init?: any) =>
  String(url).startsWith("local://") ? new Response(readFileSync(indexFile)) : realFetch(url, init)) as typeof fetch;

const { checkProvider } = await import("./check.ts");
const addresses = Object.keys(JSON.parse(readFileSync(indexFile, "utf8")).providers);

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

let next = 0, failed = 0;
async function worker() {
  while (next < addresses.length) {
    const a = addresses[next++];
    try {
      writeFileSync(new URL(`${a}.json`, outDir), JSON.stringify(await checkProvider(a), null, 1));
    } catch (e) {
      failed++; console.error(a, (e as Error).message);
    }
  }
}
await Promise.all(Array.from({ length: 6 }, worker));   // профиль из ACP API — не больше 6 запросов параллельно
console.log(`reports: ${addresses.length - failed}/${addresses.length}`);
if (failed > addresses.length / 10) process.exit(1);
