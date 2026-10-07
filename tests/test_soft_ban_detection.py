# tests/test_soft_ban_detection.py
"""Cases where the soft-ban detector could miss a ban or false-positive."""
from portal_client import _is_soft_banned


def test_origin_source_is_never_banned():
    body = {"items": [], "next_cursor": None, "meta": {"source": "origin"}}
    assert _is_soft_banned(body, []) is False


def test_edge_source_with_empty_items_is_banned():
    body = {"items": [], "next_cursor": None, "meta": {"source": "edge"}}
    assert _is_soft_banned(body, []) is True


def test_edge_source_with_truncated_page_is_banned():
    body = {"items": [{}] * 3, "next_cursor": "3", "meta": {"source": "edge"}}
    assert _is_soft_banned(body, [{}] * 3) is True


def test_healthy_last_page_is_not_banned():
    """Origin source + short last page (next_cursor None) is not a ban."""
    page = [{}] * 3
    body = {"items": page, "next_cursor": None, "meta": {"source": "origin"}}
    assert _is_soft_banned(body, page) is False


def test_missing_meta_is_not_banned():
    """Response without a meta block should not be treated as a ban."""
    body = {"items": [], "next_cursor": None}
    assert _is_soft_banned(body, []) is False