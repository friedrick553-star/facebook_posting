import json
import logging
from abc import ABC, abstractmethod

from app.services.matching_engine import ListingData

logger = logging.getLogger(__name__)


class BaseMarketplaceSource(ABC):
    source_name: str = "base"

    @abstractmethod
    async def fetch_listings(self, search_url: str, max_results: int = 50) -> list[ListingData]:
        pass

    @abstractmethod
    async def fetch_listing_details(self, url: str) -> ListingData | None:
        pass


class SourceRegistry:
    _sources: dict[str, BaseMarketplaceSource] = {}

    @classmethod
    def register(cls, source: BaseMarketplaceSource) -> None:
        cls._sources[source.source_name] = source

    @classmethod
    def get(cls, name: str) -> BaseMarketplaceSource | None:
        return cls._sources.get(name)

    @classmethod
    def list_sources(cls) -> list[str]:
        return list(cls._sources.keys())
