from datetime import timedelta, datetime
import pandas as pd
from pathlib import Path
import logging
import pytz

logger = logging.getLogger(__name__)

def convert_to_datetime(value):
    if isinstance(value, str):
        try:
            time_part = datetime.strptime(value, "%H:%M").time()
            now = datetime.now(pytz.timezone("Europe/Kiev"))
            return datetime.combine(now.date(), time_part)
        except ValueError:
            return None
    elif isinstance(value, datetime):
        return value
    return None

class BotState:
    def __init__(self):
        self.tracking_active: bool = False
        # Для поддержки нескольких сессий (админов), использующих один CSV‑файл:
        # admin_chat_ids: CSV filename -> set(chat_id)
        self.admin_chat_ids: dict[str, set[int]] = {}
        # Глобальные сообщения: CSV filename -> { chat_id -> { group_id -> message_id } }
        self.global_message_ids: dict[str, dict[int, dict[int, int]]] = {}
        # Статистика теперь хранится с ключом: (csv_filename, group_id, topic_id, phone)
        self.stats = {}
        self.topic_names = {}  # (group_id, topic_id) -> topic name
        self.last_phone = {}   # (group_id, topic_id) -> phone
        self.group_titles = {} # group_id -> group title

        # Новые структуры для разрешённых групп:
        # allowed_groups: csv_filename -> { group_id: group_name }
        self.allowed_groups = {}
        # group_to_key: group_id -> csv_filename
        # Новая структура: для каждой группы – набор CSV‑файлов (ключей), к которым она привязана
        self.group_to_keys: dict[int, set[str]] = {}

    def save_to_csv(self, filename: str = 'stats.csv'):
        if not self.stats:
            logger.info("Нет данных для сохранения в CSV.")
            return
        data = []
        for (file_key, group_id, topic_id, phone), record in self.stats.items():
            # Сохраняем записи только для нужного CSV‑файла
            if file_key != filename:
                continue
            started = convert_to_datetime(record.get("started"))
            stopped = convert_to_datetime(record.get("stopped"))
            started_str = started.strftime("%Y-%m-%dT%H:%M:%S") if started else None
            stopped_str = stopped.strftime("%Y-%m-%dT%H:%M:%S") if stopped else None
            downtime = record.get("downtime").total_seconds() if record.get("downtime") else None
            data.append({
                "group_id": group_id,
                "topic_id": topic_id,
                "phone": phone,
                "started": started_str,
                "stopped": stopped_str,
                "downtime": downtime,
                "topic_name": self.topic_names.get((group_id, topic_id)),
                "global_message_id": None,
                "last_phone": self.last_phone.get((group_id, topic_id)),
                "group_title": self.group_titles.get(group_id)
            })
        try:
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
            logger.info(f"Данные успешно сохранены в {filename}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных в CSV: {e}")

    def load_from_csv(self, filename: str = 'stats.csv'):
        if not Path(filename).exists():
            logger.info(f"Файл {filename} не найден. Начинаем с пустой статистикой.")
            return
        try:
            df = pd.read_csv(filename)
            local_now = datetime.now(pytz.timezone("Europe/Kiev")).date()
            for _, row in df.iterrows():
                started_date = pd.to_datetime(row['started']).date() if pd.notna(row['started']) else None
                stopped_date = pd.to_datetime(row['stopped']).date() if pd.notna(row['stopped']) else None
                if started_date == local_now or stopped_date == local_now:
                    key = (filename, row['group_id'], row['topic_id'], row['phone'])
                    self.stats[key] = {
                        "started": pd.to_datetime(row['started']) if pd.notna(row['started']) else None,
                        "stopped": pd.to_datetime(row['stopped']) if pd.notna(row['stopped']) else None,
                        "downtime": timedelta(seconds=row['downtime']) if pd.notna(row['downtime']) else None
                    }
                    self.topic_names[(row['group_id'], row['topic_id'])] = row['topic_name']
                    self.last_phone[(row['group_id'], row['topic_id'])] = row['last_phone']
                    self.group_titles[row['group_id']] = row['group_title']
            logger.info(f"Данные успешно загружены из {filename}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных из CSV: {e}")

state = BotState()
