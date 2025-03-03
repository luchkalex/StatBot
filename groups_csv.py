import csv
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

GROUPS_CSV = "groups.csv"

def load_allowed_groups() -> dict:
    """
    Загружает данные о разрешённых группах.
    Формат CSV: access_key, group_id, group_name
    Возвращает словарь: { access_key: { group_id: group_name, ... }, ... }
    """
    allowed_groups = {}
    if not Path(GROUPS_CSV).exists():
        logger.info("Файл groups.csv не найден, инициализируем пустую структуру разрешённых групп.")
        return allowed_groups
    try:
        with open(GROUPS_CSV, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row["access_key"]
                group_id = int(row["group_id"])
                group_name = row["group_name"]
                if key not in allowed_groups:
                    allowed_groups[key] = {}
                allowed_groups[key][group_id] = group_name
        logger.info("Разрешённые группы успешно загружены.")
    except Exception as e:
        logger.error("Ошибка загрузки разрешённых групп: %s", e)
    return allowed_groups

def save_allowed_groups(allowed_groups: dict) -> None:
    """
    Сохраняет данные о разрешённых группах в CSV-файл.
    """
    try:
        with open(GROUPS_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["access_key", "group_id", "group_name"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for key, groups in allowed_groups.items():
                for group_id, group_name in groups.items():
                    writer.writerow({"access_key": key, "group_id": group_id, "group_name": group_name})
        logger.info("Разрешённые группы успешно сохранены.")
    except Exception as e:
        logger.error("Ошибка сохранения разрешённых групп: %s", e)
