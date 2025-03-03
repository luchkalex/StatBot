import logging
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters
from state import state
from groups_csv import load_allowed_groups, save_allowed_groups

logger = logging.getLogger(__name__)

# Состояние диалога для добавления группы
ADD_GROUP = 1
REMOVE_GROUP = 1
async def add_group_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Введите ID группы и название группы через пробел.\nПример: -1002446730600 Whats for test 2")
    return ADD_GROUP

async def add_group_process(update: Update, context: CallbackContext) -> int:
    logger.info("Add group process\n")
    text = update.message.text.strip()
    args = text.split()
    if len(args) < 2:
        await update.message.reply_text("Ошибка: введите ID группы и название группы через пробел.")
        return ADD_GROUP
    try:
        group_id = int(args[0])
        group_name = " ".join(args[1:])
    except Exception as e:
        await update.message.reply_text("Ошибка: неверный формат ID группы.")
        return ADD_GROUP
    access_key = context.user_data.get("access_key")
    csv_filename = context.user_data.get("csv_filename")
    if not access_key or not csv_filename:
        await update.message.reply_text("Вы не авторизованы.")
        return ConversationHandler.END
    if csv_filename not in state.allowed_groups:
        state.allowed_groups[csv_filename] = {}
    state.allowed_groups[csv_filename][group_id] = group_name
    # Обновляем mapping для группы: добавляем csv_filename в набор для group_id
    if group_id not in state.group_to_keys:
        state.group_to_keys[group_id] = set()
    state.group_to_keys[group_id].add(csv_filename)
    allowed_groups_all = load_allowed_groups()
    if access_key not in allowed_groups_all:
        allowed_groups_all[access_key] = {}
    allowed_groups_all[access_key][group_id] = group_name
    save_allowed_groups(allowed_groups_all)
    await update.message.reply_text(f"Группа {group_name} (ID: {group_id}) добавлена в разрешённые.")
    return ConversationHandler.END

add_group_handler = ConversationHandler(
    entry_points=[CommandHandler("add_group", add_group_start)],
    states={
        ADD_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_process)]
    },
    fallbacks=[]
)


async def remove_group_start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Введите ID группы для удаления.")
    return REMOVE_GROUP

async def remove_group_process(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    args = text.split()
    if len(args) < 1:
        await update.message.reply_text("Ошибка: введите ID группы.")
        return REMOVE_GROUP
    try:
        group_id = int(args[0])
    except Exception as e:
        await update.message.reply_text("Ошибка: неверный формат ID группы.")
        return REMOVE_GROUP
    access_key = context.user_data.get("access_key")
    csv_filename = context.user_data.get("csv_filename")
    if not access_key or not csv_filename:
        await update.message.reply_text("Вы не авторизованы.")
        return ConversationHandler.END
    if csv_filename in state.allowed_groups and group_id in state.allowed_groups[csv_filename]:
        group_name = state.allowed_groups[csv_filename].pop(group_id)
        # Обновляем глобальный mapping для группы: удаляем csv_filename
        if group_id in state.group_to_keys:
            state.group_to_keys[group_id].discard(csv_filename)
            if not state.group_to_keys[group_id]:
                del state.group_to_keys[group_id]
        allowed_groups_all = load_allowed_groups()
        if access_key in allowed_groups_all and group_id in allowed_groups_all[access_key]:
            del allowed_groups_all[access_key][group_id]
            save_allowed_groups(allowed_groups_all)
        await update.message.reply_text(f"Группа {group_name} (ID: {group_id}) удалена из разрешённых.")
    else:
        await update.message.reply_text("Группа не найдена в разрешённых.")
    return ConversationHandler.END

remove_group_handler = ConversationHandler(
    entry_points=[CommandHandler("remove_group", remove_group_start)],
    states={
        REMOVE_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_group_process)]
    },
    fallbacks=[]
)

async def list_groups(update: Update, context: CallbackContext) -> None:
    """
    Команда: /list_groups
    Выводит список разрешённых групп для аккаунта.
    """
    access_key = context.user_data.get("access_key")
    csv_filename = context.user_data.get("csv_filename")
    if not access_key or not csv_filename:
        await update.message.reply_text("Вы не авторизованы.")
        return
    groups = state.allowed_groups.get(csv_filename, {})
    if not groups:
        await update.message.reply_text("Нет разрешённых групп.")
        return
    message = "Разрешённые группы:\n" + "\n".join([f"ID: {gid}, Name: {gname}" for gid, gname in groups.items()])
    await update.message.reply_text(message)
