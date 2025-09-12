from datetime import datetime, timedelta

from src.config import settings
from src.core.store import JSONStore


class PricesCache:
    def __init__(self, path: str):
        self.ttl = timedelta(days=settings.PRICE_TTL_DAYS)
        self.store = JSONStore(path, {})

    def get(self, type_id: int) -> float | None:
        data = self.store.read()
        entry = data.get(str(type_id))
        if not entry:
            return None
        ts = datetime.fromisoformat(entry["updated_at"])
        if datetime.utcnow() - ts > self.ttl:
            return None
        return float(entry["avg_price"])

    def set(self, type_id: int, avg_price: float):
        data = self.store.read()
        data[str(type_id)] = {
            "avg_price": avg_price,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.store.write(data)
