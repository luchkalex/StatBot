import asyncio
import nest_asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from auth import login_conv_handler
from stats_helpers import stop_tracking, button_handler, message_handler
from groups_commands import add_group, remove_group, list_groups
from config import TELEGRAM_BOT_TOKEN

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(login_conv_handler)
    app.add_handler(CommandHandler("stop", stop_tracking))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Обработчики команд для управления разрешёнными группами
    app.add_handler(CommandHandler("add_group", add_group))
    app.add_handler(CommandHandler("remove_group", remove_group))
    app.add_handler(CommandHandler("list_groups", list_groups))

    logger.info("Бот запущен")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
