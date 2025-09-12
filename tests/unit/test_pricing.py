from datetime import datetime

import pytest

from src.core.models import Attacker, Item, Killmail, Victim


@pytest.fixture()
def km_with_items():
    return Killmail(
        killmail_id=129772128,
        killmail_hash="deadbeef",
        killmail_time=datetime.fromisoformat("2025-09-09T19:50:01+00:00"),
        solar_system_id=30004563,
        victim=Victim(
            corporation_id=98689962,
            ship_type_id=32880,
            damage_taken=582,
            items=[
                Item(flag=94, item_type_id=31117, quantity_destroyed=1, singleton=0),
                Item(flag=93, item_type_id=31117, quantity_destroyed=1, singleton=0),
                Item(flag=11, item_type_id=1319, quantity_dropped=1, singleton=0),
            ],
        ),
        attackers=[Attacker(corporation_id=98092494, damage_done=582, final_blow=True)],
    )
