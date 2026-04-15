from collections import defaultdict
from typing import List, Dict

class ChatMemory:
    def __init__(self, max_messages=10):
        self.history: Dict[int, List[Dict]] = defaultdict(list)
        self.max_messages = max_messages

    def add_message(self, chat_id: int, role: str, content: str):
        self.history[chat_id].append({"role": role, "content": content})
        if len(self.history[chat_id]) > self.max_messages:
            self.history[chat_id].pop(0)

    def get_history(self, chat_id: int) -> List[Dict]:
        return self.history[chat_id]

    def clear(self, chat_id: int):
        self.history[chat_id] = []

memory = ChatMemory()
