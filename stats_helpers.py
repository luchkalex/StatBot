import asyncio
import logging
import re

import pytz
from datetime import datetime

from telegram import Update
import logging
import pytz
from datetime import datetime
from telegram.ext import CallbackContext
from keyboards import get_daily_stats_keyboard, get_group_stats_keyboard, get_stop_keyboard, get_start_keyboard
from state import state
from utils import extract_event_info
from utils_helpers import ensure_datetime, convert_to_datetime

logger = logging.getLogger(__name__)

def get_topic_link(group_id: int, topic_id: int) -> str:
    logger.debug("Генерация ссылки для группы %s, тема %s", group_id, topic_id)
    group_str = str(group_id)
    if group_str.startswith("-100"):
        chat_identifier = group_str[4:]
    else:
        chat_identifier = group_str
    link = f"https://t.me/c/{chat_identifier}/{topic_id}"
    logger.debug("Сгенерирована ссылка: %s", link)
    return link

def format_record(record: dict, phone: str) -> str:
    logger.debug("Форматирование записи для номера %s", phone)
    started = record.get("started")
    stopped = record.get("stopped")
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
    formatted = f"{phone} | {started_str} | {stopped_str} | {downtime_str}"
    logger.debug("Отформатированная запись: %s", formatted)
    return formatted

async def update_global_message(group_id: int, group_title: str, context: CallbackContext, view_mode: str = "grouped") -> None:
    csv_filename = context.user_data.get('csv_filename', 'stats.csv')
    admin_chat_ids = state.admin_chat_ids.get(csv_filename, set())
    if not admin_chat_ids:
        logger.warning("Не найдено chat_id для CSV файла %s", csv_filename)
        return

    logger.info("Обновление сообщения для группы '%s' для всех чатов (CSV '%s'): %s", group_title, csv_filename, admin_chat_ids)

    if view_mode == "grouped":
        lines = [f"Группа: {group_title}"]
        topics = {}
        unique_phones_today = set()
        standing_now = 0
        for (g_id, topic_id, phone), rec in state.stats.items():
            if g_id == group_id:
                topics.setdefault(topic_id, []).append((phone, rec))
                unique_phones_today.add(phone)
                if rec.get("started") and not rec.get("stopped"):
                    standing_now += 1
        topic_counter = 0
        for tid in sorted(topics.keys()):
            topic_counter += 1
            topic_link = get_topic_link(group_id, tid)
            lines.append(f"\n<b><a href='{topic_link}'>Тема: {topic_counter}</a></b>")
            topic_lines = []
            topic_total_seconds = 0
            topic_count = 0
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
                marker = " 🔴" if total_avg_minutes < 20 else " 🟠" if total_avg_minutes < 30 else ""
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
        daily_records = [(phone, rec) for (g_id, _, phone), rec in state.stats.items() if g_id == group_id]
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
        logger.error("Неверный режим отображения: %s", view_mode)
        return

    if csv_filename not in state.global_message_ids:
        state.global_message_ids[csv_filename] = {}
    for admin_chat_id in admin_chat_ids:
        global_msgs = state.global_message_ids[csv_filename]
        try:
            if admin_chat_id in global_msgs and group_id in global_msgs[admin_chat_id]:
                await context.bot.edit_message_text(
                    chat_id=admin_chat_id,
                    message_id=global_msgs[admin_chat_id][group_id],
                    text=final_message,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                logger.info("Обновлено сообщение в чате %s для группы '%s'", admin_chat_id, group_title)
            else:
                sent_msg = await context.bot.send_message(
                    chat_id=admin_chat_id,
                    text=final_message,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                if admin_chat_id not in global_msgs:
                    global_msgs[admin_chat_id] = {}
                global_msgs[admin_chat_id][group_id] = sent_msg.message_id
                logger.info("Создано сообщение в чате %s для группы '%s' с id %s", admin_chat_id, group_title, sent_msg.message_id)
        except Exception as e:
            logger.error("Ошибка при обновлении/отправке сообщения в чате %s для группы %s: %s", admin_chat_id, group_id, e)

async def send_grouped_stats(context: CallbackContext) -> None:
    logger.info("Отправка сгруппированной статистики")
    csv_filename = context.user_data.get('csv_filename', 'stats.csv')
    admin_chat_ids = state.admin_chat_ids.get(csv_filename, set())
    if not admin_chat_ids:
        logger.warning("Нет chat_id для CSV файла %s", csv_filename)
        return

    groups = {}
    for (group_id, topic_id, phone), rec in state.stats.items():
        groups.setdefault(group_id, {}).setdefault(topic_id, []).append((phone, rec))
    for g_id, topics in groups.items():
        group_title = state.group_titles.get(g_id, str(g_id))
        lines = [f"Группа: {group_title}"]
        topic_counter = 0
        for tid in sorted(topics.keys()):
            topic_counter += 1
            topic_link = get_topic_link(g_id, tid)
            lines.append(f"\n<b><a href='{topic_link}'>Тема: {topic_counter}</a></b>")
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
                total_avg_minutes = avg_hours * 60 + avg_minutes
                marker = " 🔴" if total_avg_minutes < 20 else " 🟠" if total_avg_minutes < 30 else ""
                lines.append(f"Среднее по пк - {avg_hours}:{avg_minutes:02d}{marker}")
            else:
                lines.append("Среднее по пк - 0:00")
        final_message = "\n".join(lines)
        keyboard = get_daily_stats_keyboard(g_id)
        if csv_filename not in state.global_message_ids:
            state.global_message_ids[csv_filename] = {}
        for admin_chat_id in admin_chat_ids:
            global_msgs = state.global_message_ids[csv_filename]
            try:
                if admin_chat_id in global_msgs and g_id in global_msgs[admin_chat_id]:
                    await context.bot.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=global_msgs[admin_chat_id][g_id],
                        text=final_message,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    logger.info("Обновлено сообщение в чате %s для группы %s", admin_chat_id, g_id)
                else:
                    sent_msg = await context.bot.send_message(
                        chat_id=admin_chat_id,
                        text=final_message,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    if admin_chat_id not in global_msgs:
                        global_msgs[admin_chat_id] = {}
                    global_msgs[admin_chat_id][g_id] = sent_msg.message_id
                    logger.info("Создано сообщение в чате %s для группы %s с id %s", admin_chat_id, g_id, sent_msg.message_id)
            except Exception as e:
                logger.error("Ошибка при обновлении/отправке сообщения в чате %s для группы %s: %s", admin_chat_id, g_id, e)

async def start_tracking(context: CallbackContext, update=None) -> None:
    logger.info("Запуск отслеживания статистики")
    csv_filename = context.user_data.get('csv_filename', 'stats.csv')
    chat_id = None
    if update:
        if update.message:
            chat_id = update.message.chat_id
        elif update.callback_query and update.callback_query.message:
            chat_id = update.callback_query.message.chat_id
    if chat_id:
        if csv_filename not in state.admin_chat_ids:
            state.admin_chat_ids[csv_filename] = set()
        state.admin_chat_ids[csv_filename].add(chat_id)
        logger.info("Добавлен chat_id %s для CSV '%s'", chat_id, csv_filename)
    state.tracking_active = True
    state.stats.clear()
    state.load_from_csv(csv_filename)
    await send_grouped_stats(context)
    if update:
        if update.message:
            await update.message.reply_text("Статистика запущена", reply_markup=get_stop_keyboard())
        elif update.callback_query:
            await update.callback_query.message.reply_text("Статистика запущена", reply_markup=get_stop_keyboard())
    logger.info("Отслеживание статистики запущено")

async def stop_tracking(update, context: CallbackContext) -> None:
    logger.info("Остановка отслеживания статистики")
    csv_filename = context.user_data.get('csv_filename', 'stats.csv')
    chat_id = None
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    if chat_id and csv_filename in state.admin_chat_ids and chat_id in state.admin_chat_ids[csv_filename]:
        state.admin_chat_ids[csv_filename].remove(chat_id)
        logger.info("Удалён chat_id %s для CSV '%s'", chat_id, csv_filename)
    state.tracking_active = False
    if update:
        if update.message:
            await update.message.reply_text("Статистика остановлена", reply_markup=get_start_keyboard())
        elif update.callback_query:
            await update.callback_query.message.reply_text("Статистика остановлена", reply_markup=get_start_keyboard())
    logger.info("Отслеживание статистики остановлено")

async def button_handler(update, context: CallbackContext) -> None:
    logger.info("Обработка нажатия кнопки")
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "start_tracking":
        await start_tracking(context, update)
    elif data == "stop_tracking":
        await stop_tracking(update, context)
    elif data.startswith("group_stats_"):
        group_id = int(data.split('_')[2])
        group_title = state.group_titles.get(group_id, str(group_id))
        await update_global_message(group_id, group_title, context, view_mode="grouped")
    elif data.startswith("daily_stats_"):
        group_id = int(data.split('_')[2])
        group_title = state.group_titles.get(group_id, str(group_id))
        await update_global_message(group_id, group_title, context, view_mode="daily")


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
        f"\n\nПолучено {'отредактированное' if update.edited_message else 'новое'} сообщение в группе {group_id} ({chat.title or group_id}): {text}")

    # Удаляем только символы '-', '+', '(', ')', и пробелы
    phone_candidate = re.sub(r'[-+() ]', '', text)

    # Если после очистки остались только цифры и длина строки больше 8
    if phone_candidate.isdigit() and len(phone_candidate) > 8:
        state.last_phone[(group_id, topic_id)] = phone_candidate
        logger.info(f"Запомнен номер {phone_candidate} для темы {topic_id} группы {group_id}.\n\n")
        return

    extraction = await asyncio.to_thread(extract_event_info, text, topic_id, message_sent)
    logger.info(f"Извлеченные данные: {extraction}")

    # Если извлеченные данные не содержат полезной информации, игнорируем сообщение
    if extraction.get("phone") is None and not extraction.get("started", False) and not extraction.get("stopped",
                                                                                                       False):
        logger.info(f"Сообщение не содержит полезной информации и будет проигнорировано.\n\n")
        return
    # Если извлеченные данные содержат только номер запоминаем его
    if not extraction.get("phone") is None and not extraction.get("started", False) and not extraction.get(
            "stopped", False):
        phone_extracted = extraction.get("phone")
        state.last_phone[(group_id, topic_id)] = phone_extracted
        logger.info(f"Запомнен номер {phone_extracted} для темы {topic_id} группы {group_id}.")
        return

    # Присваиваем переменным значение
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
    logger.info(f"Запрос на сохранение в CSV {context.user_data.get('csv_filename', 'stats.csv')}")
    state.save_to_csv(context.user_data.get('csv_filename', 'stats.csv'))
