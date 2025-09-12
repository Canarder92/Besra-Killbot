from src.core.models import Killmail
from src.core.prices_cache import PricesCache
from src.esi.market import fetch_price


async def compute_killmail_value(km: Killmail, prices: PricesCache) -> float:
    total = 0.0

    # hull
    hull_price = await get_price(km.victim.ship_type_id, prices)
    total += hull_price

    # items
    for item in km.victim.items:
        qty = (item.quantity_destroyed or 0) + (item.quantity_dropped or 0)
        if qty > 0:
            total += qty * await get_price(item.item_type_id, prices)

    return total


async def get_price(type_id: int, prices: PricesCache) -> float:
    cached = prices.get(type_id)
    if cached is not None:
        return cached
    new_price = await fetch_price(type_id)
    prices.set(type_id, new_price)
    return new_price


async def compute_killmail_drop(km: Killmail, prices: PricesCache) -> float:
    """Somme des items qui ont *drop* (hors hull, hors destroyed)."""
    total_drop = 0.0
    for item in km.victim.items:
        qty_drop = item.quantity_dropped or 0
        if qty_drop > 0:
            total_drop += qty_drop * await get_price(item.item_type_id, prices)
    return total_drop
