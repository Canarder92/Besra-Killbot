from src.scheduler.cleanup_policy import should_rewrite_cleanup_index


def test_cleanup_rewrite_requires_esi_snapshot():
    assert not should_rewrite_cleanup_index(
        esi_snapshot_ok=False,
        zkb_enabled=False,
        zkb_snapshot_ok=True,
    )


def test_cleanup_rewrite_requires_zkb_snapshot_when_enabled():
    assert not should_rewrite_cleanup_index(
        esi_snapshot_ok=True,
        zkb_enabled=True,
        zkb_snapshot_ok=False,
    )


def test_cleanup_rewrite_allows_complete_dual_snapshot():
    assert should_rewrite_cleanup_index(
        esi_snapshot_ok=True,
        zkb_enabled=True,
        zkb_snapshot_ok=True,
    )


def test_cleanup_rewrite_allows_esi_only_mode():
    assert should_rewrite_cleanup_index(
        esi_snapshot_ok=True,
        zkb_enabled=False,
        zkb_snapshot_ok=False,
    )