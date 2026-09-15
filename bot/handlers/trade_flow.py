"""FSM helpers for edit/cancel trade flows — pause price monitoring while user updates the diary."""

from aiogram.fsm.context import FSMContext

from bot.services.trade_service import TradeService


async def begin_trade_flow(
    state: FSMContext,
    trades: TradeService,
    trade_id: int,
) -> None:
    """Pause SL/TP monitoring for this trade until the flow ends."""
    data = await state.get_data()
    prev_id = data.get("trade_id")
    if prev_id and prev_id != trade_id:
        trades.resume_monitoring(int(prev_id))
    trades.pause_monitoring(trade_id)


async def end_trade_flow(state: FSMContext, trades: TradeService) -> int | None:
    """Resume monitoring and clear edit/cancel FSM state."""
    data = await state.get_data()
    trade_id = data.get("trade_id")
    await state.clear()
    if trade_id:
        trades.resume_monitoring(int(trade_id))
        return int(trade_id)
    return None
