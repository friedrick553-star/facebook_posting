"""Placeholder for future Autoscout24 integration."""

from app.services.matching_engine import ListingData
from app.sources.base import BaseMarketplaceSource, SourceRegistry


class Autoscout24Source(BaseMarketplaceSource):
    source_name = "autoscout24"

    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        raise NotImplementedError("Autoscout24 integration coming soon")

    async def fetch_listing_details(self, url: str) -> ListingData | None:
        raise NotImplementedError("Autoscout24 integration coming soon")


SourceRegistry.register(Autoscout24Source())
