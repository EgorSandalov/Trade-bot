from contextvars import ContextVar

_request_chat_id: ContextVar[int | None] = ContextVar("request_chat_id", default=None)


def set_request_chat_id(chat_id: int | None) -> None:
    _request_chat_id.set(chat_id)


def get_request_chat_id() -> int | None:
    return _request_chat_id.get()
