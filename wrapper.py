import logging
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
logger = logging.getLogger(__name__)

def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):

        if not context.user_data.get("access_key"):
            # Если пользователь не авторизован, отправляем сообщение с просьбой использовать /start
            # Если сообщение пришло не из приватного чата, игнорируем его
            if update.effective_chat.type != "private":
                logger.info("Получено сообщение в группе без авторизации")
                return
            if update.message:
                await update.message.reply_text("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.")
            elif update.callback_query:
                await update.callback_query.answer("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
