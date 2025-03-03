import logging
from telegram import Update
from telegram.ext import CallbackContext
from state import state
from groups_csv import load_allowed_groups, save_allowed_groups

logger = logging.getLogger(__name__)

async def add_group(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /add_group <group_id> <group_name>")
        return
    try:
        group_id = int(args[0])
        group_name = " ".join(args[1:])
    except Exception as e:
        await update.message.reply_text("Ошибка: неверный формат group_id.")
        return
    access_key = context.user_data.get("access_key")
    csv_filename = context.user_data.get("csv_filename")
    if not access_key or not csv_filename:
        await update.message.reply_text("Вы не авторизованы.")
        return
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


async def remove_group(update: Update, context: CallbackContext) -> None:
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: /remove_group <group_id>")
        return
    try:
        group_id = int(args[0])
    except Exception as e:
        await update.message.reply_text("Ошибка: неверный формат group_id.")
        return
    access_key = context.user_data.get("access_key")
    csv_filename = context.user_data.get("csv_filename")
    if not access_key or not csv_filename:
        await update.message.reply_text("Вы не авторизованы.")
        return
    if csv_filename in state.allowed_groups and group_id in state.allowed_groups[csv_filename]:
        group_name = state.allowed_groups[csv_filename].pop(group_id)
        # Обновляем global mapping для группы: удаляем csv_filename
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
