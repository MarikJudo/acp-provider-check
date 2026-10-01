# provider_check — offering агента Second

Платная проверка ACP-провайдера перед наймом. Клиент присылает адрес провайдера и получает вердикт
`RELIABLE / CAUTION / WASH_SUSPECTED / UNRESPONSIVE / UNPROVEN / NOT_FOUND` + ончейн-статистику + флаги риска. Цена $0.10, SLA 5 мин.

## Как устроено

```
indexer.py ──(раз в час, GitHub Actions)──> data/provider_index.json ──(публичный URL)──┐
                                                                                      ▼
клиент ACP ──job──> ACP Serve (хостинг Virtuals) ──> serve/handler.ts ──> serve/check.ts ──> отчёт
                                                                    └──> api.acp.virtuals.io (профиль)
```

- **indexer.py** — сканирует все события ACP-контракта `0x238E…32E0` на Base (публичный RPC, без ключей),
  собирает по каждому провайдеру: получено работ, на сколько выставил бюджет, оплачено, выплачено, отказы,
  возвраты, число клиентов, доля крупнейшего клиента, self-trade, активность за 7/30 дней.
- **serve/check.ts** — вся логика вердикта. Профиль берёт из публичного ACP API, статистику — из индекса.
- **serve/handler.ts** — тонкая обёртка под ACP Serve.
- **serve/try.ts** — локальный прогон без ACP: `node serve/try.ts 0xадрес`.

## Вердикты

| Вердикт | Когда |
|---|---|
| RELIABLE | ≥10 оплаченных работ, ≥3 клиента, сдал ≥90% оплаченных, главный клиент <80% объёма, выплаты за 7 дней |
| CAUTION | работает, но есть оговорки: один клиент ≥80% объёма, мало сдаёт, давно не было выплат |
| WASH_SUSPECTED | кольцо (два кошелька — главные клиенты друг друга) или self-trade: объём не отражает спрос |
| UNRESPONSIVE | ни разу не выставил бюджет, или за 30 дней ≥2 заказа, бюджет <30%, ни одной выплаты (как CryptoRadarX) |
| UNPROVEN | отвечает / есть в каталоге, но ни разу не получил оплату |
| NOT_FOUND | нет ни профиля, ни истории |

Надёжность меряется по **сдаче** оплаченных работ (`delivery_rate`), а не по выплатам: тысячи работ Otto
сданы, но не приняты клиентом-накрутчиком и вернулись по таймауту — это вина клиента, не провайдера.

Срез на 2026-10-01 (509 провайдеров): RELIABLE 1 · CAUTION 250 · WASH_SUSPECTED 16 · UNRESPONSIVE 200 · UNPROVEN 42.
Кольцо `0x44cc…6664` (iCLONE) ↔ `0xe09f…8584` — ~$1 455, ~77% всех выплат агентам в ACP за историю.

## Запуск (по шагам)

1. **Индекс.** `python indexer.py` — первый раз полный скан (~30 мин), потом только новые блоки.
2. **Публикация индекса.** Репозиторий на GitHub (публичный) с этой папкой → Actions раз в час обновляет
   `data/provider_index.json`. Ссылка вида
   `https://raw.githubusercontent.com/<user>/<repo>/main/data/provider_index.json` → это `PROVIDER_INDEX_URL`.
3. **ACP Serve** (на своём компьютере, из-под аккаунта владельца Second):
   ```
   npm i -g @virtuals-protocol/acp-cli
   acp configure                      # вход, выбрать агента Second
   acp serve init --name provider_check
   # заменить сгенерированные handler.ts / offering.json на файлы из serve/, положить рядом check.ts,
   # в check.ts вписать INDEX_URL
   acp serve start                    # локальный тест
   acp offering create --from-file offering.json
   acp serve deploy                   # хостинг у Virtuals, работает 24/7 без вашего компьютера
   ```
4. **Проверка.** Нанять самого себя с другого агента (например, Searcher Agent) за $0.10 и проверить ответ.
