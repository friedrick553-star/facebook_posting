"""Per-user Facebook browser instances — separate Chromium session per user."""
from __future__ import annotations

from app.sources.facebook import FacebookMarketplaceSource

_instances: dict[int, FacebookMarketplaceSource] = {}


def get_facebook_source(user_id: int) -> FacebookMarketplaceSource:
    if user_id not in _instances:
        _instances[user_id] = FacebookMarketplaceSource(user_id=user_id)
    return _instances[user_id]


def all_facebook_sources() -> list[FacebookMarketplaceSource]:
    return list(_instances.values())
