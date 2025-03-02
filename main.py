# main.py
import asyncio
import nest_asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

# Импортируем новые обработчики для авторизации вместе с другими функциями
from handlers import (
    message_handler,
    stop_tracking,
    button_handler,
    start_auth,
    process_access_key,
    login_conv_handler  # ConversationHandler, который мы создавали для авторизации
)
from config import TELEGRAM_BOT_TOKEN

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем ConversationHandler для авторизации.
    # Он перехватывает команду /start и запрашивает ключ доступа.
    app.add_handler(login_conv_handler)

    # Регистрируем остальные обработчики, которые будут использоваться после авторизации.
    app.add_handler(CommandHandler("stop", stop_tracking))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Бот запущен")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
