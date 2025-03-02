# state.py
from datetime import timedelta
from typing import Dict, Tuple
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Типизация ключей: (group_id, topic_id, phone)
StatsType = Dict[Tuple[int, int, str], dict]
TopicNamesType = Dict[Tuple[int, int], str]
GlobalMsgIDsType = Dict[int, int]
LastPhoneType = Dict[Tuple[int, int], str]
GroupTitlesType = Dict[int, str]

from datetime import datetime
import pytz


from datetime import datetime

def convert_to_datetime(value):
    if isinstance(value, str):
        try:
            time_part = datetime.strptime(value, "%H:%M").time()
            now = datetime.now(pytz.timezone("Europe/Kiev"))  # или используйте нужный часовой пояс, например: datetime.now(pytz.timezone("Europe/Kiev"))
            return datetime.combine(now.date(), time_part)
        except ValueError:
            return None
    elif isinstance(value, datetime):
        return value
    return None


class BotState:
    def __init__(self):
        self.tracking_active: bool = False
        self.admin_chat_id: int = None
        self.stats: StatsType = {}  # (group_id, topic_id, phone) -> {"started": datetime, "stopped": datetime, "downtime": timedelta}
        self.topic_names: TopicNamesType = {}  # (group_id, topic_id) -> topic name
        self.global_message_ids: GlobalMsgIDsType = {}  # group_id -> message_id
        self.last_phone: LastPhoneType = {}  # (group_id, topic_id) -> phone
        self.group_titles: GroupTitlesType = {}  # group_id -> group title

    from datetime import datetime



    def save_to_csv(self, filename: str = 'stats.csv'):
        if not self.stats:
            logger.info("Нет данных для сохранения в CSV.")
            return
        data = []
        for (group_id, topic_id, phone), record in self.stats.items():
            # Преобразуем 'started' и 'stopped' в datetime перед использованием strftime()
            started = convert_to_datetime(record.get("started"))
            stopped = convert_to_datetime(record.get("stopped"))

            started_str = started.strftime("%Y-%m-%dT%H:%M:%S") if started else None
            stopped_str = stopped.strftime("%Y-%m-%dT%H:%M:%S") if stopped else None
            downtime = record.get("downtime").total_seconds() if record.get("downtime") else None
            logger.info(f"""\nДанные для записи
            group_title: {self.group_titles.get(group_id)}
            started: {started_str}
            stopped: {stopped_str}
            downtime: {downtime}
            phone: {phone}
            last phone: {self.last_phone.get((group_id, topic_id))}
""")
            data.append({
                "group_id": group_id,
                "topic_id": topic_id,
                "phone": phone,
                "started": started_str,
                "stopped": stopped_str,
                "downtime": downtime,
                "topic_name": self.topic_names.get((group_id, topic_id)),
                "global_message_id": self.global_message_ids.get(group_id),
                "last_phone": self.last_phone.get((group_id, topic_id)),
                "group_title": self.group_titles.get(group_id)
            })

        try:
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False)
            logger.info(f"Данные успешно сохранены в {filename}\n\n")
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных в CSV: {e}")

    def load_from_csv(self, filename: str = 'stats.csv'):
        if not Path(filename).exists():
            logger.info(f"Файл {filename} не найден. Начинаем с пустой статистикой.\n\n")
            return

        try:
            df = pd.read_csv(filename)
            # Получаем текущую дату по местному времени
            local_now = datetime.now(pytz.timezone("Europe/Kiev")).date()

            for _, row in df.iterrows():
                # Считываем дату события
                started_date = pd.to_datetime(row['started']).date() if pd.notna(row['started']) else None
                stopped_date = pd.to_datetime(row['stopped']).date() if pd.notna(row['stopped']) else None

                # Загружаем только данные за текущий день
                if started_date == local_now or stopped_date == local_now:
                    key = (row['group_id'], row['topic_id'], row['phone'])
                    self.stats[key] = {
                        "started": pd.to_datetime(row['started']) if pd.notna(row['started']) else None,
                        "stopped": pd.to_datetime(row['stopped']) if pd.notna(row['stopped']) else None,
                        "downtime": timedelta(seconds=row['downtime']) if pd.notna(row['downtime']) else None
                    }
                    self.topic_names[(row['group_id'], row['topic_id'])] = row['topic_name']
                    self.global_message_ids[row['group_id']] = row['global_message_id']
                    self.last_phone[(row['group_id'], row['topic_id'])] = row['last_phone']
                    self.group_titles[row['group_id']] = row['group_title']
            logger.info(f"Данные успешно загружены из {filename}\n\n")
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных из CSV: {e}")


state = BotState()