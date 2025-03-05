import logging
from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackContext

from config import ACCESS_KEYS
from keyboards import get_stop_keyboard, get_main_keyboard
from stats_helpers import send_grouped_stats
from state import state
from groups_csv import load_allowed_groups  # импорт нового модуля

logger = logging.getLogger(__name__)

ACCESS_KEY_STATE = 1
MAX_ACTIVE_USERS = 3
async def start_auth(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info("Авторизация: Получена команда /start от пользователя %s (chat_id: %s)", user_id, chat_id)
    await update.message.reply_text(f"""Привет! 👋 Я — бот для мониторинга активности телефонных номеров в Telegram-группах.
Я собираю статистику о том, когда номера начали и закончили работу, считаю время простоя и создаю отчёты.

📊 Основные возможности:

✅ Отслеживание активности номеров в группах и темах

✅ Создание персональных отчётов в реальном времени

✅ Управление через команды

🔹 Как пользоваться:
1️⃣ Авторизация: Введите /start и укажите ваш ключ доступа.

2️⃣ Добавление группы для мониторинга: Используйте команду /add_group, затем введите ID группы и её название.

3️⃣ Удаление группы из списка: Используйте /remove_group, затем введите ID группы.

4️⃣ Остановка мониторинга: Используйте /stop.

5️⃣ Возобновление сбора статистики: Используйте /relaunch_stat.

6️⃣ Просмотр списка отслеживаемых групп: Используйте /list_groups.

Добавьте меня в нужные группы и сбор статистики начнется🚀
Если возникнут вопросы – обращайтесь @jeasusy 💬
    """)
    await update.message.reply_text(f"Введите ключ доступа:")
    return ACCESS_KEY_STATE


async def process_access_key(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    access_key = update.message.text.strip()
    logger.info("Авторизация: Пользователь %s (chat_id: %s) ввёл ключ '%s'", user_id, chat_id, access_key)

    if access_key in ACCESS_KEYS:
        csv_filename = ACCESS_KEYS[access_key]
        # Проверка: если под этим ключом уже залогинено 3 или более пользователей, отклоняем запрос
        if csv_filename not in state.admin_chat_ids:
            state.admin_chat_ids[csv_filename] = set()
        if len(state.admin_chat_ids[csv_filename]) >= MAX_ACTIVE_USERS:
            await update.message.reply_text("Превышено допустимое количество пользователей для этого ключа.")
            return ACCESS_KEY_STATE

        context.user_data['csv_filename'] = csv_filename
        context.user_data['access_key'] = access_key  # сохраняем ключ
        logger.info("Авторизация: Ключ '%s' корректен. Привязан CSV файл: %s", access_key, csv_filename)
        state.admin_chat_ids[csv_filename].add(chat_id)

        # Загрузка разрешённых групп для данного ключа
        allowed_groups_all = load_allowed_groups()
        user_allowed_groups = allowed_groups_all.get(access_key, {})  # {group_id: group_name}
        context.user_data["allowed_groups"] = user_allowed_groups
        state.allowed_groups[csv_filename] = user_allowed_groups

        # Обновляем mapping group_to_keys: для каждой группы добавляем csv_filename
        for group_id in user_allowed_groups.keys():
            if group_id not in state.group_to_keys:
                state.group_to_keys[group_id] = set()
            state.group_to_keys[group_id].add(csv_filename)

        state.tracking_active = True
        state.stats.clear()
        state.load_from_csv(csv_filename)

        await send_grouped_stats(context)
        await update.message.reply_text(
            "Авторизация успешна.\nСтатистика запущена",
            reply_markup=get_main_keyboard()
        )
        logger.info("Авторизация завершена для пользователя %s (chat_id: %s)", user_id, chat_id)
        return ConversationHandler.END
    else:
        logger.warning("Авторизация: Пользователь %s ввёл неверный ключ '%s'", user_id, access_key)
        await update.message.reply_text("Неверный ключ доступа. Попробуйте ещё раз:")
        return ACCESS_KEY_STATE



login_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start_auth)],
    states={
        ACCESS_KEY_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_access_key)]
    },
    fallbacks=[]
)
