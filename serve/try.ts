// Локальный прогон проверки без ACP: node serve/try.ts 0xадрес [0xадрес ...]
// Индекс читается из data/provider_index.json, профиль — из живого ACP API.
import { readFileSync } from "node:fs";

process.env.PROVIDER_INDEX_URL ??= "local://index";
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: any, init?: any) =>
  String(url).startsWith("local://")
    ? new Response(readFileSync(new URL("../data/provider_index.json", import.meta.url)))
    : realFetch(url, init)) as typeof fetch;

const { checkProvider } = await import("./check.ts");
for (const a of process.argv.slice(2)) console.log(JSON.stringify(await checkProvider(a), null, 2));
