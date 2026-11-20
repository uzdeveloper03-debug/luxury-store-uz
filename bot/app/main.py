import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from .config import BotSettings, get_settings


def create_router(settings: BotSettings) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Открыть магазин",
                        web_app=WebAppInfo(url=settings.webapp_url),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Техподдержка",
                        url=settings.support_url,
                    )
                ],
            ]
        )

        await message.answer(
            "Добро пожаловать! Выберите пункт:",
            reply_markup=keyboard,
        )

    return router


async def main() -> None:
    settings = get_settings()

    bot = Bot(token=settings.bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(settings))

    logging.basicConfig(level=logging.INFO)

    logging.info("Luxury Store UZ bot is starting")

    async with bot:
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
