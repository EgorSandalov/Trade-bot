"""Compare OKX candle sources: swap last, spot, mark, index."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import aiohttp

sys.stdout.reconfigure(encoding="utf-8")

MSK = timezone(timedelta(hours=3))


async def fetch_okx(endpoint: str, inst: str, after_ms: int, limit: int = 10) -> list:
    url = f"https://www.okx.com/api/v5/market/{endpoint}?instId={inst}&bar=1m&after={after_ms}&limit={limit}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json() if r.status == 200 else {}
    return (data or {}).get("data") or []


def fmt_row(row: list) -> str:
    ts_ms = int(row[0])
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=MSK)
    return f"{dt.strftime('%H:%M MSK')} O={row[1]} H={row[2]} L={row[3]} C={row[4]}"


async def compare_minute(label: str, msk_h: int, msk_m: int) -> None:
    ts = datetime(2026, 9, 13, msk_h, msk_m, tzinfo=MSK)
    after_ms = int((ts + timedelta(minutes=3)).timestamp() * 1000)
    print(f"\n=== {label} ({msk_h:02d}:{msk_m:02d} MSK) ===")
    sources = [
        ("swap last", "history-candles", "BTC-USDT-SWAP"),
        ("spot last", "history-candles", "BTC-USDT"),
        ("swap mark", "mark-price-candles", "BTC-USDT-SWAP"),
        ("swap index", "index-candles", "BTC-USDT"),
    ]
    for name, endpoint, inst in sources:
        rows = await fetch_okx(endpoint, inst, after_ms, limit=8)
        target = None
        for row in rows:
            row_ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=MSK)
            if row_ts.hour == msk_h and row_ts.minute == msk_m:
                target = row
                break
        if target:
            print(f"  {name:12s} {fmt_row(target)}")
        else:
            print(f"  {name:12s} (not found in {len(rows)} rows)")


async def main() -> None:
    await compare_minute("Peak on chart #1", 20, 12)
    await compare_minute("Peak on chart #2", 22, 7)
    await compare_minute("User cursor 20:10", 20, 10)

    # Ticker comparison now
    print("\n=== Live tickers ===")
    async with aiohttp.ClientSession() as s:
        for inst in ("BTC-USDT-SWAP", "BTC-USDT"):
            async with s.get(
                f"https://www.okx.com/api/v5/market/ticker?instId={inst}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
                t = d["data"][0]
                print(
                    f"  {inst}: last={t['last']} high24h={t['high24h']} "
                    f"low24h={t['low24h']}"
                )


if __name__ == "__main__":
    asyncio.run(main())
