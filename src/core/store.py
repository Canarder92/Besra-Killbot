import json
import os
from typing import Any


class JSONStore:
    """Safe JSON file store with atomic writes."""

    def __init__(self, path: str, default: Any):
        self.path = path
        self.default = default
        if not os.path.exists(path):
            self.write(default)

    def read(self) -> Any:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self.default

    def write(self, data: Any) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
