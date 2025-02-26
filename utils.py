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
        "- phone: номер телефона (номер может быть с + или в формате  +7 995 488-58-59 но выводить нужно без плюса и без всех разделителей; если в сообщении указан только номер, то это номер), иначе null.\n"
        "- started: true, если в сообщении явно указано, что номер начал работать (например, 'встал', 'работает', 'зашел' '+') (также могут быть опечатки например 'вслат' 'стлоит' 'сашел' и тому подобные, учтитывай это), иначе false. если встал или тому подобные с вопросом например 'работает?' 'встал?' то False\n"
        "- stopped: true, если в сообщении явно указано, что номер перестал работать (например, 'слетел', 'умер', '-', '#СЛЕТ') (также могут быть опечатки например 'стел' 'стелел' и тому подобные, учтитывай это), иначе false. если слетел или тому подобные с вопросом например 'слет?' 'минус?' то False\n"
        "- started_time: время события 'встал' в формате HH:MM, если указано (номер может быть с опечатками например '1200' '12^00' '12.00' '12/00' '12 00' и тому подобное), иначе null.\n"
        "- stopped_time: время события 'слетел' в формате HH:MM, если указано (номер может быть с опечатками например '1200' '12^00' '12.00' '12/00' '12 00' и тому подобное)), иначе null.\n"
        "- topic_id: если в тексте есть 'id: 2', то выведи 2, иначе null.\n"
        "Дополнения: если просто 4 цифры например 'встал 1122' то распознавай это как время 11:22, могут быть сообщения в которых указаны оба события например '+ 1150 - 1155' нужно распознать это как два события started 11:50 stopped 11:55"
        "нужно вернуть только один JSON для номер, если номера нет но есть время входа и выхода то нужно вернуть время для пустого номера started true и stopped true"
        "после создания json еще раз перепроверь чтобы была только одна запись для одного phone даже если он none"
        "Пример правильного ответа:\n"
        "{\"phone\": \"79954885859\", \"started\": true, \"stopped\": true, \"started_time\": \"12:30\", \"stopped_time\": \"12:40\", \"topic_id\": 2}\n"
        "Пример НЕ правильного ответа (нельзя присылать несколько записей)\n"
        """[
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
        
        если у тебя получился такой json то соедини эти записи в одну
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