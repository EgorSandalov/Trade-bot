"""Query trailing SL extremes for trades #8-10."""
import asyncio
import aiosqlite
import sys

sys.stdout.reconfigure(encoding="utf-8")


async def main() -> None:
    async with aiosqlite.connect("trades.db") as db:
        db.row_factory = aiosqlite.Row
        rows = await (
            await db.execute(
                """
                SELECT t.id, t.user_trade_number, t.exchange, t.symbol, t.side, t.status,
                       t.entry_price, t.executed_entry_price, t.remaining_percent,
                       sl.trail_mode, sl.trail_value, sl.price AS sl_price,
                       sl.activation_price, sl.pre_activation_stop,
                       sl.extreme_price, sl.trail_active, sl.status AS sl_status
                FROM trades t
                LEFT JOIN stop_losses sl ON sl.trade_id = t.id
                WHERE t.user_trade_number IN (8, 9, 10)
                ORDER BY t.user_trade_number
                """
            )
        ).fetchall()
        print(f"Found {len(rows)} trades")
        for r in rows:
            d = dict(r)
            num = d["user_trade_number"]
            print(f"\n=== Trade #{num} (db id={d['id']}) ===")
            print(f"  {d['exchange']} {d['symbol']} {d['side'].upper()} | status: {d['status']}")
            print(f"  Entry: {d['executed_entry_price'] or d['entry_price']}")
            print(f"  Trail mode: {d['trail_mode']} | value: {d['trail_value']}")
            print(f"  SL price now: {d['sl_price']} | trail_active: {bool(d['trail_active'])}")
            print(f"  Activation: {d['activation_price']} | pre-stop: {d['pre_activation_stop']}")
            print(f"  EXTREME (max tracked): {d['extreme_price']}")
            ev = await (
                await db.execute(
                    """
                    SELECT event_type, description, created_at FROM trade_events
                    WHERE trade_id=? AND event_type IN ('sl_trailed', 'sl_changed')
                    ORDER BY created_at
                    """,
                    (d["id"],),
                )
            ).fetchall()
            if ev:
                print("  Trail events:")
                for e in ev:
                    print(f"    {e[2]} | {e[0]} | {e[1]}")
            if d["extreme_price"] is None and d["trail_mode"] != "fixed":
                all_ev = await (
                    await db.execute(
                        "SELECT event_type, description, created_at FROM trade_events WHERE trade_id=? ORDER BY created_at",
                        (d["id"],),
                    )
                ).fetchall()
                if all_ev:
                    print("  All events (trail never activated):")
                    for e in all_ev:
                        print(f"    {e[2]} | {e[0]} | {e[1]}")


if __name__ == "__main__":
    asyncio.run(main())
