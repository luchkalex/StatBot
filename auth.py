import logging
from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackContext
from keyboards import get_stop_keyboard
from stats_helpers import send_grouped_stats
from state import state

logger = logging.getLogger(__name__)

# Состояние для ConversationHandler
ACCESS_KEY_STATE = 1

# Словарь допустимых ключей доступа и соответствующих CSV-файлов
ACCESS_KEYS = {
    "key1": "stats_account1.csv",
    "key2": "stats_account2.csv"
}


async def start_auth(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    logger.info(f"Авторизация: Получена команда /start от пользователя {user_id}")
    await update.message.reply_text("Введите ключ доступа:")
    return ACCESS_KEY_STATE


async def process_access_key(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    access_key = update.message.text.strip()
    logger.info(f"Авторизация: Пользователь {user_id} ввёл ключ '{access_key}'")

    if access_key in ACCESS_KEYS:
        csv_filename = ACCESS_KEYS[access_key]
        context.user_data['csv_filename'] = csv_filename
        logger.info(f"Авторизация: Ключ '{access_key}' корректен. Привязан CSV файл: {csv_filename}")

        # Запускаем отслеживание статистики
        state.tracking_active = True
        state.admin_chat_id = update.message.chat_id
        state.stats.clear()
        state.global_message_ids.clear()
        state.load_from_csv(csv_filename)

        # Отправляем текущую статистику и сообщение о запуске
        await send_grouped_stats(context)
        await update.message.reply_text(
            f"Авторизация успешна.\nСтатистика запущена. Данные сохраняются в {csv_filename}.",
            reply_markup=get_stop_keyboard()
        )
        logger.info(f"Авторизация: Завершена успешно для пользователя {user_id}")
        return ConversationHandler.END
    else:
        logger.warning(f"Авторизация: Пользователь {user_id} ввёл неверный ключ '{access_key}'")
        await update.message.reply_text("Неверный ключ доступа. Попробуйте ещё раз:")
        return ACCESS_KEY_STATE


# ConversationHandler для авторизации
login_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start_auth)],
    states={
        ACCESS_KEY_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_access_key)]
    },
    fallbacks=[]
)
