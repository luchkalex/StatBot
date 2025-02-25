# utils.txt
import re
import json
import logging
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_API_KEY_SECONDARY

logger = logging.getLogger(__name__)

def extract_event_info(text: str, default_topic_id: int) -> dict:
    prompt = (
        "Ты помощник по анализу текстов. Извлеки данные и выведи только JSON.\n"
        "- phone: номер телефона (номер может быть с +, но выводить нужно без плюса; если в сообщении указан только номер, то это номер), иначе null.\n"
        "- started: true, если в сообщении явно указано, что номер начал работать (например, 'встал', 'работает', '+'), иначе false.\n"
        "- stopped: true, если в сообщении явно указано, что номер перестал работать (например, 'слетел', 'умер', '-', '#СЛЕТ'), иначе false.\n"
        "- started_time: время события 'встал' в формате HH:MM, если указано, иначе null.\n"
        "- stopped_time: время события 'слетел' в формате HH:MM, если указано, иначе null.\n"
        "- topic_id: если в тексте есть 'id: 2', то выведи 2, иначе null.\n"
        "Пример правильного ответа:\n"
        "{\"phone\": \"79130000000\", \"started\": true, \"stopped\": false, \"started_time\": \"12:30\", \"stopped_time\": null, \"topic_id\": 2}\n"
        "Если в сообщении отсутствуют явные указания на событие, верни started и stopped как false."
    )
    full_prompt = prompt + "\nТекст: " + text

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
            return extracted
        except Exception as e:
            err_msg = str(e).lower()
            logger.error(f"Ошибка при запросе с ключом {key}: {e}")
            # Если ошибка связана с исчерпанием лимита, пробуем следующий ключ
            if any(substr in err_msg for substr in ["limit", "exhausted", "quota"]):
                logger.info(f"Попытка использовать следующий Gemini API ключ вместо {key}")
                continue
            else:
                break  # Если ошибка не из-за лимита – не пытаемся дальше

    # Если ни один ключ не сработал, возвращаем значения по умолчанию
    return {
        "phone": None,
        "started": False,
        "stopped": False,
        "started_time": None,
        "stopped_time": None,
        "topic_id": default_topic_id
    }


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