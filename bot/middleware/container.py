from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.app.container import AppContainer


class ContainerMiddleware(BaseMiddleware):
    """Injects the composition root into handler data (Dependency Inversion)."""

    def __init__(self, container: AppContainer) -> None:
        if container is None:
            raise ValueError("Container must be provided")
        self._container = container

    async def __call__(self, handler, event: TelegramObject, data: dict):
        data["container"] = self._container
        return await handler(event, data)
