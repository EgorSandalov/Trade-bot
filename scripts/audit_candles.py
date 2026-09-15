"""Audit OKX candles vs chart for trailing high detection."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

from bot.services.price_service import fetch_candles, _fetch_okx_candles, _ms, fetch_price

# MSK = UTC+3
MSK = timezone(timedelta(hours=3))


def msk(y, m, d, h, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=MSK).astimezone(timezone.utc)


async def main() -> None:
    windows = [
        ("Peak ~20:10 MSK", msk(2026, 9, 13, 20, 5), msk(2026, 9, 13, 20, 20)),
        ("Peak ~22:07 MSK", msk(2026, 9, 13, 22, 0), msk(2026, 9, 13, 22, 15)),
        ("Catch-up ~21:58 MSK", msk(2026, 9, 13, 21, 50), msk(2026, 9, 13, 22, 10)),
        ("Full day segment", msk(2026, 9, 13, 16, 0), msk(2026, 9, 13, 20, 0)),
    ]

    print("Current OKX price:", await fetch_price("OKX", "BTCUSDT"))
    print()

    for label, since, until in windows:
        print(f"=== {label} ({since.astimezone(MSK).strftime('%H:%M')}–{until.astimezone(MSK).strftime('%H:%M')} MSK) ===")
        candles = await fetch_candles("OKX", "BTCUSDT", since, until)
        if not candles:
            print("  NO CANDLES returned")
            continue
        max_c = max(candles, key=lambda c: c.high)
        print(f"  Candles: {len(candles)} | max high: {max_c.high} @ {max_c.ts.astimezone(MSK).strftime('%H:%M:%S MSK')}")
        above_77400 = [c for c in candles if c.high >= 77400]
        print(f"  Candles with high >= 77400: {len(above_77400)}")
        for c in above_77400:
            print(
                f"    {c.ts.astimezone(MSK).strftime('%H:%M')} "
                f"O={c.open:.1f} H={c.high:.1f} L={c.low:.1f} C={c.close:.1f}"
            )

        # SWAP only
        swap = await _fetch_okx_candles("BTC", _ms(since), _ms(until))
        if swap:
            sm = max(swap, key=lambda c: c.high)
            print(f"  SWAP-only max: {sm.high} @ {sm.ts.astimezone(MSK).strftime('%H:%M MSK')}")
        print()

    # Check if history-candles vs candles endpoint differ
    print("=== Raw OKX API check (single minute 22:07 MSK) ===")
    ts = msk(2026, 9, 13, 22, 7)
    start_ms = _ms(ts - timedelta(minutes=1))
    end_ms = _ms(ts + timedelta(minutes=2))

    import aiohttp

    async def get(url: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None

    for inst in ("BTC-USDT-SWAP", "BTC-USDT"):
        after = end_ms + 60_000
        data = await get(
            f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1m&after={after}&limit=5"
        )
        rows = (data or {}).get("data") or []
        print(f"  {inst} history-candles ({len(rows)} rows):")
        for row in rows[:5]:
            ts_ms = int(row[0])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=MSK)
            print(f"    {dt.strftime('%H:%M:%S MSK')} O={row[1]} H={row[2]} L={row[3]} C={row[4]}")


if __name__ == "__main__":
    asyncio.run(main())
