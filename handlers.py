# handlers.py
import re
import asyncio
import pytz
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from utils import extract_event_info
from state import state

logger = logging.getLogger(__name__)


def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Стоп", callback_data="stop_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)


# Функция для проверки и преобразования значения в datetime
def ensure_datetime(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%H:%M")  # Попробуем преобразовать строку в datetime
        except ValueError:
            return None  # Если не удается преобразовать, вернем None
    elif isinstance(value, datetime):
        return value  # Если уже datetime, просто возвращаем его
    return None  # Если значение не строка и не datetime, возвращаем None

async def update_global_message(group_id: int, group_title: str, context: CallbackContext,
                                view_mode: str = "grouped") -> None:
    if not state.admin_chat_id:
        return
    if view_mode == "grouped":
        lines = [f"Группа: {group_title}"]
        overall_total_seconds = 0
        overall_count = 0
        topics = {}

        unique_phones_today = set()
        standing_now = 0

        for (g_id, topic_id, phone), rec in state.stats.items():
            if g_id == group_id:
                topics.setdefault(topic_id, []).append((phone, rec))
                unique_phones_today.add(phone)
                if rec.get("started") and not rec.get("stopped"):
                    standing_now += 1

        for tid in sorted(topics.keys()):
            lines.append(f"\nTopic id: {tid}")
            topic_lines = []
            topic_total_seconds = 0
            topic_count = 0

            # Преобразуем все значения в 'started' в datetime перед сортировкой
            sorted_entries = sorted(topics[tid], key=lambda item: ensure_datetime(item[1].get("started")))

            for phone, rec in sorted_entries:
                topic_lines.append(format_record(rec, phone))
                if rec.get("downtime"):
                    topic_total_seconds += rec["downtime"].total_seconds()
                    topic_count += 1
            lines.extend(topic_lines)
            if topic_count:
                avg_seconds = topic_total_seconds / topic_count
                avg_hours = int(avg_seconds // 3600)
                avg_minutes = int((avg_seconds % 3600) // 60)
                total_avg_minutes = avg_hours * 60 + avg_minutes
                marker = ""
                if total_avg_minutes < 20:
                    marker = " 🔴"
                elif total_avg_minutes < 30:
                    marker = " 🟠"
                lines.append(f"Среднее по пк - {avg_hours}:{avg_minutes:02d}{marker}")
            else:
                lines.append("Среднее по пк - 0:00")

        lines.append(f"\n\nПоставили: {len(unique_phones_today)}")
        lines.append(f"Стоят сейчас: {standing_now}")

        final_message = "\n".join(lines)
        keyboard = get_daily_stats_keyboard(group_id)

    elif view_mode == "daily":
        lines = [f"Группа: {group_title}"]
        total_seconds = 0
        count = 0
        unique_phones_today = set()
        standing_now = 0

        daily_records = [
            (phone, rec)
            for (g_id, _, phone), rec in state.stats.items()
            if g_id == group_id
        ]

        # Сортируем по времени 'started', преобразуя значения в datetime
        daily_sorted = sorted(daily_records, key=lambda item: ensure_datetime(item[1].get("started")))

        for phone, rec in daily_sorted:
            lines.append(format_record(rec, phone))
            if rec.get("downtime"):
                total_seconds += rec["downtime"].total_seconds()
                count += 1
            unique_phones_today.add(phone)
            if rec.get("started") and not rec.get("stopped"):
                standing_now += 1

        if count:
            avg_seconds = total_seconds / count
            avg_hours = int(avg_seconds // 3600)
            avg_minutes = int((avg_seconds % 3600) // 60)
        else:
            avg_hours, avg_minutes = 0, 0

        lines.append(f"Среднее по группе: {avg_hours}:{avg_minutes:02d}")
        lines.append(f"\nПоставили: {len(unique_phones_today)}")
        lines.append(f"Стоят сейчас: {standing_now}")

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



async def message_handler(update: Update, context: CallbackContext) -> None:
    if not state.tracking_active:
        return
    new_message = None
    if update.edited_message and update.edited_message.text:
        new_message = update.edited_message
    elif update.message and update.message.text:
        new_message = update.message

    # Если нет текста в сообщении или отредактированном сообщении, выходим
    if not new_message:
        return

    # Теперь у нас есть новое сообщение или отредактированное сообщение в переменной new_message
    text = new_message.text.strip()
    message_sent = new_message.date.astimezone(pytz.timezone("Europe/Kiev"))
    chat = new_message.chat
    group_id = chat.id
    topic_id = new_message.message_thread_id if new_message.message_thread_id is not None else group_id
    if chat.title:
        state.group_titles[group_id] = chat.title
    if new_message.forum_topic_created:
        state.topic_names[(group_id, topic_id)] = new_message.forum_topic_created.name
        logger.info(f"Сохранено имя темы: {new_message.forum_topic_created.name} для topic_id {topic_id}")

    logger.info(
        f"Получено {'отредактированное' if update.edited_message else 'новое'} сообщение в группе {group_id} ({chat.title or group_id}): {text}")

    # Удаляем только символы '-', '+', '(', ')', и пробелы
    phone_candidate = re.sub(r'[-+() ]', '', text)

    # Если после очистки остались только цифры и длина строки больше 8
    if phone_candidate.isdigit() and len(phone_candidate) > 8:
        state.last_phone[(group_id, topic_id)] = phone_candidate
        logger.info(f"Запомнен номер {phone_candidate} для темы {topic_id} группы {group_id}.")
        return

    extraction = await asyncio.to_thread(extract_event_info, text, topic_id, message_sent)
    logger.info(f"Извлеченные данные: {extraction}")

    # Если извлеченные данные не содержат полезной информации, игнорируем сообщение
    if extraction.get("phone") is None and not extraction.get("started", False) and not extraction.get("stopped",
                                                                                                       False):
        logger.info(f"Сообщение не содержит полезной информации и будет проигнорировано.")
        return
    # Если извлеченные данные содержат только номер запоминаем его
    if not extraction.get("phone") is None and not extraction.get("started", False) and not extraction.get(
            "stopped", False):
        phone_extracted = extraction.get("phone")
        state.last_phone[(group_id, topic_id)] = phone_extracted
        logger.info(f"Запомнен номер {phone_extracted} для темы {topic_id} группы {group_id}.")
        return

    phone_extracted = extraction.get("phone")
    started_flag = extraction.get("started", False)
    stopped_flag = extraction.get("stopped", False)
    started_time_str = extraction.get("started_time")
    stopped_time_str = extraction.get("stopped_time")
    extracted_topic_id = extraction.get("topic_id")

    if phone_extracted:
        state.last_phone[(group_id, extracted_topic_id)] = phone_extracted

    # Если номер не указан, пробуем взять последний запомненный номер для темы
    if not phone_extracted and (started_flag or stopped_flag):
        if (group_id, extracted_topic_id) in state.last_phone:
            phone_extracted = state.last_phone[(group_id, extracted_topic_id)]
        else:
            logger.info(f"Нет номера для события в теме {extracted_topic_id} группы {group_id}.")
            return

    key = (group_id, extracted_topic_id, phone_extracted)


    record = state.stats.get(key, {})
    # Обработка события "встал"
    if started_flag:
        record["started"] = started_time_str
        record["stopped"] = None
        record["downtime"] = None

    # Обработка события "слетел"
    if stopped_flag:
        if record.get("started"):
            record["stopped"] = stopped_time_str
            # Преобразуем 'started' и 'stopped' в datetime перед вычитанием
            started_time = convert_to_datetime(record.get("started"))
            stopped_time = convert_to_datetime(record.get("stopped"))

            # Если обе переменные стали datetime, вычисляем downtime
            if started_time and stopped_time:
                record["downtime"] = stopped_time - started_time
            else:
                record["downtime"] = None  # Если одно из значений не удалось преобразовать в datetime

        else:
            # Если записи с событием "встал" нет, ищем подходящую запись по теме
            candidate_key = None
            candidate_record = None
            for (g, tid, ph), rec in state.stats.items():
                if g == group_id and tid == extracted_topic_id and rec.get("started") and rec.get("stopped") is None:
                    if candidate_record is None or rec["started"] > candidate_record["started"]:
                        candidate_key = (g, tid, ph)
                        candidate_record = rec
            if candidate_record is None:
                logger.info("Нет записи 'встал' для события 'слетел'")
                return
            key = candidate_key
            record = candidate_record
            record["stopped"] = stopped_time_str
            record["downtime"] = record["stopped"] - record["started"]

    state.stats[key] = record
    group_title = chat.title if chat.title else str(group_id)
    await update_global_message(group_id, group_title, context)
    state.save_to_csv()


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
                # Вычисляем общее количество минут
                total_avg_minutes = avg_hours * 60 + avg_minutes
                # Определяем эмодзи в зависимости от среднего времени
                marker = ""
                if total_avg_minutes < 20:
                    marker = " 🔴"
                elif total_avg_minutes < 30:
                    marker = " 🟠"
                lines.append(f"Среднее по пк - {avg_hours}:{avg_minutes:02d}{marker}")
            else:
                lines.append("Среднее по пк - 0:00")
        if overall_count:
            overall_avg = overall_total_seconds / overall_count
            overall_hours = int(overall_avg // 3600)
            overall_minutes = int((overall_avg % 3600) // 60)
            # lines.append(f"\nСреднее по группе - {overall_hours}:{overall_minutes:02d}")
        # else:
        #   lines.append("\nСреднее по группе - 0:00")
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


AUTHORIZED_USERS = [6546400704]  # Пример разрешённых user_id


# --------------------------------BUTTON HANDLERS-------------------------------------
async def start_tracking(update: Update, context: CallbackContext):
    # Если это callback_query (нажатие кнопки), используем query
    if update.callback_query:
        user_id = update.callback_query.from_user.id  # Получаем user_id из callback_query
    elif update.message:
        user_id = update.message.from_user.id  # Получаем user_id из message
    else:
        return  # Если update не содержит ни message, ни callback_query, выходим из функции

    # Проверка авторизации
    if user_id not in AUTHORIZED_USERS:
        await update.callback_query.message.reply_text(
            "У вас нет доступа к этому боту.") if update.callback_query else await update.message.reply_text(
            "У вас нет доступа к этому боту.")
        return  # Прекращаем выполнение, если пользователь не авторизован
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


from datetime import datetime

def convert_to_datetime(value):
    if isinstance(value, str):
        try:
            time_part = datetime.strptime(value, "%H:%M").time()
            now = datetime.now(pytz.timezone("Europe/Kiev"))   # или используйте нужный часовой пояс, например: datetime.now(pytz.timezone("Europe/Kiev"))
            return datetime.combine(now.date(), time_part)
        except ValueError:
            return None
    elif isinstance(value, datetime):
        return value
    return None



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
        [InlineKeyboardButton("Статистика по группе", callback_data=f"daily_stats_{group_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_start_keyboard():
    logger.info(f"start keyboard")
    keyboard = [
        [InlineKeyboardButton("Старт", callback_data="start_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_record(record: dict, phone: str) -> str:
    started = record.get("started")
    stopped = record.get("stopped")

    # Преобразуем время, если это строка
    started = convert_to_datetime(started) if isinstance(started, str) else started
    stopped = convert_to_datetime(stopped) if isinstance(stopped, str) else stopped

    started_str = started.strftime("%H:%M") if started else "-"
    stopped_str = stopped.strftime("%H:%M") if stopped else "-"

    downtime = record.get("downtime")
    if downtime:
        total_minutes = int(downtime.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        downtime_str = f"{hours}:{minutes:02d}"
    else:
        downtime_str = "-"

    return f"{phone} | {started_str} | {stopped_str} | {downtime_str}"
