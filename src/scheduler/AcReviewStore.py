import json
import os


class AcReviewStore:
    def __init__(self, history_dir: str):
        self._dir = history_dir
        os.makedirs(history_dir, exist_ok=True)

    def load(self, cardset_id: str) -> dict:
        path = os.path.join(self._dir, f"{cardset_id}.json")
        if not os.path.exists(path):
            return {"cardset_id": cardset_id, "cards": {}}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, cardset_id: str, state: dict) -> None:
        path = os.path.join(self._dir, f"{cardset_id}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
