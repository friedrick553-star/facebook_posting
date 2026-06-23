"""Placeholder for future Anibis integration."""

from app.services.matching_engine import ListingData
from app.sources.base import BaseMarketplaceSource, SourceRegistry


class AnibisSource(BaseMarketplaceSource):
    source_name = "anibis"

    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        raise NotImplementedError("Anibis integration coming soon")

    async def fetch_listing_details(self, url: str) -> ListingData | None:
        raise NotImplementedError("Anibis integration coming soon")


SourceRegistry.register(AnibisSource())
