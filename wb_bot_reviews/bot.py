import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from handlers import router
from handlers import _auto_worker_loop

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "токен"

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML") 
)

dp = Dispatcher()
dp.include_router(router)


async def main():
    print("✅ Бот запущен!")
    stop_event = asyncio.Event()
    # старт фоновой задачи
    auto_task = asyncio.create_task(_auto_worker_loop(stop_event))

    try:
        await dp.start_polling(bot)
    finally:
        # при завершении — остановим таск
        stop_event.set()
        await auto_task


if __name__ == "__main__":
    asyncio.run(main())
