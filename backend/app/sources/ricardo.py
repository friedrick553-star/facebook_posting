"""Placeholder for future Ricardo integration."""

from app.services.matching_engine import ListingData
from app.sources.base import BaseMarketplaceSource, SourceRegistry


class RicardoSource(BaseMarketplaceSource):
    source_name = "ricardo"

    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        raise NotImplementedError("Ricardo integration coming soon")

    async def fetch_listing_details(self, url: str) -> ListingData | None:
        raise NotImplementedError("Ricardo integration coming soon")


SourceRegistry.register(RicardoSource())
