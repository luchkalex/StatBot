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
    
        started: true, if the message explicitly states that the number has started working (e.g., 'встал', 'работает', 'зашел', '+') (also consider typos like 'вслат', 'стлоит', 'сашел', etc.), otherwise false. If 'встал' or similar is followed by a question, e.g., 'работает?', 'встал?', then False.
    
        stopped: true, if the message explicitly states that the number has stopped working (e.g., 'слетел', 'умер', '-', '#СЛЕТ') (also consider typos like 'стел', 'стелел', etc.), otherwise false. If 'слетел' or similar is followed by a question, e.g., 'слет?', 'минус?', then False.
    
        started_time: the time of the started event usually written after specifying an event in HH:MM format, if specified (the number may include typos like '1200', '12^00', '12.00', '12/00', '12 00', etc.), otherwise message time sent.
    
        stopped_time: the time of the stopped event usually written after specifying an event in HH:MM format, if specified (the number may include typos like '1200', '12^00', '12.00', '12/00', '12 00', etc.), otherwise message time sent.
    
        topic_id: if the text contains 'id: 2', then output 2, otherwise null.
    
        Additional notes: 
        1. If there are simply 4 digits, e.g., 'встал 1122', recognize this as time 11:22. There may be messages with both events specified, e.g., '+ 1150 - 1155', which should be recognized as two events: started 11:50 and stopped 11:55.
        2. Return only one JSON for the number. If there is no number but there are entry and exit times, return the times for an empty number with started true and stopped true.
        After creating the JSON, double-check to ensure there is only one entry for one phone, even if it is none.
        
        3. If the message sending time differs from the time specified in the message more then 45 minutes, editing is required. If difference less then 45 minutes no editing needed 
        You need to find out if there is a time zone difference between the event and the time the message was sent.
        For example, if the message is 'встал 12:00' and the message sending time is '2025-02-27 11:02:02+02:00', this means the time zones differ by minus 1 hour. 
        The correct response in this case would be '11:00'.
        
        4. If the message contains both events You need to find out if there is a time zone difference based on stopped time.
        e.g., u need figure out time zone difference '+1200 -1400', and the message sending time is '2025-02-27 13:02:02+02:00', 
        compare the message sending time '2025-02-27 13:02:02+02:00' specifically with the stopped time '1400'. 
        13:02 minus 14:00 is -0:58 (time zones differ by minus 1 hour). Convert both events to local time, i.e.,
        Text: '+1200 -1400' output: started_time 11:00 stopped_time 13:00.
        Only change the hours according to the calculated time zone difference.
        
        5. For example message text is 'встал 2039' and message time is '2025-02-27 20:36:43+02:00' difference between them is 3 minutes < 45 minutes no editing needed
        correct output started_time 20:39
        For example message text is 'встал 2040' and message time is '2025-02-27 19:41:43+02:00' difference between them is 59 minutes > 45 minutes, editing required 
        correct output started_time 19:39
        6. the message can be like 'встал - 21:00' this should be interpreted as started time 21:00, and NOT as stopped time
        
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


