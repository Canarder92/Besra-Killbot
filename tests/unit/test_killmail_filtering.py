import asyncio

from src.scheduler.loop import KillIndex


def test_kill_index_roundtrip(tmp_path):
    p = tmp_path / "kills_index.json"
    idx = KillIndex(str(p))

    # vide au départ
    assert asyncio.run(idx.known_set()) == set()

    # ajout (claim) : deux entrées
    assert asyncio.run(idx.add_if_absent(1, "hash1")) is True
    assert asyncio.run(idx.add_if_absent(2, "hash2")) is True

    # doublon : ne doit pas réajouter
    assert asyncio.run(idx.add_if_absent(1, "hash1")) is False

    known = asyncio.run(idx.known_set())
    assert known == {(1, "hash1"), (2, "hash2")}

    # réécriture filtrée (simulateur de cleanup)
    asyncio.run(idx.rewrite_with({(2, "hash2")}))
    known2 = asyncio.run(idx.known_set())
    assert known2 == {(2, "hash2")}
