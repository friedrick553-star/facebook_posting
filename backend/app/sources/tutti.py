"""Placeholder for future Tutti integration."""

from app.services.matching_engine import ListingData
from app.sources.base import BaseMarketplaceSource, SourceRegistry


class TuttiSource(BaseMarketplaceSource):
    source_name = "tutti"

    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        raise NotImplementedError("Tutti integration coming soon")

    async def fetch_listing_details(self, url: str) -> ListingData | None:
        raise NotImplementedError("Tutti integration coming soon")


SourceRegistry.register(TuttiSource())
