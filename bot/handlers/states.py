from aiogram.fsm.state import State, StatesGroup


class EditStates(StatesGroup):
    waiting_setup = State()


class CancelStates(StatesGroup):
    waiting_reason = State()


class ProfileStates(StatesGroup):
    waiting_banner = State()
    waiting_reaction = State()
    waiting_loss_reaction = State()
