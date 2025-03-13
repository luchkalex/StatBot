# utils.txt
import re
import json
import logging
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_API_KEY_SECONDARY

logger = logging.getLogger(__name__)

def extract_event_info(text: str, default_topic_id: int, message_sent_time) -> dict:
    prompt = (

        """
        You are a text analysis assistant. Extract the data and output only JSON.
        A text in Russian language and Message sending time in the format 2025-02-27 17:56:02+02:00 will be provided.

        phone: phone number (the number may include a + or be in the format +7 995 488-58-59, but it should be output without the + and any separators; if only a number is specified in the message, then it is the number), otherwise null.
    
        started: true, if the message explicitly states that the number has started working (e.g., 'встал', 'работает', 'зашел', '+ time' (if just '+' without anything then false)) (also consider typos (if u see that u don't understand this world try to guess typo) and transliteration like 'вслат', 'стлоит', 'сашел', 'вхлд' 'vstal' 'zashel' etc.), otherwise e.g. ('ошибка' 'новый' 'этот') false. If 'встал' or similar is followed by a question, e.g., 'работает?', 'встал?' then False.
    
        stopped: true, if the message explicitly states that the number has stopped working (e.g., 'слетел', 'умер', '- time' (if just '-' without anything then false), '#СЛЕТ') (also consider typos (if u see that u don't understand this world try to guess typo) and transliteration like 'стел', 'стелел', 'slet', 'sletel' etc.), otherwise false. If 'слетел' or similar is followed by a question, e.g., 'слет?', 'минус?', then False. but if something is following like 'слет можно новый?' it is true and questions is about new number and not about stopped
    
        started_time: the time of the started event usually written after specifying an event in HH:MM format, if specified (the number may include typos like '1200', '12^00', '12.00', '12/00', '12 00', etc.), otherwise message time sent in format HH:MM.
    
        stopped_time: the time of the stopped event usually written after specifying an event in HH:MM format, if specified (the number may include typos like '1200', '12^00', '12.00', '12/00', '12 00', etc.), otherwise message time sent in format HH:MM.
    
        topic_id: if the text contains 'id: 2', then output 2, otherwise null.
    
        Additional notes: 
        1. If there are simply 4 digits, e.g., 'встал 1122', recognize this as time 11:22. There may be messages with both events specified, e.g., '+ 1150 - 1155', which should be recognized as two events: started 11:50 and stopped 11:55.
        2. Return only one JSON for the number. If there is no number but there are entry and exit times, return the times for an empty number with started true and stopped true.
        After creating the JSON, double-check to ensure there is only one entry for one phone, even if it is none.
        3. the message can be like 'встал - 21:00' this should be interpreted as started time 21:00, and NOT as stopped time
        4. the message can be like 'начал грузить и вылет' or 'встал и сразу слетел' should be recognized as started: false stopped: false
        
        Example of a correct response:
        {"phone": "79954885859", "started": true, "stopped": true, "started_time": "12:30", "stopped_time": "12:40", "topic_id": 2}
        
        Example of an INCORRECT response (do not send multiple entries):
        [
            {
                "phone": "79954885859",
                "started": False,
                "stopped": False,
                "started_time": None,
                "stopped_time": None,
                "topic_id": None
            },
            {
                "phone": None,
                "started": True,
                "stopped": True,
                "started_time": "12:30",
                "stopped_time": "12:40",
                "topic_id": None
            }
        ]
        
        if you got json like this then combine these records into one
        {
                "phone": 79954885859,
                "started": True,
                "stopped": True,
                "started_time": "12:30",
                "stopped_time": "12:40",
                "topic_id": None
            }
        """
    )
    full_prompt = prompt + f"\nТекст: " + text + f"\nВремя отправки сообщения: {message_sent_time}"
    logger.info(f"Сообщение для LLM: {text} {message_sent_time}")
    # Список ключей для попытки использования
    gemini_keys = [GEMINI_API_KEY, GEMINI_API_KEY_SECONDARY]
    for key in gemini_keys:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=full_prompt)
            output_text = response.text.strip()
            json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
            if json_match:
                output_text = json_match.group(0)
            output_text = output_text.replace('```json', '').replace('```', '').strip()
            logger.info(f"Очищенный ответ Gemini: {output_text}")
            extracted = json.loads(output_text)
            if extracted.get("phone"):
                extracted["phone"] = re.sub(r'[^\d+]', '', extracted["phone"]).lstrip('+')
            topic_id_match = re.search(r'id:\s*(\d+)', text)
            extracted["topic_id"] = extracted.get("topic_id") or (int(topic_id_match.group(1)) if topic_id_match else default_topic_id)
            # Гарантируем, что значения started и stopped – булевы
            extracted["started"] = bool(extracted.get("started"))
            extracted["stopped"] = bool(extracted.get("stopped"))
            new_started, new_stopped = adjust_times(
                extracted["started"],
                extracted["stopped"],
                extracted["started_time"],
                extracted["stopped_time"],
                message_sent_time
            )

            extracted["started_time"] = new_started
            extracted["stopped_time"] = new_stopped
            return extracted
        except Exception as e:
            err_msg = str(e).lower()
            logger.error(f"Ошибка при запросе с ключом {key}: {e}")
            logger.info(f"Попытка использовать следующий Gemini API ключ вместо {key}")
            continue

    # Если ни один ключ не сработал, возвращаем значения по умолчанию
    return {
        "phone": None,
        "started": False,
        "stopped": False,
        "started_time": None,
        "stopped_time": None,
        "topic_id": default_topic_id
    }

from datetime import datetime, timedelta

from datetime import datetime, timedelta

def adjust_times(started: bool, stopped: bool, started_time: str, stopped_time: str, message_time_send: datetime) -> (str, str):
    fmt = "%H:%M"
    # Преобразуем строки в datetime, используя дату и tzinfo из message_time_send
    try:
        parsed_started = datetime.combine(message_time_send.date(), datetime.strptime(started_time, fmt).time())
        parsed_started = parsed_started.replace(tzinfo=message_time_send.tzinfo)
    except Exception:
        parsed_started = message_time_send  # если не удаётся распарсить, берем время отправки
    try:
        parsed_stopped = datetime.combine(message_time_send.date(), datetime.strptime(stopped_time, fmt).time())
        parsed_stopped = parsed_stopped.replace(tzinfo=message_time_send.tzinfo)
    except Exception:
        parsed_stopped = message_time_send

    adjustment = timedelta(hours=1)
    threshold = timedelta(minutes=45)

    new_started = parsed_started
    new_stopped = parsed_stopped

    if started and stopped:
        diff = parsed_stopped - message_time_send
        if diff > threshold:
            new_started = parsed_started - adjustment
            new_stopped = parsed_stopped - adjustment
    elif started and not stopped:
        diff = parsed_started - message_time_send
        if diff > threshold:
            new_started = parsed_started - adjustment
            new_stopped = message_time_send
    elif not started and stopped:
        diff = parsed_stopped - message_time_send
        if diff > threshold:
            new_started = message_time_send
            new_stopped = parsed_stopped - adjustment

    return new_started.strftime(fmt), new_stopped.strftime(fmt)


