"""Live smoke test: price + 2h candles for every supported exchange."""

import asyncio
from datetime import datetime, timedelta, timezone

from bot.domain.exchanges import SUPPORTED_EXCHANGES
from bot.services.price_service import fetch_candles, fetch_price


async def check_exchange(exchange: str) -> dict:
    symbol = "BTCUSDT"
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=2)
    price = await fetch_price(exchange, symbol)
    candles = await fetch_candles(exchange, symbol, since, now)
    return {
        "exchange": exchange,
        "price": price,
        "candles": len(candles),
        "ok": price is not None and len(candles) >= 60,
    }


async def main() -> None:
    results = await asyncio.gather(*(check_exchange(ex) for ex in SUPPORTED_EXCHANGES))
    print(f"{'Exchange':<14} {'Price':>12} {'Candles(2h)':>12}  OK")
    print("-" * 44)
    for row in results:
        price = f"{row['price']:.2f}" if row["price"] else "—"
        ok = "OK" if row["ok"] else "FAIL"
        print(f"{row['exchange']:<14} {price:>12} {row['candles']:>12}  {ok}")


if __name__ == "__main__":
    asyncio.run(main())
