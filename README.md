# Trade Stats Bot — Lobster Group

Бот для **закрытой Telegram-группы с ветками (Topics)**.

## Структура группы

| Ветка | Действие |
|-------|----------|
| **Торговые сетапы** | Фиксация сетапа строгим сообщением → бот отвечает reply |
| **General** | `/мои_сделки`, `/лидерборд`, inline-управление |

## Биржи (авто-мониторинг цен)

Публичные API, без ключей пользователя:

- **OKX** — spot + swap
- **Binance** — spot + futures
- **Bybit** — linear
- **Bitget** — USDT-FUTURES
- **BingX** — swap
- **MEXC** — futures + spot
- **Hyperliquid** — allMids (perp, приоритетная котировка)

Каждые 7 сек бот проверяет цену и автоматически фиксирует TP/SL.

> Приватные API ключи (синхронизация позиций пользователя) — следующий этап.

## Баллы

```
Баллы = чистое движение (1% = 1 балл)
      + бонус (личный результат / 20)
      БУ = -1 балл
```

Пример: +1% чистое, плечо 50x → личное +50% → **3.5 балла**

## Настройка `.env`

```env
# chat_id:setups_topic:general_topic:database_file (; separated)
GROUPS=-100111:3:1:trades_alpha.db;-100222:24101:1:trades_prod.db

# Общие профили (баннер/стикеры) для всех групп
PROFILES_DATABASE_PATH=data/profiles.db
```

ID ветки можно узнать: переслать сообщение из ветки боту @userinfobot или через getUpdates.

## Запуск

```bash
pip install -r requirements.txt
python -m bot.main
```

Бот должен быть **админом группы** (для Topics и ответов в ветках).
