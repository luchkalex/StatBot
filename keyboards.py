import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# keyboards.py
from telegram import ReplyKeyboardMarkup

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["/start", "/list_groups"],
        ["/add_group", "/remove_group"],
        ["/stop_work", "/restart_work"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_stop_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Создание клавиатуры 'Стоп'")
    keyboard = [
        [InlineKeyboardButton("Стоп", callback_data="stop_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_start_keyboard() -> InlineKeyboardMarkup:
    logger.debug("Создание клавиатуры 'Старт'")
    keyboard = [
        [InlineKeyboardButton("Старт", callback_data="start_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_group_stats_keyboard(group_id: int) -> InlineKeyboardMarkup:
    logger.debug(f"Создание клавиатуры 'Статистика по пк' для группы {group_id}")
    keyboard = [
        [InlineKeyboardButton("Статистика по пк", callback_data=f"group_stats_{group_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_daily_stats_keyboard(group_id: int) -> InlineKeyboardMarkup:
    logger.debug(f"Создание клавиатуры 'Статистика по группе' для группы {group_id}")
    keyboard = [
        [InlineKeyboardButton("Статистика по группе", callback_data=f"daily_stats_{group_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)