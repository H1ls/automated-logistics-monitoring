import json
from Navigation_Bot.core.paths import DATASET_DIR, DATASET_FILE

class DatasetArchive:
    def __init__(self, log_func=print):
        self.log = log_func
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        self.filepath = DATASET_FILE

    def append(self, sample: dict):
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        # self.log(f"📦 Архивировано → {self.filepath.name}")
