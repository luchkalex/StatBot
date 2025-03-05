import asyncio
import nest_asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from auth import login_conv_handler
from stats_helpers import stop_tracking, button_handler, message_handler, relaunch_stat
from groups_commands import list_groups, add_group_handler, remove_group_handler
from config import TELEGRAM_BOT_TOKEN

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Сначала регистрируем обработчики команд
    app.add_handler(login_conv_handler)
    app.add_handler(CommandHandler("stop_work", stop_tracking))
    app.add_handler(CommandHandler("restart_work", relaunch_stat))
    app.add_handler(CommandHandler("list_groups", list_groups))
    # Затем ConversationHandler для диалогов
    app.add_handler(add_group_handler)
    app.add_handler(remove_group_handler)

    # Обработчик callback-кнопок
    app.add_handler(CallbackQueryHandler(button_handler))

    # Общий обработчик текстовых сообщений (должен быть **последним**!)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
