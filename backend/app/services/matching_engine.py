import json
import re
from dataclasses import dataclass, field


@dataclass
class FilterCriteria:
    country: str | None = None
    city: str | None = None
    radius_km: int | None = None
    brands: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    fuel_types: list[str] = field(default_factory=list)
    transmission_types: list[str] = field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    mileage_min: int | None = None
    mileage_max: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_match_score: float = 80.0


@dataclass
class ListingData:
    external_id: str
    url: str
    title: str
    price: float | None = None
    currency: str = "CHF"
    mileage: int | None = None
    year: int | None = None
    brand: str | None = None
    model: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    description: str | None = None
    location: str | None = None
    seller_name: str | None = None
    images: list[str] = field(default_factory=list)
    posted_time: str | None = None
    source: str = "facebook"


@dataclass
class MatchResult:
    score: float
    details: dict[str, float]
    excluded: bool = False
    exclusion_reason: str | None = None


def _normalize(text: str | None) -> str:
    return (text or "").lower().strip()


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords if kw)


def _list_match(value: str | None, allowed: list[str]) -> float:
    if not allowed:
        return 100.0
    if not value:
        return 0.0
    if _text_matches_any_allowed(value, allowed):
        return 100.0
    return 0.0


def _normalize_token(text: str) -> str:
    return (text or "").lower().strip()


FUEL_ALIASES: dict[str, set[str]] = {
    "petrol": {"petrol", "benzin", "gasoline", "gas", "essence", "tfsi", "tsi", "fsi"},
    "diesel": {"diesel", "tdi", "dci", "cdti", "hdi", "crdi"},
    "electric": {"electric", "ev", "elektro", "e-tron"},
    "hybrid": {"hybrid", "phev", "plug-in", "plug in"},
    "lpg": {"lpg", "autogas"},
}


def _fuel_key(label: str) -> str:
    t = _normalize_token(label)
    for key, aliases in FUEL_ALIASES.items():
        if t == key or t in aliases:
            return key
    return t


def _text_matches_any_allowed(text: str, allowed: list[str], *, prefer_longest: bool = False) -> bool:
    """True if text contains at least one allowed value (OR within the same filter field)."""
    if not allowed:
        return True
    haystack = _normalize_token(text)
    if not haystack:
        return False

    items = [a.strip() for a in allowed if a and a.strip()]
    if prefer_longest:
        items = sorted(items, key=len, reverse=True)

    for item in items:
        needle = _normalize_token(item)
        if not needle:
            continue
        if needle in haystack:
            return True
        if len(needle) <= 30 and re.search(rf"\b{re.escape(needle)}\b", haystack):
            return True
    return False


def _fuel_matches_text(text: str, allowed_fuels: list[str]) -> bool:
    if not allowed_fuels:
        return True
    haystack = _normalize_token(text)
    if not haystack:
        return False

    inferred = infer_fuel_from_text(text)
    inferred_key = _fuel_key(inferred) if inferred else ""

    for fuel in allowed_fuels:
        fuel_key = _fuel_key(fuel)
        if fuel_key and fuel_key in haystack:
            return True
        if _text_matches_any_allowed(haystack, [fuel]):
            return True
        if inferred_key and inferred_key == fuel_key:
            return True
        aliases = FUEL_ALIASES.get(fuel_key, set())
        if any(alias in haystack for alias in aliases):
            return True
    return False


def _first_match_in_list(text: str, allowed: list[str], *, prefer_longest: bool = False) -> str | None:
    if not allowed:
        return None
    items = [a.strip() for a in allowed if a and a.strip()]
    if prefer_longest:
        items = sorted(items, key=len, reverse=True)
    haystack = _normalize_token(text)
    for item in items:
        needle = _normalize_token(item)
        if needle and (needle in haystack or re.search(rf"\b{re.escape(needle)}\b", haystack)):
            return item
    return None


def _range_match(value: float | int | None, min_val: float | int | None, max_val: float | int | None) -> float:
    if value is None:
        return 50.0 if (min_val is not None or max_val is not None) else 100.0
    if min_val is not None and value < min_val:
        return max(0.0, 100.0 - ((min_val - value) / max(min_val, 1)) * 100)
    if max_val is not None and value > max_val:
        return max(0.0, 100.0 - ((value - max_val) / max(max_val, 1)) * 100)
    return 100.0


def _location_match(location: str | None, city: str | None, country: str | None) -> float:
    if not city and not country:
        return 100.0
    loc = _normalize(location)
    score = 0.0
    if city and city.lower() in loc:
        score += 60.0
    if country and country.lower() in loc:
        score += 40.0
    if score == 0.0 and (city or country):
        return 30.0
    return min(score, 100.0)


def _extract_brand_model_from_title(title: str, brands: list[str], models: list[str]) -> tuple[str | None, str | None]:
    found_brand = _first_match_in_list(title, brands)
    found_model = _first_match_in_list(title, models, prefer_longest=True)
    return found_brand, found_model


def _keyword_score(text: str, include_keywords: list[str]) -> float:
    if not include_keywords:
        return 100.0
    matches = sum(1 for kw in include_keywords if kw.lower() in text.lower())
    return min(100.0, (matches / len(include_keywords)) * 100 + (20 if matches > 0 else 0))


class MatchingEngine:
    WEIGHTS = {
        "brand": 15,
        "model": 20,
        "mileage": 15,
        "year": 10,
        "fuel_type": 15,
        "transmission": 15,
        "location": 10,
        "keywords": 10,
    }

    def score(self, listing: ListingData, criteria: FilterCriteria) -> MatchResult:
        combined_text = " ".join(
            filter(None, [listing.title, listing.description or "", listing.fuel_type or "", listing.transmission or ""])
        )

        if criteria.exclude_keywords and _contains_any(combined_text, criteria.exclude_keywords):
            matched = next(kw for kw in criteria.exclude_keywords if kw.lower() in combined_text.lower())
            return MatchResult(score=0.0, details={}, excluded=True, exclusion_reason=f"Excluded keyword: {matched}")

        brand = listing.brand or _extract_brand_model_from_title(listing.title, criteria.brands, criteria.models)[0]
        model = listing.model or _extract_brand_model_from_title(listing.title, criteria.brands, criteria.models)[1]

        details = {
            "brand": _list_match(brand, criteria.brands),
            "model": _list_match(model or listing.title, criteria.models),
            "mileage": _range_match(listing.mileage, criteria.mileage_min, criteria.mileage_max),
            "year": _range_match(listing.year, criteria.year_min, criteria.year_max),
            "fuel_type": _list_match(listing.fuel_type or combined_text, criteria.fuel_types),
            "transmission": _list_match(listing.transmission or combined_text, criteria.transmission_types),
            "location": _location_match(listing.location, criteria.city, criteria.country),
            "keywords": _keyword_score(combined_text, criteria.include_keywords),
        }

        total_weight = sum(self.WEIGHTS.values())
        weighted_score = sum(details[k] * self.WEIGHTS[k] for k in self.WEIGHTS) / total_weight
        return MatchResult(score=round(weighted_score, 2), details=details)

    def is_full_match(self, listing: ListingData, criteria: FilterCriteria) -> tuple[bool, MatchResult]:
        """
        True only when ALL configured filter fields match (AND across fields).
        Within one field (e.g. brands: Audi|BMW), ANY listed value may match (OR).
        Example: brand=Audi AND model=Audi A4 AND fuel=Petrol must all appear in listing.
        """
        combined_text = " ".join(
            filter(
                None,
                [
                    listing.title,
                    listing.description or "",
                    listing.fuel_type or "",
                    listing.transmission or "",
                    listing.location or "",
                ],
            )
        )

        if criteria.exclude_keywords and _contains_any(combined_text, criteria.exclude_keywords):
            matched = next(kw for kw in criteria.exclude_keywords if kw.lower() in combined_text.lower())
            return False, MatchResult(
                score=0.0,
                details={},
                excluded=True,
                exclusion_reason=f"Excluded keyword: {matched}",
            )

        if criteria.brands and not _text_matches_any_allowed(combined_text, criteria.brands):
            return False, MatchResult(
                score=0.0, details={"brand": 0.0}, exclusion_reason=f"Brand not in filter: {criteria.brands}"
            )
        if criteria.models and not _text_matches_any_allowed(combined_text, criteria.models, prefer_longest=True):
            return False, MatchResult(
                score=0.0, details={"model": 0.0}, exclusion_reason=f"Model not in filter: {criteria.models}"
            )
        if criteria.fuel_types and not _fuel_matches_text(combined_text, criteria.fuel_types):
            return False, MatchResult(
                score=0.0,
                details={"fuel_type": 0.0},
                exclusion_reason=f"Fuel type not in filter: {criteria.fuel_types}",
            )
        if criteria.transmission_types and not _text_matches_any_allowed(combined_text, criteria.transmission_types):
            return False, MatchResult(
                score=0.0,
                details={"transmission": 0.0},
                exclusion_reason=f"Transmission not in filter: {criteria.transmission_types}",
            )
        if not _strict_range_match(listing.mileage, criteria.mileage_min, criteria.mileage_max):
            return False, MatchResult(score=0.0, details={"mileage": 0.0}, exclusion_reason="Mileage out of range")
        if not _strict_range_match(listing.year, criteria.year_min, criteria.year_max):
            return False, MatchResult(score=0.0, details={"year": 0.0}, exclusion_reason="Year out of range")

        if criteria.include_keywords:
            for kw in criteria.include_keywords:
                if kw.lower() not in combined_text.lower():
                    return False, MatchResult(
                        score=0.0,
                        details={"keywords": 0.0},
                        exclusion_reason=f"Missing keyword: {kw}",
                    )

        brand = listing.brand or _first_match_in_list(combined_text, criteria.brands)
        model = listing.model or _first_match_in_list(combined_text, criteria.models, prefer_longest=True)
        fuel = listing.fuel_type or infer_fuel_from_text(combined_text)
        transmission = listing.transmission or infer_transmission_from_text(combined_text)

        enriched = ListingData(
            external_id=listing.external_id,
            url=listing.url,
            title=listing.title,
            price=listing.price,
            currency=listing.currency,
            mileage=listing.mileage,
            year=listing.year,
            brand=brand,
            model=model,
            fuel_type=fuel,
            transmission=transmission,
            description=listing.description,
            location=listing.location,
            seller_name=listing.seller_name,
            images=listing.images,
            posted_time=listing.posted_time,
            source=listing.source,
        )
        listing.brand = brand
        listing.model = model
        listing.fuel_type = fuel
        listing.transmission = transmission
        result = self.score(enriched, criteria)
        return True, result


def parse_number_from_text(text: str) -> int | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text.replace("'", "").replace(",", ""))
    return int(cleaned) if cleaned else None


def listing_has_filter_hint(text: str, criteria: FilterCriteria) -> bool:
    """
    Lightweight check on main-page text only.
    Opens detail page only when configured brand/model hints appear (AND if both set).
    """
    if not criteria.brands and not criteria.models:
        return False

    combined = " ".join(filter(None, [text])).strip()
    if not combined or combined.lower() in {"unknown vehicle", "unknown"}:
        return False

    if criteria.brands and not _text_matches_any_allowed(combined, criteria.brands):
        return False
    if criteria.models and not _text_matches_any_allowed(combined, criteria.models, prefer_longest=True):
        return False
    return True


def listing_hint_text(*parts: str | None) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def item_dict_hint_text(item: dict) -> str:
    return listing_hint_text(
        item.get("title"),
        item.get("card_text"),
        item.get("aria_label"),
    )


def parse_price_from_text(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"[\d''\s.,]+", text)
    if not match:
        return None
    digits_only = re.sub(r"[^\d]", "", match.group().replace("'", "").replace(" ", ""))
    return float(digits_only) if digits_only else None


def parse_year_from_title(title: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", title)
    return int(match.group()) if match else None


def parse_mileage_from_text(text: str) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d[\d'\s.,]*)\s*km", text, re.I)
    if match:
        return parse_number_from_text(match.group(1))
    return None


def infer_fuel_from_text(text: str) -> str | None:
    text_lower = text.lower()
    fuels = {
        "diesel": "Diesel",
        "benzin": "Petrol",
        "petrol": "Petrol",
        "gasoline": "Petrol",
        "electric": "Electric",
        "hybrid": "Hybrid",
        "plug-in": "Hybrid",
        "lpg": "LPG",
    }
    for key, label in fuels.items():
        if key in text_lower:
            return label
    return None


def infer_transmission_from_text(text: str) -> str | None:
    text_lower = text.lower()
    if any(k in text_lower for k in ("automatic", "automatik", "auto ")):
        return "Automatic"
    if any(k in text_lower for k in ("manual", "schalt", "stick")):
        return "Manual"
    return None


def _strict_list_match(value: str | None, allowed: list[str]) -> bool:
    if not allowed:
        return True
    return _list_match(value, allowed) >= 100.0


def _strict_range_match(
    value: float | int | None, min_val: float | int | None, max_val: float | int | None
) -> bool:
    if min_val is None and max_val is None:
        return True
    if value is None:
        return True
    if min_val is not None and value < min_val:
        return False
    if max_val is not None and value > max_val:
        return False
    return True


def listing_to_hash(listing: ListingData) -> str:
    import hashlib
    key = f"{listing.external_id}|{listing.title}|{listing.price}|{listing.url}"
    return hashlib.sha256(key.encode()).hexdigest()
