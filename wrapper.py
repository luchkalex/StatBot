from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext

def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if not context.user_data.get("access_key"):
            # Если пользователь не авторизован, отправляем сообщение с просьбой использовать /start
            if update.message:
                await update.message.reply_text("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.")
            elif update.callback_query:
                await update.callback_query.answer("Вы не авторизованы. Пожалуйста, используйте /start для авторизации.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
