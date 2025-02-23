import logging
import re
import asyncio
import nest_asyncio
import pytz
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    CallbackContext,
    CommandHandler,
    CallbackQueryHandler
)
from google import genai

nest_asyncio.apply()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
group_titles = {}

TELEGRAM_BOT_TOKEN = "7479078489:AAGkMmNqXDOuYq18EaaITfyK0MA40nxZeOg"

# API key и модель для Gemini
# Глобальные переменные для управления сбором статистики
tracking_active = False
admin_chat_id = None

# Словари для хранения статистики, имен тем, идентификаторов сообщений и последнего номера
stats = {}           # ключ: (group_id, topic_id, phone), значение: {"started": datetime, "stopped": datetime, "downtime": timedelta}
topic_names = {}     # ключ: (group_id, topic_id), значение: имя темы
global_message_ids = {}  # ключ: group_id, значение: message_id отправленного (или отредактированного) сообщения
last_phone = {}         # ключ: (group_id, topic_id), значение: последний номер

def extract_event_info(text: str, default_topic_id: int) -> dict:
    prompt = (
        "Ты помощник по анализу текстов. Извлеки данные и выведи только JSON.\n"
        "- phone: номер телефона (номер может быть с +, но выводить нужно без плюса; если в сообщении указан только номер, то это номер), иначе null.\n"
        "- event: если в сообщении явно указано, что номер начал работать (например, 'встал', 'работает', '+') - верни 'started', "
        "если явно указано, что номер перестал работать (например, 'слетел', 'умер', '-') - верни 'stopped'. "
        "Если таких указаний нет, верни null.\n"
        "- event_time: время события в формате HH:MM, иначе null. Обращай внимание, что время может содержать опечатки, например '4.23', '1454', '14*34'. Если время не указано, оставь null.\n"
        "- topic_id: если в тексте есть 'id: 2', то выведи 2, иначе null.\n"
        "Пример правильного ответа:\n"
        "{\"phone\": \"79130000000\", \"event\": \"started\", \"event_time\": \"12:30\", \"topic_id\": 2}\n"
        "Если в сообщении отсутствуют явные указания на событие (например, 'замена', 'повтор', 'что с ним'), верни event как null."
    )

    full_prompt = prompt + "\nТекст: " + text

    try:
        client = genai.Client(api_key="AIzaSyDUeD5yRZ6fkRW1PYDd2oOVG9PrttcLs4A")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt
        )
        output_text = response.text.strip()

        # Попытка извлечь JSON из ответа
        json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(0)
        output_text = output_text.replace('```json', '').replace('```', '').strip()

        logger.info(f"Очищенный ответ Gemini: {output_text}")

        extracted = json.loads(output_text)

        # Нормализация номера телефона: оставляем только цифры и убираем ведущий плюс.
        if extracted.get("phone"):
            extracted["phone"] = re.sub(r'[^\d+]', '', extracted["phone"])
            extracted["phone"] = extracted["phone"].lstrip('+')

        # Поиск topic_id в тексте (например, "id: 2")
        topic_id_match = re.search(r'id:\s*(\d+)', text)
        extracted["topic_id"] = extracted.get("topic_id") or (
            int(topic_id_match.group(1)) if topic_id_match else default_topic_id
        )

        return extracted
    except Exception as e:
        logger.error(f"Ошибка при извлечении данных через Gemini API: {e}")
        return {"phone": None, "event": None, "event_time": None, "topic_id": default_topic_id}

def format_record(record: dict, phone: str) -> str:
    started_str = record.get("started").strftime("%H:%M") if record.get("started") else "-"
    stopped_str = record.get("stopped").strftime("%H:%M") if record.get("stopped") else "-"
    downtime = record.get("downtime")
    if downtime:
        total_minutes = int(downtime.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        downtime_str = f"{hours}:{minutes:02d}"
    else:
        downtime_str = "-"
    return f"{phone} | {started_str} | {stopped_str} | {downtime_str}"

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Статистика за сегодня", callback_data="daily_stats")],
        [InlineKeyboardButton("Стоп", callback_data="stop_tracking")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def update_global_message(group_id: int, group_title: str, context: CallbackContext) -> None:
    global admin_chat_id
    if not admin_chat_id:
        return
    lines = [f"Группа: {group_title}"]
    overall_total_seconds = 0
    overall_count = 0

    # Группируем записи по topic_id для данной группы
    topics = {}
    for (g_id, topic_id, phone), rec in stats.items():
        if g_id == group_id:
            topics.setdefault(topic_id, []).append((phone, rec))

    for tid in sorted(topics.keys()):
        # Выводим заголовок темы как "Topic id: <id>"
        lines.append(f"\nTopic id: {tid}")
        topic_lines = []
        topic_total_seconds = 0
        topic_count = 0
        for phone, rec in topics[tid]:
            topic_lines.append(format_record(rec, phone))
            if rec.get("downtime") is not None:
                topic_total_seconds += rec["downtime"].total_seconds()
                topic_count += 1
        topic_lines.sort()
        lines.extend(topic_lines)
        if topic_count:
            avg_seconds = topic_total_seconds / topic_count
            avg_hours = int(avg_seconds // 3600)
            avg_minutes = int((avg_seconds % 3600) // 60)
            lines.append(f"Среднее по пк - {avg_hours}:{avg_minutes:02d}")
            overall_total_seconds += topic_total_seconds
            overall_count += topic_count
        else:
            lines.append("Среднее по пк - 0:00")

    if overall_count:
        overall_avg = overall_total_seconds / overall_count
        overall_hours = int(overall_avg // 3600)
        overall_minutes = int((overall_avg % 3600) // 60)
    else:
        overall_hours, overall_minutes = 0, 0

    lines.append(f"\nСреднее по группе - {overall_hours}:{overall_minutes:02d}")
    final_message = "\n".join(lines)

    if group_id in global_message_ids:
        try:
            await context.bot.edit_message_text(
                chat_id=admin_chat_id,
                message_id=global_message_ids[group_id],
                text=final_message,
                reply_markup=get_main_keyboard()
            )
            logger.info(f"Обновлено глобальное сообщение для группы {group_id}")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения для группы {group_id}: {e}")
    else:
        try:
            sent_msg = await context.bot.send_message(
                chat_id=admin_chat_id,
                text=final_message,
                reply_markup=get_main_keyboard()
            )
            global_message_ids[group_id] = sent_msg.message_id
            logger.info(f"Создано сообщение для группы {group_id} с id {sent_msg.message_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения для группы {group_id}: {e}")

async def send_daily_stats(context: CallbackContext):
    global admin_chat_id, group_titles
    if not admin_chat_id:
        return
    groups = {}
    for (g_id, topic_id, phone), rec in stats.items():
        groups.setdefault(g_id, []).append((phone, rec))
    for g_id, records in groups.items():
        # Используем сохранённое название группы, если оно есть, иначе выводим id
        group_title = group_titles.get(g_id, str(g_id))
        lines = [f"Группа: {group_title}"]
        total_seconds = 0
        count = 0
        for phone, rec in records:
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
        lines.append(f"среднее время: {avg_hours}:{avg_minutes:02d}")
        message_text = "\n".join(lines)
        await context.bot.send_message(chat_id=admin_chat_id, text=message_text)



async def message_handler(update: Update, context: CallbackContext) -> None:
    global tracking_active, group_titles
    if not tracking_active:
        return

    if update.message and update.message.text:
        text = update.message.text.strip()
        message_sent = update.message.date.astimezone(pytz.timezone("Europe/Kiev"))
        chat = update.message.chat
        group_id = chat.id
        topic_id = update.message.message_thread_id if update.message.message_thread_id is not None else group_id

        # Сохраняем название группы, если оно есть
        if chat.title:
            group_titles[group_id] = chat.title

        # Если сообщение о создании темы – сохраняем имя темы
        global topic_names
        if update.message.forum_topic_created:
            topic_names[(group_id, topic_id)] = update.message.forum_topic_created.name
            logger.info(f"Сохранено имя темы: {update.message.forum_topic_created.name} для topic_id {topic_id}")

        logger.info(f"Получено сообщение в группе {group_id} ({chat.title or group_id}): {text}")

        # Если сообщение содержит только номер – запоминаем его
        if re.fullmatch(r'\+?\d+', text):
            phone_only = re.sub(r'[^\d]', '', text)
            last_phone[(group_id, topic_id)] = phone_only
            logger.info(f"Запомнен номер {phone_only} для темы {topic_id} группы {group_id}.")
            return

        extraction = await asyncio.to_thread(extract_event_info, text, topic_id)
        phone_extracted = extraction.get("phone")
        event = extraction.get("event")
        event_time_str = extraction.get("event_time")
        extracted_topic_id = extraction.get("topic_id")
        logger.info(f"Извлеченные данные: {extraction}")

        if phone_extracted:
            last_phone[(group_id, extracted_topic_id)] = phone_extracted

        if not event:
            logger.info(f"Сообщение не содержит явного события. Номер {phone_extracted} запомнен для темы {extracted_topic_id} группы {group_id}.")
            return

        if not event_time_str:
            event_time_str = message_sent.strftime("%H:%M")
            logger.info(f"Время не указано, используем время отправки: {event_time_str}")

        if event == "started" and not phone_extracted:
            if (group_id, extracted_topic_id) in last_phone:
                phone_extracted = last_phone[(group_id, extracted_topic_id)]
            else:
                logger.info("Сообщение 'started' не содержит номера и нет сохраненного номера, игнорирую.")
                return

        key = (group_id, extracted_topic_id, phone_extracted) if phone_extracted else None

        if event == "stopped":
            if not phone_extracted:
                candidate_key = None
                candidate_record = None
                for (g, tid, ph), rec in stats.items():
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

        record = stats.get(key, {})
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

        stats[key] = record
        group_title = chat.title if chat.title else str(group_id)
        await update_global_message(group_id, group_title, context)



async def start_tracking(update: Update, context: CallbackContext):
    global tracking_active, admin_chat_id, stats, global_message_ids
    tracking_active = True
    admin_chat_id = update.message.chat_id
    stats.clear()
    global_message_ids.clear()
    await update.message.reply_text(
        "Статистика запущена",
        reply_markup=get_main_keyboard()
    )

async def stop_tracking(update: Update, context: CallbackContext):
    global tracking_active
    tracking_active = False
    await update.message.reply_text("Статистика остановлена")

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == "stop_tracking":
        global tracking_active
        tracking_active = False
        await query.edit_message_text("Статистика остановлена")
    elif query.data == "daily_stats":
        await send_daily_stats(context)
        # Можно оставить клавиатуру в исходном сообщении, если требуется:
        await query.edit_message_reply_markup(reply_markup=get_main_keyboard())

async def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_tracking))
    app.add_handler(CommandHandler("stop", stop_tracking))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("Бот запущен")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
