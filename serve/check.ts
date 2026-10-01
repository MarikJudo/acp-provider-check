// Логика проверки провайдера ACP. Отдельно от handler.ts, чтобы гонять локально без ACP.
// Источники: (1) ончейн-индекс по контракту ACP (собирает indexer.py), (2) публичный профиль агента в ACP API.

// Публичный URL файла provider_index.json (обновляется индексатором раз в час через GitHub Actions).
export const INDEX_URL =
  process.env.PROVIDER_INDEX_URL ?? "https://raw.githubusercontent.com/MarikJudo/acp-provider-check/main/data/provider_index.json";
const ACP_API = "https://api.acp.virtuals.io";
const DAY = 86400;

type Stats = {
  received: number; budget_set: number; funded: number; funded_usdc: number; submitted: number;
  paid: number; paid_usdc: number; rejected: number; expired: number; refunded_usdc: number;
  received_30d: number; budget_set_30d: number; paid_30d: number; paid_7d: number;
  first_job: number; last_job: number; last_paid: number | null;
  unique_clients: number; top_client: string | null; top_client_share: number; self_trade_usdc: number;
};
type Index = { generated_at: number; head_block: number; providers: Record<string, Stats> };

export type Verdict = "RELIABLE" | "CAUTION" | "UNRESPONSIVE" | "UNPROVEN" | "NOT_FOUND";

let cache: { at: number; data: Index } | null = null;
async function loadIndex(): Promise<Index> {
  if (cache && Date.now() - cache.at < 10 * 60_000) return cache.data;
  if (!INDEX_URL) throw new Error("PROVIDER_INDEX_URL is not set");
  const res = await fetch(INDEX_URL);
  if (!res.ok) throw new Error(`index fetch failed: ${res.status}`);
  cache = { at: Date.now(), data: (await res.json()) as Index };
  return cache.data;
}

async function loadProfile(address: string): Promise<any | null> {
  const res = await fetch(`${ACP_API}/agents/wallet/${address}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`profile fetch failed: ${res.status}`);
  return ((await res.json()) as any).data;
}

const pct = (x: number) => Math.round(x * 100);
const iso = (t: number | null) => (t ? new Date(t * 1000).toISOString().slice(0, 10) : null);

export async function checkProvider(rawAddress: unknown) {
  const address = String(rawAddress ?? "").trim().toLowerCase();
  if (!/^0x[0-9a-f]{40}$/.test(address)) {
    return { error: "provider_address must be a 0x-prefixed 20-byte EVM address" };
  }

  const [index, profile] = await Promise.all([loadIndex(), loadProfile(address)]);
  const s = index.providers[address];
  const now = index.generated_at;
  const flags: string[] = [];

  // --- профиль ACP ---
  const lastActive = profile?.lastActiveAt ? Date.parse(profile.lastActiveAt) / 1000 : null;
  if (lastActive && lastActive > now + 365 * DAY) {
    flags.push("lastActiveAt is pinned to the far future — 'always online' status is self-declared, not measured");
  }
  if (profile?.isHidden) flags.push("profile is hidden from the marketplace");

  if (!s) {
    const verdict: Verdict = profile ? "UNPROVEN" : "NOT_FOUND";
    return {
      provider_address: address, name: profile?.name ?? null, verdict,
      summary: profile ? "Listed on ACP but has no on-chain job history yet." : "No ACP profile and no on-chain jobs for this address.",
      onchain: null, flags, index_as_of: iso(now),
    };
  }

  // --- ончейн-метрики ---
  const budgetRate = s.received ? s.budget_set / s.received : 0;        // отвечает ли на заказы вообще
  const completionRate = s.funded ? s.paid / s.funded : 0;              // доводит ли оплаченные до выплаты
  const recentBudgetRate = s.received_30d ? s.budget_set_30d / s.received_30d : null;

  if (s.self_trade_usdc > 0) flags.push(`self-trading: ${s.self_trade_usdc} USDC funded by its own wallet`);
  if (s.paid >= 5 && s.top_client_share >= 0.8)
    flags.push(`${pct(s.top_client_share)}% of funded volume comes from one client (${s.top_client}) — stats may be inflated`);
  if (s.funded >= 5 && completionRate < 0.7) flags.push(`only ${pct(completionRate)}% of funded jobs were paid out`);
  if (s.rejected > 0) flags.push(`${s.rejected} job(s) rejected`);

  let verdict: Verdict;
  let summary: string;
  if (s.received_30d >= 2 && (recentBudgetRate ?? 0) < 0.3 && s.paid_30d === 0) {
    verdict = "UNRESPONSIVE";
    summary = `Received ${s.received_30d} job(s) in the last 30 days but quoted a budget on ${pct(recentBudgetRate ?? 0)}% and completed none.`;
  } else if (s.paid === 0) {
    verdict = "UNPROVEN";
    summary = "Has received jobs but never been paid on-chain.";
  } else if (s.paid >= 10 && s.unique_clients >= 3 && completionRate >= 0.8 && s.paid_7d > 0 && flags.length === 0) {
    verdict = "RELIABLE";
    summary = `${s.paid} paid jobs from ${s.unique_clients} clients, ${pct(completionRate)}% completion, active in the last 7 days.`;
  } else {
    verdict = "CAUTION";
    summary = `${s.paid} paid job(s) from ${s.unique_clients} client(s), ${pct(completionRate)}% completion` +
      (s.paid_7d ? "" : ", no payouts in the last 7 days") + (flags.length ? "; see flags." : ".");
  }

  return {
    provider_address: address,
    name: profile?.name ?? null,
    listed_on_acp: !!profile,
    verdict,
    summary,
    onchain: {
      jobs_received: s.received,
      budget_quoted_rate: pct(budgetRate),
      jobs_funded: s.funded,
      jobs_paid: s.paid,
      completion_rate: pct(completionRate),
      paid_usdc: s.paid_usdc,
      refunded_usdc: s.refunded_usdc,
      unique_paying_clients: s.unique_clients,
      top_client_share: pct(s.top_client_share),
      jobs_received_30d: s.received_30d,
      jobs_paid_30d: s.paid_30d,
      first_job: iso(s.first_job),
      last_job: iso(s.last_job),
      last_paid: iso(s.last_paid),
    },
    offerings: profile?.offerings?.filter((o: any) => !o.isHidden).map((o: any) => ({ name: o.name, price_usdc: Number(o.priceValue), sla_min: o.slaMinutes })) ?? [],
    flags,
    index_as_of: iso(now),
  };
}
