# utils.txt
import re
import json
import logging
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

def extract_event_info(text: str, default_topic_id: int) -> dict:
    prompt = (
        "Ты помощник по анализу текстов. Извлеки данные и выведи только JSON.\n"
        "- phone: номер телефона (номер может быть с +, но выводить нужно без плюса; если в сообщении указан только номер, то это номер), иначе null.\n"
        "- event: если в сообщении явно указано, что номер начал работать (например, 'встал', 'работает', '+') - верни 'started', "
        "если явно указано, что номер перестал работать (например, 'слетел', 'умер', '-') - верни 'stopped'. "
        "Если таких указаний нет, верни null.\n"
        "- event_time: время события в формате HH:MM, иначе null. Если время не указано, оставь null.\n"
        "- topic_id: если в тексте есть 'id: 2', то выведи 2, иначе null.\n"
        "Пример правильного ответа:\n"
        "{\"phone\": \"79130000000\", \"event\": \"started\", \"event_time\": \"12:30\", \"topic_id\": 2}\n"
        "Если в сообщении отсутствуют явные указания на событие, верни event как null."
    )

    full_prompt = prompt + "\nТекст: " + text

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
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