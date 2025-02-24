# handlers.py
import re
import asyncio
import pytz
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from utils import extract_event_info, format_record
from state import state

logger = logging.getLogger(__name__)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Стоп", callback_data="stop_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def update_global_message(group_id: int, group_title: str, context: CallbackContext, view_mode: str = "grouped") -> None:
    if not state.admin_chat_id:
        return
    if view_mode == "grouped":
        lines = [f"Группа: {group_title}"]
        overall_total_seconds = 0
        overall_count = 0
        topics = {}
        for (g_id, topic_id, phone), rec in state.stats.items():
            if g_id == group_id:
                topics.setdefault(topic_id, []).append((phone, rec))
        for tid in sorted(topics.keys()):
            lines.append(f"\nTopic id: {tid}")
            topic_lines = []
            topic_total_seconds = 0
            topic_count = 0
            for phone, rec in topics[tid]:
                topic_lines.append(format_record(rec, phone))
                if rec.get("downtime"):
                    topic_total_seconds += rec["downtime"].total_seconds()
                    topic_count += 1
            topic_lines.sort()
            lines.extend(topic_lines)
            if topic_count:
                avg_seconds = topic_total_seconds / topic_count
                avg_hours = int(avg_seconds // 3600)
                avg_minutes = int((avg_seconds % 3600) // 60)
                lines.append(f"Среднее по теме - {avg_hours}:{avg_minutes:02d}")
                overall_total_seconds += topic_total_seconds
                overall_count += topic_count
            else:
                lines.append("Среднее по теме - 0:00")
        if overall_count:
            overall_avg = overall_total_seconds / overall_count
            overall_hours = int(overall_avg // 3600)
            overall_minutes = int((overall_avg % 3600) // 60)
            lines.append(f"\nСреднее по группе - {overall_hours}:{overall_minutes:02d}")
        else:
            lines.append("\nСреднее по группе - 0:00")
        final_message = "\n".join(lines)
        keyboard = get_daily_stats_keyboard(group_id)
    elif view_mode == "daily":
        lines = [f"Группа: {group_title}"]
        total_seconds = 0
        count = 0
        for (g_id, _, phone), rec in state.stats.items():
            if g_id == group_id:
                lines.append(format_record(rec, phone))
                if rec.get("downtime"):
                    total_seconds += rec["downtime"].total_seconds()
                    count += 1
        if count:
            avg_seconds = total_seconds / count
            avg_hours = int(avg_seconds // 3600)
            avg_minutes = int((avg_seconds % 3600) // 60)
            lines.append(f"\nСреднее по группе: {avg_hours}:{avg_minutes:02d}")
        else:
            lines.append("\nСреднее по группе: 0:00")
        final_message = "\n".join(lines)
        keyboard = get_group_stats_keyboard(group_id)
    else:
        return
    
    try:
        if group_id in state.global_message_ids:
            await context.bot.edit_message_text(
                chat_id=state.admin_chat_id,
                message_id=state.global_message_ids[group_id],
                text=final_message,
                reply_markup=keyboard
            )
            logger.info(f"Обновлено сообщение для группы {group_id}")
        else:
            sent_msg = await context.bot.send_message(
                chat_id=state.admin_chat_id,
                text=final_message,
                reply_markup=keyboard
            )
            state.global_message_ids[group_id] = sent_msg.message_id
            logger.info(f"Создано сообщение для группы {group_id} с id {sent_msg.message_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании сообщения для группы {group_id}: {e}")

async def send_daily_stats(context: CallbackContext, group_id: int):
    if not state.admin_chat_id:
        return
    lines = [f"Группа: {state.group_titles.get(group_id, str(group_id))}"]
    total_seconds = 0
    count = 0
    for (g_id, _, phone), rec in state.stats.items():
        if g_id == group_id:
            lines.append(format_record(rec, phone))
            if rec.get("downtime"):
                total_seconds += rec["downtime"].total_seconds()
                count += 1
    if count:
        avg_seconds = total_seconds / count
        avg_hours = int(avg_seconds // 3600)
        avg_minutes = int((avg_seconds % 3600) // 60)
    else:
        avg_hours, avg_minutes = 0, 0
    lines.append(f"Среднее по группе: {avg_hours}:{avg_minutes:02d}")
    final_message = "\n".join(lines)
    keyboard = get_group_stats_keyboard(group_id)
    try:
        if group_id in state.global_message_ids:
            await context.bot.edit_message_text(
                chat_id=state.admin_chat_id,
                message_id=state.global_message_ids[group_id],
                text=final_message,
                reply_markup=keyboard
            )
            logger.info(f"Обновлено сообщение для группы {group_id}")
        else:
            sent_msg = await context.bot.send_message(
                chat_id=state.admin_chat_id,
                text=final_message,
                reply_markup=keyboard
            )
            state.global_message_ids[group_id] = sent_msg.message_id
            logger.info(f"Создано сообщение для группы {group_id} с id {sent_msg.message_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании сообщения для группы {group_id}: {e}")

async def message_handler(update: Update, context: CallbackContext) -> None:
    if not state.tracking_active:
        return
    if update.message and update.message.text:
        text = update.message.text.strip()
        message_sent = update.message.date.astimezone(pytz.timezone("Europe/Kiev"))
        chat = update.message.chat
        group_id = chat.id
        topic_id = update.message.message_thread_id if update.message.message_thread_id is not None else group_id
        if chat.title:
            state.group_titles[group_id] = chat.title
        if update.message.forum_topic_created:
            state.topic_names[(group_id, topic_id)] = update.message.forum_topic_created.name
            logger.info(f"Сохранено имя темы: {update.message.forum_topic_created.name} для topic_id {topic_id}")
        logger.info(f"Получено сообщение в группе {group_id} ({chat.title or group_id}): {text}")
        if re.fullmatch(r'\+?\d+', text):
            phone_only = re.sub(r'[^\d]', '', text)
            state.last_phone[(group_id, topic_id)] = phone_only
            logger.info(f"Запомнен номер {phone_only} для темы {topic_id} группы {group_id}.")
            return
        extraction = await asyncio.to_thread(extract_event_info, text, topic_id)
        phone_extracted = extraction.get("phone")
        event = extraction.get("event")
        event_time_str = extraction.get("event_time")
        extracted_topic_id = extraction.get("topic_id")
        logger.info(f"Извлеченные данные: {extraction}")
        if phone_extracted:
            state.last_phone[(group_id, extracted_topic_id)] = phone_extracted
        if not event:
            logger.info(f"Сообщение не содержит явного события. Номер {phone_extracted} запомнен для темы {extracted_topic_id} группы {group_id}.")
            return
        if not event_time_str:
            event_time_str = message_sent.strftime("%H:%M")
            logger.info(f"Время не указано, используем время отправки: {event_time_str}")
        if event == "started" and not phone_extracted:
            if (group_id, extracted_topic_id) in state.last_phone:
                phone_extracted = state.last_phone[(group_id, extracted_topic_id)]
            else:
                logger.info("Сообщение 'started' не содержит номера и нет сохраненного номера, игнорирую.")
                return
        key = (group_id, extracted_topic_id, phone_extracted) if phone_extracted else None
        if event == "stopped":
            if not phone_extracted:
                candidate_key = None
                candidate_record = None
                for (g, tid, ph), rec in state.stats.items():
                    if g == group_id and tid == extracted_topic_id and rec.get("started") and rec.get("stopped") is None:
                        if candidate_record is None or rec["started"] > candidate_record["started"]:
                            candidate_key = (g, tid, ph)
                            candidate_record = rec
                if candidate_record is None:
                    logger.info("Нет записи 'started' для события 'stopped'")
                    return
                key = candidate_key
                phone_extracted = candidate_key[2]
        try:
            reported_time = datetime.strptime(event_time_str, "%H:%M").time()
        except Exception as e:
            logger.error(f"Ошибка парсинга времени '{event_time_str}': {e}")
            return
        reported_datetime = datetime.combine(message_sent.date(), reported_time)
        diff_hours = reported_datetime.hour - message_sent.hour
        actual_event_time = reported_datetime - timedelta(hours=diff_hours) if diff_hours > 0 else reported_datetime
        record = state.stats.get(key, {})
        if event == "started":
            record["started"] = actual_event_time
            record["stopped"] = None
            record["downtime"] = None
        elif event == "stopped":
            if record.get("started"):
                record["stopped"] = actual_event_time
                record["downtime"] = record["stopped"] - record["started"]
            else:
                logger.info("Нет записи 'started' для события 'stopped'")
                return
        state.stats[key] = record
        group_title = chat.title if chat.title else str(group_id)
        await update_global_message(group_id, group_title, context)
        state.save_to_csv()  # Сохранение статистики в CSV файл




async def send_grouped_stats(context: CallbackContext):
    logger.info(f"Grouped stats")
    if not state.admin_chat_id:
        return
    groups = {}
    for (group_id, topic_id, phone), rec in state.stats.items():
        groups.setdefault(group_id, {}).setdefault(topic_id, []).append((phone, rec))
    for g_id, topics in groups.items():
        group_title = state.group_titles.get(g_id, str(g_id))
        lines = [f"Группа: {group_title}"]
        overall_total_seconds = 0
        overall_count = 0
        for tid in sorted(topics.keys()):
            lines.append(f"\nTopic id: {tid}")
            topic_lines = []
            topic_total_seconds = 0
            topic_count = 0
            for phone, rec in topics[tid]:
                topic_lines.append(format_record(rec, phone))
                if rec.get("downtime"):
                    topic_total_seconds += rec["downtime"].total_seconds()
                    topic_count += 1
            topic_lines.sort()
            lines.extend(topic_lines)
            if topic_count:
                avg_seconds = topic_total_seconds / topic_count
                avg_hours = int(avg_seconds // 3600)
                avg_minutes = int((avg_seconds % 3600) // 60)
                lines.append(f"Среднее по теме - {avg_hours}:{avg_minutes:02d}")
                overall_total_seconds += topic_total_seconds
                overall_count += topic_count
            else:
                lines.append("Среднее по теме - 0:00")
        if overall_count:
            overall_avg = overall_total_seconds / overall_count
            overall_hours = int(overall_avg // 3600)
            overall_minutes = int((overall_avg % 3600) // 60)
            lines.append(f"\nСреднее по группе - {overall_hours}:{overall_minutes:02d}")
        else:
            lines.append("\nСреднее по группе - 0:00")
        final_message = "\n".join(lines)
        keyboard = get_daily_stats_keyboard(g_id)  # Измените на get_group_stats_keyboard(g_id)
        try:
            sent_msg = await context.bot.send_message(
                chat_id=state.admin_chat_id,
                text=final_message,
                reply_markup=keyboard
            )
            state.global_message_ids[g_id] = sent_msg.message_id
            logger.info(f"Создано сообщение для группы {g_id} с id {sent_msg.message_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения для группы {g_id}: {e}")





#--------------------------------BUTTON HANDLERS-------------------------------------
async def start_tracking(update: Update, context: CallbackContext):
    state.tracking_active = True

    # Используем update.message, если это не callback_query, а обычное сообщение
    if update.message:
        state.admin_chat_id = update.message.chat_id
    elif update.callback_query and update.callback_query.message:
        state.admin_chat_id = update.callback_query.message.chat_id
    else:
        logger.error("Ошибка: не удалось получить chat_id.")
        return

    state.stats.clear()
    state.global_message_ids.clear()
    state.load_from_csv()  # Загрузка статистики из CSV файла

    # Отправка всех имеющихся данных в виде группировки по темам
    await send_grouped_stats(context)

    # Отправить новое сообщение с кнопкой "Стоп"
    await update.message.reply_text(
        "Статистика запущена",
        reply_markup=get_stop_keyboard()  # Кнопка "Стоп"
    ) if update.message else await update.callback_query.message.reply_text(
        "Статистика запущена",
        reply_markup=get_stop_keyboard()  # Кнопка "Стоп"
    )


async def stop_tracking(update: Update, context: CallbackContext):
    state.tracking_active = False
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(
                text="Статистика остановлена",
                reply_markup=get_start_keyboard()
            )
            logger.info("Обновлено глобальное сообщение: Статистика остановлена")
        except Exception as e:
            logger.error(f"Ошибка при обновлении глобального сообщения: {e}")
    else:
        await update.message.reply_text("Статистика остановлена", reply_markup=get_start_keyboard())


async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "start_tracking":
        # Обрабатываем нажатие кнопки "Старт"
        await start_tracking(update, context)  # Запускаем отслеживание
    elif query.data == "stop_tracking":
        await stop_tracking(update, context)  # Останавливаем отслеживание
    elif query.data.startswith("group_stats_"):
        group_id = int(query.data.split('_')[2])
        group_title = state.group_titles.get(group_id, str(group_id))
        await update_global_message(group_id, group_title, context, view_mode="grouped")
    elif query.data.startswith("daily_stats_"):
        group_id = int(query.data.split('_')[2])
        group_title = state.group_titles.get(group_id, str(group_id))
        await update_global_message(group_id, group_title, context, view_mode="daily")


def get_stop_keyboard():
    keyboard = [
        [InlineKeyboardButton("Стоп", callback_data="stop_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_group_stats_keyboard(group_id):
    keyboard = [
        [InlineKeyboardButton("Статистика по пк", callback_data=f"group_stats_{group_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_daily_stats_keyboard(group_id):
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data=f"daily_stats_{group_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_start_keyboard():
    logger.info(f"start keyboard")
    keyboard = [
        [InlineKeyboardButton("Старт", callback_data="start_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)