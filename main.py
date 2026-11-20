import asyncio
import logging
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN
from bot.handlers import router, user_sessions
from web.server import init_web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        logging.error("BOT_TOKEN не задан! Укажите токен в файле .env")
        return

    # Сессия бота с увеличенным таймаутом
    session = AiohttpSession(timeout=300.0)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.include_router(router)

    # Запуск веб-сервера загрузки больших видео (до 10-15 ГБ) на порту 8080
    web_app = init_web_app(bot, user_sessions)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()
    logging.info("🚀 Веб-студия загрузки (до 15 ГБ) доступна на http://localhost:8080 и http://192.168.0.108:8080")

    logging.info("ai-editor from softer_052: Бот запускается...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот и сервер остановлены.")
