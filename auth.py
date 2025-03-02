import logging
from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackContext

from config import ACCESS_KEYS
from keyboards import get_stop_keyboard
from stats_helpers import send_grouped_stats
from state import state

logger = logging.getLogger(__name__)

# Состояние для ConversationHandler
ACCESS_KEY_STATE = 1

# Словарь допустимых ключей доступа и соответствующих CSV-файлов

async def start_auth(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info("Авторизация: Получена команда /start от пользователя %s (chat_id: %s)", user_id, chat_id)
    await update.message.reply_text("Введите ключ доступа:")
    return ACCESS_KEY_STATE

async def process_access_key(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    access_key = update.message.text.strip()
    logger.info("Авторизация: Пользователь %s (chat_id: %s) ввёл ключ '%s'", user_id, chat_id, access_key)

    if access_key in ACCESS_KEYS:
        csv_filename = ACCESS_KEYS[access_key]
        context.user_data['csv_filename'] = csv_filename
        logger.info("Авторизация: Ключ '%s' корректен. Привязан CSV файл: %s", access_key, csv_filename)

        # Добавляем chat_id для этого CSV-файла
        if csv_filename not in state.admin_chat_ids:
            state.admin_chat_ids[csv_filename] = set()
        state.admin_chat_ids[csv_filename].add(chat_id)
        logger.info("Авторизация: Добавлен chat_id %s для CSV '%s'. Текущие chat_id: %s",
                    chat_id, csv_filename, state.admin_chat_ids[csv_filename])

        # Запускаем отслеживание статистики
        state.tracking_active = True
        state.stats.clear()
        state.load_from_csv(csv_filename)

        # Отправляем текущую статистику и сообщение о запуске
        await send_grouped_stats(context)
        await update.message.reply_text(
            f"Авторизация успешна.\nСтатистика запущена. Данные сохраняются в {csv_filename}.",
            reply_markup=get_stop_keyboard()
        )
        logger.info("Авторизация завершена для пользователя %s (chat_id: %s)", user_id, chat_id)
        return ConversationHandler.END
    else:
        logger.warning("Авторизация: Пользователь %s ввёл неверный ключ '%s'", user_id, access_key)
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
