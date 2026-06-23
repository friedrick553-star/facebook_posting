import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.database import get_db
from app.models import Filter, FilterTemplate, Listing, ListingStatus, User
from app.services.listing_query import matched_listings_query
from app.repositories.filter_repo import create_filter, filter_to_response, update_filter
from app.schemas import (
    FilterCreate,
    FilterResponse,
    FilterTemplateCreate,
    FilterTemplateResponse,
    FilterUpdate,
    ListingResponse,
    LogsBulkDelete,
)

router = APIRouter(tags=["Filters & Listings"])


@router.get("/filters", response_model=list[FilterResponse])
def list_filters(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    filters = db.query(Filter).order_by(desc(Filter.created_at)).all()
    return [filter_to_response(f, db) for f in filters]


@router.post("/filters", response_model=FilterResponse)
def create_filter_endpoint(
    data: FilterCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        db_filter = create_filter(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter_to_response(db_filter, db)


@router.get("/filters/{filter_id}", response_model=FilterResponse)
def get_filter(filter_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    db_filter = db.query(Filter).filter(Filter.id == filter_id).first()
    if not db_filter:
        raise HTTPException(status_code=404, detail="Filter not found")
    return filter_to_response(db_filter, db)


@router.put("/filters/{filter_id}", response_model=FilterResponse)
def update_filter_endpoint(
    filter_id: int,
    data: FilterCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    db_filter = db.query(Filter).filter(Filter.id == filter_id).first()
    if not db_filter:
        raise HTTPException(status_code=404, detail="Filter not found")
    try:
        updated = update_filter(db, db_filter, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter_to_response(updated, db)


@router.delete("/filters/{filter_id}")
def delete_filter(filter_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db_filter = db.query(Filter).filter(Filter.id == filter_id).first()
    if not db_filter:
        raise HTTPException(status_code=404, detail="Filter not found")
    db.delete(db_filter)
    db.commit()
    return {"message": "Filter deleted"}


@router.get("/filter-templates", response_model=list[FilterTemplateResponse])
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(FilterTemplate).order_by(desc(FilterTemplate.created_at)).all()


@router.post("/filter-templates", response_model=FilterTemplateResponse)
def create_template(
    data: FilterTemplateCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    template = FilterTemplate(
        name=data.name,
        config_json=data.filter_data.model_dump_json(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.post("/filter-templates/{template_id}/load", response_model=FilterResponse)
def load_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    template = db.query(FilterTemplate).filter(FilterTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    filter_data = FilterCreate.model_validate_json(template.config_json)
    filter_data.name = f"{filter_data.name} (from template)"
    db_filter = create_filter(db, filter_data)
    return filter_to_response(db_filter, db)


@router.post("/filter-templates/{template_id}/duplicate", response_model=FilterTemplateResponse)
def duplicate_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    template = db.query(FilterTemplate).filter(FilterTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    new_template = FilterTemplate(
        name=f"{template.name} (Copy)",
        config_json=template.config_json,
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template


@router.delete("/filter-templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    template = db.query(FilterTemplate).filter(FilterTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"message": "Template deleted"}


def _listing_to_response(listing: Listing) -> ListingResponse:
    images = []
    if listing.images:
        try:
            images = json.loads(listing.images)
        except json.JSONDecodeError:
            images = []
    match_details = None
    if listing.match_details:
        try:
            match_details = json.loads(listing.match_details)
        except json.JSONDecodeError:
            pass
    return ListingResponse(
        id=listing.id,
        external_id=listing.external_id,
        source=listing.source,
        url=listing.url,
        title=listing.title,
        price=listing.price,
        currency=listing.currency,
        mileage=listing.mileage,
        year=listing.year,
        brand=listing.brand,
        model=listing.model,
        fuel_type=listing.fuel_type,
        transmission=listing.transmission,
        description=listing.description,
        location=listing.location,
        seller_name=listing.seller_name,
        images=images,
        posted_time=listing.posted_time,
        match_score=listing.match_score,
        status=listing.status.value,
        match_details=match_details,
        is_duplicate=listing.is_duplicate,
        notification_sent=listing.notification_sent,
        found_at=listing.found_at,
    )


@router.get("/listings", response_model=dict)
def list_listings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    today: bool = False,
    sort_by: str = "found_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if status:
        query = db.query(Listing).filter(Listing.status == status)
    else:
        query = matched_listings_query(db)
    if search:
        query = query.filter(
            or_(
                Listing.title.ilike(f"%{search}%"),
                Listing.location.ilike(f"%{search}%"),
                Listing.brand.ilike(f"%{search}%"),
            )
        )
    if status:
        query = query.filter(Listing.status == status)
    if today:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(Listing.found_at >= today_start)

    sort_col = getattr(Listing, sort_by, Listing.found_at)
    query = query.order_by(desc(sort_col) if sort_order == "desc" else sort_col)

    total = query.count()
    listings = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_listing_to_response(l) for l in listings],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/listings/{listing_id}", response_model=ListingResponse)
def get_listing(listing_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_to_response(listing)


@router.get("/listings/export/csv")
def export_listings_csv(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    listings = matched_listings_query(db).order_by(desc(Listing.found_at)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Price", "Currency", "Mileage", "Year", "Location", "Score", "Status", "URL", "Found At"])
    for l in listings:
        writer.writerow([
            l.external_id, l.title, l.price, l.currency, l.mileage, l.year,
            l.location, l.match_score, l.status.value, l.url, l.found_at.isoformat(),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=listings.csv"},
    )


@router.delete("/listings/all")
def delete_all_listings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deleted = db.query(Listing).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": f"Deleted {deleted} listings"}


@router.delete("/listings")
def delete_listings(
    data: LogsBulkDelete,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not data.ids:
        return {"deleted": 0, "message": "No listings selected"}
    deleted = db.query(Listing).filter(Listing.id.in_(data.ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted, "message": f"Deleted {deleted} listings"}
