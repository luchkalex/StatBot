# main.py
import asyncio
import nest_asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from handlers import message_handler, start_tracking, stop_tracking, button_handler
from config import TELEGRAM_BOT_TOKEN

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_tracking))
    app.add_handler(CommandHandler("stop", stop_tracking))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("Бот запущен")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())