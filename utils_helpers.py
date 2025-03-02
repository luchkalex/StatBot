import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

def ensure_datetime(value):
    logger.debug("Проверка и преобразование значения '%s' в datetime", value)
    if isinstance(value, str):
        try:
            dt = datetime.strptime(value, "%H:%M")
            logger.debug("Строка '%s' успешно преобразована в datetime: %s", value, dt)
            return dt
        except ValueError:
            logger.error("Ошибка преобразования строки '%s' в datetime", value)
            return None
    elif isinstance(value, datetime):
        logger.debug("Значение уже является datetime: %s", value)
        return value
    logger.warning("Неподдерживаемый тип для преобразования в datetime: %s", type(value))
    return None

def convert_to_datetime(value):
    logger.debug("Преобразование значения '%s' в datetime с учетом часового пояса Europe/Kiev", value)
    if isinstance(value, str):
        try:
            time_part = datetime.strptime(value, "%H:%M").time()
            now = datetime.now(pytz.timezone("Europe/Kiev"))
            dt = datetime.combine(now.date(), time_part)
            logger.debug("Преобразование успешно: %s", dt)
            return dt
        except ValueError:
            logger.error("Ошибка преобразования строки '%s' в datetime", value)
            return None
    elif isinstance(value, datetime):
        logger.debug("Значение уже является datetime: %s", value)
        return value
    logger.warning("Неподдерживаемый тип для преобразования: %s", type(value))
    return None
