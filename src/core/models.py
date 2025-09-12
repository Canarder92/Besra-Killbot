from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EsiBaseModel(BaseModel):
    # Ignore les champs en plus qui peuvent apparaître dans les réponses ESI
    model_config = ConfigDict(extra="ignore")


class KillmailRef(EsiBaseModel):
    killmail_id: int
    killmail_hash: str


class Item(EsiBaseModel):
    flag: int
    item_type_id: int
    quantity_destroyed: int | None = 0
    quantity_dropped: int | None = 0
    singleton: int


class Victim(EsiBaseModel):
    character_id: int | None = None
    corporation_id: int
    alliance_id: int | None = None
    ship_type_id: int
    damage_taken: int
    items: list[Item] = Field(default_factory=list)


class Attacker(EsiBaseModel):
    character_id: int | None = None
    corporation_id: int | None = None
    alliance_id: int | None = None
    ship_type_id: int | None = None
    weapon_type_id: int | None = None
    damage_done: int = 0
    final_blow: bool = False


class Killmail(EsiBaseModel):
    killmail_id: int
    killmail_hash: str
    killmail_time: datetime
    solar_system_id: int
    victim: Victim
    attackers: list[Attacker]

    def involved_count(self) -> int:
        return len(self.attackers)
