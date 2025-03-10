import logging
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
logger = logging.getLogger(__name__)

from state import state  # импорт глобального состояния

def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        chat_type = update.effective_chat.type
        # Для личных чатов требуем, чтобы у пользователя был access_key
        if chat_type == "private":
            if not context.user_data.get("access_key"):
                if update.message:
                    await update.message.reply_text("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.")
                elif update.callback_query:
                    await update.callback_query.answer("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.", show_alert=True)
                return
        else:
            # Для групп проверяем, что ID группы присутствует в глобальном списке разрешённых
            group_id = update.effective_chat.id
            if group_id not in state.group_to_keys or not state.group_to_keys[group_id]:
                logger.info("Сообщение из группы %s, которая не входит в список разрешённых", group_id)
                return
        return await func(update, context, *args, **kwargs)
    return wrapper
