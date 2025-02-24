from datetime import timedelta
from typing import Dict, Tuple

# Типизация ключей: (group_id, topic_id, phone)
StatsType = Dict[Tuple[int, int, str], dict]
TopicNamesType = Dict[Tuple[int, int], str]
GlobalMsgIDsType = Dict[int, int]
LastPhoneType = Dict[Tuple[int, int], str]
GroupTitlesType = Dict[int, str]

class BotState:
    def __init__(self):
        self.tracking_active: bool = False
        self.admin_chat_id: int = None
        self.stats: StatsType = {}              # (group_id, topic_id, phone) -> {"started": datetime, "stopped": datetime, "downtime": timedelta}
        self.topic_names: TopicNamesType = {}    # (group_id, topic_id) -> topic name
        self.global_message_ids: GlobalMsgIDsType = {}  # group_id -> message_id
        self.last_phone: LastPhoneType = {}      # (group_id, topic_id) -> phone
        self.group_titles: GroupTitlesType = {}    # group_id -> group title

state = BotState()
