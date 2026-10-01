# Индексатор для offering `provider_check`.
# Сканирует события ACP-контракта (ERC-8183, Base) и собирает статистику по каждому провайдеру
# в data/provider_index.json. Первый запуск — полный скан параллельно (~10-15 мин),
# дальше — только новые блоки (инкрементально, по state.json).
#
#   python indexer.py            # догнать сеть и пересобрать индекс
#   python indexer.py --rebuild  # только пересобрать индекс из уже скачанных событий
import json, os, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D); from keccak import keccak256

RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
ACP = "0x238E541BfefD82238730D00a2208E5497F1832E0"
DEPLOY_BLOCK = 44427013
STEP = 2000            # лимит getLogs публичного RPC
WORKERS = 8
DATA = os.path.join(D, "data")
EVENTS = os.path.join(DATA, "events.jsonl")
STATE = os.path.join(DATA, "state.json")
INDEX = os.path.join(DATA, "provider_index.json")

abi = json.load(open(os.path.join(D, "abi.json"), encoding="utf-8"))["abi"]
canon = lambda e: e["name"] + "(" + ",".join(i["type"] for i in e["inputs"]) + ")"
TOPIC = {"0x" + keccak256(canon(e).encode()).hex(): e["name"] for e in abi if e.get("type") == "event"}

def rpc(method, params, tries=10):
    for k in range(tries):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            d = json.loads(urllib.request.urlopen(req, timeout=45).read())
            if "error" in d: time.sleep(0.6 + 0.4 * k); continue
            return d["result"]
        except Exception:
            time.sleep(0.6 + 0.4 * k)
    raise RuntimeError(f"RPC failed: {method}")

addr = lambda t: "0x" + t[-40:]
usdc = lambda w: int(w, 16) / 1e6

def decode(lg):
    """Лог -> компактная строка [тип, jobId, ..., block]. None для неинтересных событий."""
    nm = TOPIC.get(lg["topics"][0]); t = lg["topics"]; data = lg["data"][2:]; w0 = data[:64] or "0"
    b = int(lg["blockNumber"], 16)
    if nm == "JobCreated":      return ["C", int(t[1], 16), addr(t[2]), addr(t[3]), b]
    if nm == "ProviderSet":     return ["PS", int(t[1], 16), addr(t[2]), b]
    if nm == "BudgetSet":       return ["B", int(t[1], 16), b]          # сумму не берём: в поле бывает мусор
    if nm == "JobFunded":       return ["F", int(t[1], 16), usdc(w0), b]
    if nm == "JobSubmitted":    return ["S", int(t[1], 16), b]
    if nm == "PaymentReleased": return ["P", int(t[1], 16), addr(t[2]), usdc(w0), b]
    if nm == "JobRejected":     return ["J", int(t[1], 16), b]
    if nm == "JobExpired":      return ["E", int(t[1], 16), b]
    if nm == "Refunded":        return ["R", int(t[1], 16), usdc(w0), b]
    return None

def fetch_range(a, z):
    rows = []
    for lg in rpc("eth_getLogs", [{"fromBlock": hex(a), "toBlock": hex(z), "address": ACP}]) or []:
        r = decode(lg)
        if r: rows.append(r)
    return rows

def sync():
    os.makedirs(DATA, exist_ok=True)
    start = json.load(open(STATE))["last_block"] + 1 if os.path.exists(STATE) else DEPLOY_BLOCK
    end = int(rpc("eth_blockNumber", []), 16) - 5   # небольшой запас от реорга
    if start > end: return
    chunks = [(a, min(a + STEP - 1, end)) for a in range(start, end + 1, STEP)]
    print(f"sync {start}..{end}: {len(chunks)} chunks")
    done = [0]; lock = threading.Lock()
    def job(c):
        r = fetch_range(*c)
        with lock:
            done[0] += 1
            if done[0] % 200 == 0: print(f"  {done[0]}/{len(chunks)}")
        return r
    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(job, chunks))       # порядок чанков сохраняется
    with open(EVENTS, "a", encoding="utf-8") as f:
        for rows in results:
            for r in rows: f.write(json.dumps(r) + "\n")
    json.dump({"last_block": end}, open(STATE, "w"))

def build():
    jobs = {}   # jobId -> dict
    for line in open(EVENTS, encoding="utf-8"):
        r = json.loads(line); k = r[0]; j = jobs.setdefault(r[1], {})
        if k == "C":    j.update(client=r[2], provider=r[3], created=r[4])
        elif k == "PS": j["provider"] = r[2]
        elif k == "B":  j["budget"] = True
        elif k == "F":  j["funded"] = j.get("funded", 0) + r[2]
        elif k == "S":  j["submitted"] = r[2]
        elif k == "P":  j.update(paid=j.get("paid", 0) + r[3], paid_at=r[4], provider=r[2])
        elif k == "J":  j["rejected"] = True
        elif k == "E":  j["expired"] = True
        elif k == "R":  j["refund"] = j.get("refund", 0) + r[2]

    head = int(rpc("eth_blockNumber", []), 16)
    head_ts = int(rpc("eth_getBlockByNumber", [hex(head), False])["timestamp"], 16)
    ts = lambda b: head_ts - (head - b) * 2           # Base: блок раз в 2 с
    d30 = head - 30 * 86400 // 2; d7 = head - 7 * 86400 // 2

    P = {}
    zero = "0x" + "0" * 40
    for jid, j in jobs.items():
        p = j.get("provider")
        if not p or p == zero or "created" not in j: continue
        s = P.setdefault(p, dict(received=0, budget_set=0, funded=0, funded_usdc=0.0, submitted=0, delivered=0, accepted_never=0, paid=0, paid_usdc=0.0,
                                 rejected=0, expired=0, refunded_usdc=0.0, received_30d=0, budget_set_30d=0, paid_30d=0,
                                 paid_7d=0, first_job=None, last_job=None, last_paid=None, _clients={}, _self=0.0))
        s["received"] += 1
        s["first_job"] = min(s["first_job"] or j["created"], j["created"]); s["last_job"] = max(s["last_job"] or 0, j["created"])
        recent = j["created"] >= d30
        if recent: s["received_30d"] += 1
        if j.get("budget"):
            s["budget_set"] += 1
            if recent: s["budget_set_30d"] += 1
        if j.get("funded"):
            s["funded"] += 1; s["funded_usdc"] += j["funded"]
            c = j["client"]; s["_clients"][c] = s["_clients"].get(c, 0) + j["funded"]
            if c == p: s["_self"] += j["funded"]
        if "submitted" in j:
            s["submitted"] += 1
            if j.get("funded"):
                s["delivered"] += 1                         # оплаченная работа сдана провайдером
                if not j.get("paid") and not j.get("rejected"): s["accepted_never"] += 1  # клиент не принял -> возврат
        if j.get("paid"):
            s["paid"] += 1; s["paid_usdc"] += j["paid"]; s["last_paid"] = max(s["last_paid"] or 0, j["paid_at"])
            if j["paid_at"] >= d30: s["paid_30d"] += 1
            if j["paid_at"] >= d7: s["paid_7d"] += 1
        if j.get("rejected"): s["rejected"] += 1
        if j.get("expired"): s["expired"] += 1
        s["refunded_usdc"] += j.get("refund", 0)

    out = {}
    for p, s in P.items():
        cl = s.pop("_clients"); self_usdc = s.pop("_self"); tot = sum(cl.values())
        top = max(cl.items(), key=lambda kv: kv[1]) if cl else (None, 0)
        s.update(
            unique_clients=len(cl),
            top_client=top[0], top_client_share=round(top[1] / tot, 3) if tot else 0,
            self_trade_usdc=round(self_usdc, 4),
            funded_usdc=round(s["funded_usdc"], 4), paid_usdc=round(s["paid_usdc"], 4), refunded_usdc=round(s["refunded_usdc"], 4),
            first_job=ts(s["first_job"]), last_job=ts(s["last_job"]), last_paid=ts(s["last_paid"]) if s["last_paid"] else None,
        )
        out[p] = s
    # Кольца: A — главный клиент B, а B — главный клиент A (платят друг другу).
    for p, s in out.items():
        c = s["top_client"]
        s["ring_with"] = c if c in out and out[c]["top_client"] == p and s["top_client_share"] >= 0.5 else None
    json.dump({"generated_at": head_ts, "head_block": head, "contract": ACP, "providers": out},
              open(INDEX, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"index: {len(out)} providers, {len(jobs)} jobs -> {INDEX} ({os.path.getsize(INDEX)//1024} KB)")

if __name__ == "__main__":
    if "--rebuild" not in sys.argv: sync()
    build()
