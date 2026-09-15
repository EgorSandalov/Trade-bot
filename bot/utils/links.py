def setup_message_link(chat_id: int, thread_id: int | None, message_id: int) -> str:
    """Telegram link to the original setup message in a forum topic."""
    internal = str(chat_id).removeprefix("-100")
    if thread_id:
        return f"https://t.me/c/{internal}/{thread_id}/{message_id}"
    return f"https://t.me/c/{internal}/{message_id}"
