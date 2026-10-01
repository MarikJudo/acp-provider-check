# provider_check — offering агента Second

Платная проверка ACP-провайдера перед наймом. Клиент присылает адрес провайдера и получает вердикт
`RELIABLE / CAUTION / UNRESPONSIVE / UNPROVEN / NOT_FOUND` + ончейн-статистику + флаги риска. Цена $0.10, SLA 5 мин.

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
| RELIABLE | ≥10 оплаченных работ, ≥3 клиента, ≥80% доведено до выплаты, выплаты за 7 дней, без флагов |
| CAUTION | работает, но есть флаги (один клиент ≥80% объёма, self-trade, низкое завершение) или давно не было выплат |
| UNRESPONSIVE | за 30 дней ≥2 заказа, бюджет выставлен <30%, ни одной выплаты (как CryptoRadarX) |
| UNPROVEN | есть в каталоге / получал заказы, но ни разу не получил оплату |
| NOT_FOUND | нет ни профиля, ни истории |

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
