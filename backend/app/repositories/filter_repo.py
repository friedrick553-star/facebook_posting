import json

from sqlalchemy.orm import Session

from app.models import Filter, FilterKeyword
from app.schemas import FilterCreate, FilterResponse


def _serialize_list(items: list[str]) -> str:
    return json.dumps(items)


def _deserialize_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return [v.strip() for v in value.split(",") if v.strip()]


def validate_filter_data(data: FilterCreate) -> None:
    """Required fields for Facebook search + match/email alerts."""
    if not (data.city or "").strip():
        raise ValueError("City is required")
    if not (data.country or "").strip():
        raise ValueError("Country / Region is required")
    if not data.radius_km or data.radius_km <= 0:
        raise ValueError("Radius (km) is required")
    if data.price_min is None or data.price_min <= 0:
        raise ValueError("Min Price is required")
    if data.price_max is None or data.price_max <= 0:
        raise ValueError("Max Price is required")
    if data.price_max < data.price_min:
        raise ValueError("Max Price must be ≥ Min Price")
    if not data.brands:
        raise ValueError("At least one brand is required")
    if not data.models:
        raise ValueError("At least one model is required")
    if data.min_match_score is None or data.min_match_score < 0 or data.min_match_score > 100:
        raise ValueError("Min Match Score (0–100) is required")


def filter_to_response(db_filter: Filter, db: Session) -> FilterResponse:
    keywords = db.query(FilterKeyword).filter(FilterKeyword.filter_id == db_filter.id).all()
    return FilterResponse(
        id=db_filter.id,
        name=db_filter.name,
        is_active=db_filter.is_active,
        country=db_filter.country,
        city=db_filter.city,
        radius_km=db_filter.radius_km,
        brands=_deserialize_list(db_filter.brands),
        models=_deserialize_list(db_filter.models),
        fuel_types=_deserialize_list(db_filter.fuel_types),
        transmission_types=_deserialize_list(db_filter.transmission_types),
        price_min=db_filter.price_min,
        price_max=db_filter.price_max,
        mileage_min=db_filter.mileage_min,
        mileage_max=db_filter.mileage_max,
        year_min=db_filter.year_min,
        year_max=db_filter.year_max,
        min_match_score=db_filter.min_match_score,
        search_url=db_filter.search_url,
        include_keywords=[k.keyword for k in keywords if k.keyword_type == "include"],
        exclude_keywords=[k.keyword for k in keywords if k.keyword_type == "exclude"],
        created_at=db_filter.created_at,
        updated_at=db_filter.updated_at,
    )


def create_filter(db: Session, data: FilterCreate) -> Filter:
    validate_filter_data(data)
    db_filter = Filter(
        name=data.name,
        is_active=data.is_active,
        country=data.country,
        city=data.city,
        radius_km=data.radius_km,
        brands=_serialize_list(data.brands),
        models=_serialize_list(data.models),
        fuel_types=_serialize_list(data.fuel_types),
        transmission_types=_serialize_list(data.transmission_types),
        price_min=data.price_min,
        price_max=data.price_max,
        mileage_min=data.mileage_min,
        mileage_max=data.mileage_max,
        year_min=data.year_min,
        year_max=data.year_max,
        min_match_score=data.min_match_score,
        search_url=data.search_url,
    )
    db.add(db_filter)
    db.commit()
    db.refresh(db_filter)

    for kw in data.include_keywords:
        db.add(FilterKeyword(filter_id=db_filter.id, keyword=kw, keyword_type="include"))
    for kw in data.exclude_keywords:
        db.add(FilterKeyword(filter_id=db_filter.id, keyword=kw, keyword_type="exclude"))
    db.commit()
    return db_filter


def update_filter(db: Session, db_filter: Filter, data: FilterCreate) -> Filter:
    validate_filter_data(data)
    db_filter.name = data.name
    db_filter.is_active = data.is_active
    db_filter.country = data.country
    db_filter.city = data.city
    db_filter.radius_km = data.radius_km
    db_filter.brands = _serialize_list(data.brands)
    db_filter.models = _serialize_list(data.models)
    db_filter.fuel_types = _serialize_list(data.fuel_types)
    db_filter.transmission_types = _serialize_list(data.transmission_types)
    db_filter.price_min = data.price_min
    db_filter.price_max = data.price_max
    db_filter.mileage_min = data.mileage_min
    db_filter.mileage_max = data.mileage_max
    db_filter.year_min = data.year_min
    db_filter.year_max = data.year_max
    db_filter.min_match_score = data.min_match_score
    db_filter.search_url = data.search_url

    db.query(FilterKeyword).filter(FilterKeyword.filter_id == db_filter.id).delete()
    for kw in data.include_keywords:
        db.add(FilterKeyword(filter_id=db_filter.id, keyword=kw, keyword_type="include"))
    for kw in data.exclude_keywords:
        db.add(FilterKeyword(filter_id=db_filter.id, keyword=kw, keyword_type="exclude"))
    db.commit()
    db.refresh(db_filter)
    return db_filter
