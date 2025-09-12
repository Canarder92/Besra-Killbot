import asyncio

from src.scheduler.loop import KillIndex


def test_kill_index_roundtrip(tmp_path):
    p = tmp_path / "kills_index.json"
    idx = KillIndex(str(p))

    # Vide au départ
    assert asyncio.run(idx.known_set()) == set()

    # Ajout
    asyncio.run(idx.add_and_mark_posted(1, "hash1"))
    asyncio.run(idx.add_and_mark_posted(2, "hash2"))

    known = asyncio.run(idx.known_set())
    assert known == {(1, "hash1"), (2, "hash2")}

    # Réécriture filtrée
    asyncio.run(idx.rewrite_with({(2, "hash2")}))
    known2 = asyncio.run(idx.known_set())
    assert known2 == {(2, "hash2")}
