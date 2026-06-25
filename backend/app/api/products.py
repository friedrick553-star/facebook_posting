import json
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.core.db_ready import require_db_ready
from app.core.deps import get_current_user, require_admin
from app.database import get_db
from app.models import ProductPost, ProductStatus, User, product_content_hash
from app.models.product import CATALOG_STATUSES
from app.schemas import (
    ProductBulkDelete,
    ProductStatsResponse,
    ProductUpdate,
    ProductResponse,
    PaginatedProductsResponse,
)
from app.services.product_csv import parse_products_csv

router = APIRouter(prefix="/products", tags=["Products"])

_SCHEDULE_DAY_ORDER = case(
    (ProductPost.schedule_day == "mon", 0),
    (ProductPost.schedule_day == "tue", 1),
    (ProductPost.schedule_day == "wed", 2),
    (ProductPost.schedule_day == "thu", 3),
    (ProductPost.schedule_day == "fri", 4),
    (ProductPost.schedule_day == "sat", 5),
    (ProductPost.schedule_day == "sun", 6),
    else_=99,
)


def _product_has_schedule(p: ProductPost) -> bool:
    if not p.schedule_time:
        return False
    return bool(p.schedule_date or p.schedule_day)


def _apply_product_sort(q, status: str | None, sort: str | None):
    effective = sort
    if not effective and status == "scheduled":
        effective = "schedule"
    elif not effective and status == "published":
        effective = "published"

    if effective == "schedule":
        return q.order_by(
            ProductPost.schedule_date.asc().nulls_last(),
            ProductPost.schedule_time.asc().nulls_last(),
            _SCHEDULE_DAY_ORDER.asc(),
            ProductPost.id.asc(),
        )
    if effective == "published":
        return q.order_by(
            ProductPost.published_at.desc().nulls_last(),
            ProductPost.id.desc(),
        )
    if effective == "newest":
        return q.order_by(ProductPost.created_at.desc(), ProductPost.id.desc())
    return q.order_by(ProductPost.id.asc())


def _images_list(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _extra_details_dict(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except json.JSONDecodeError:
        pass
    return {}


def _to_response(p: ProductPost) -> ProductResponse:
    return ProductResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        price=p.price,
        currency=p.currency,
        images=_images_list(p.images),
        category=p.category,
        condition=getattr(p, "condition", None) or "new",
        availability=getattr(p, "availability", None) or "single",
        extra_details=_extra_details_dict(getattr(p, "extra_details", "{}")),
        schedule_date=p.schedule_date,
        schedule_day=p.schedule_day,
        schedule_time=p.schedule_time,
        status=p.status.value,
        facebook_url=p.facebook_url,
        error_message=p.error_message,
        retry_count=p.retry_count,
        batch_label=p.batch_label,
        published_at=p.published_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _apply_schedule_status(p: ProductPost) -> None:
    if p.status in (ProductStatus.PUBLISHED, ProductStatus.PUBLISHING, ProductStatus.DUPLICATE, ProductStatus.MISSING):
        return
    if _product_has_schedule(p):
        p.status = ProductStatus.SCHEDULED
    elif p.status == ProductStatus.SCHEDULED:
        p.status = ProductStatus.PENDING


def _products_query(db: Session, user: User):
    return db.query(ProductPost).filter(ProductPost.user_id == user.id)


def _get_user_product(db: Session, user: User, product_id: int) -> ProductPost | None:
    return (
        _products_query(db, user)
        .filter(ProductPost.id == product_id)
        .first()
    )


def _product_from_row(
    row,
    *,
    user_id: int,
    status: ProductStatus,
    batch_label: str,
    content_hash: str,
    error_message: str | None = None,
) -> ProductPost:
    return ProductPost(
        user_id=user_id,
        name=row.name,
        description=row.description or "",
        price=row.price,
        currency=row.currency,
        images=json.dumps(row.images),
        category=row.category,
        condition=row.condition or "new",
        availability=row.availability or "single",
        extra_details=json.dumps(row.extra_details),
        schedule_date=row.schedule_date,
        schedule_day=None,
        schedule_time=row.schedule_time,
        status=status,
        content_hash=content_hash,
        batch_label=batch_label,
        error_message=error_message,
    )


@router.get("/stats", response_model=ProductStatsResponse)
def product_stats(
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    catalog_q = _products_query(db, current_user).filter(ProductPost.status.in_(CATALOG_STATUSES))
    total = catalog_q.count()
    pending = catalog_q.filter(ProductPost.status == ProductStatus.PENDING).count()
    scheduled = catalog_q.filter(ProductPost.status == ProductStatus.SCHEDULED).count()
    published = catalog_q.filter(ProductPost.status == ProductStatus.PUBLISHED).count()
    failed = catalog_q.filter(ProductPost.status == ProductStatus.FAILED).count()
    duplicate = _products_query(db, current_user).filter(ProductPost.status == ProductStatus.DUPLICATE).count()
    missing = _products_query(db, current_user).filter(ProductPost.status == ProductStatus.MISSING).count()
    return ProductStatsResponse(
        total=total,
        pending=pending,
        scheduled=scheduled,
        published=published,
        failed=failed,
        duplicate=duplicate,
        missing=missing,
    )


@router.get("/image-proxy")
async def product_image_proxy(
    url: str = Query(..., min_length=8, max_length=2048),
):
    """Fetch external product images server-side (public — img tags cannot send JWT)."""
    target = url.strip()
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid image URL")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(
                target,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; FacebookPosting/1.0)",
                    "Accept": "image/*,*/*",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not fetch image") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Image not found")

    content_type = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="URL is not an image")

    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("", response_model=PaginatedProductsResponse)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    catalog: bool = Query(False, description="Only main products (exclude missing/duplicate)"),
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _products_query(db, current_user)
    if catalog:
        q = q.filter(ProductPost.status.in_(CATALOG_STATUSES))
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(ProductPost.name.ilike(like) | ProductPost.description.ilike(like))
    if status:
        try:
            q = q.filter(ProductPost.status == ProductStatus(status))
        except ValueError:
            pass
    total = q.count()
    items = (
        _apply_product_sort(q, status, sort)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedProductsResponse(
        items=[_to_response(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.post("/upload-csv")
async def upload_products_csv(
    file: UploadFile = File(...),
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV file too large (max 5 MB)")

    parsed = parse_products_csv(content)
    if parsed.errors and not parsed.valid_rows and not parsed.incomplete_rows:
        raise HTTPException(status_code=400, detail=parsed.errors[0])

    batch_label = file.filename
    db_hashes = {
        h
        for (h,) in _products_query(db, current_user)
        .filter(ProductPost.status.in_(CATALOG_STATUSES))
        .all()
    }

    imported = 0
    missing_count = 0
    duplicate_count = 0
    seen_in_batch: set[str] = set()
    missing_preview: list[dict] = []

    for row, missing_fields in parsed.incomplete_rows:
        h = product_content_hash(row.name, row.description, row.price)
        msg = f"Missing: {', '.join(missing_fields)}"
        db.add(
            _product_from_row(
                row,
                user_id=current_user.id,
                status=ProductStatus.MISSING,
                batch_label=batch_label,
                content_hash=h,
                error_message=msg,
            )
        )
        missing_count += 1
        missing_preview.append(
            {"row": row.row_number, "name": row.name, "missing_fields": missing_fields}
        )

    for row in parsed.valid_rows:
        h = product_content_hash(row.name, row.description, row.price)
        if h in seen_in_batch or h in db_hashes:
            db.add(
                _product_from_row(
                    row,
                    user_id=current_user.id,
                    status=ProductStatus.DUPLICATE,
                    batch_label=batch_label,
                    content_hash=h,
                    error_message="Duplicate — same name, description and price already exists",
                )
            )
            duplicate_count += 1
            continue

        db.add(
            _product_from_row(
                row,
                user_id=current_user.id,
                status=ProductStatus.SCHEDULED,
                batch_label=batch_label,
                content_hash=h,
            )
        )
        seen_in_batch.add(h)
        imported += 1

    db.commit()
    return {
        "total_rows": len(parsed.valid_rows) + len(parsed.incomplete_rows),
        "imported": imported,
        "missing": missing_count,
        "duplicates_skipped": duplicate_count,
        "already_exists": duplicate_count,
        "missing_rows": missing_preview[:20],
        "parse_warnings": parsed.errors,
        "batch_label": batch_label,
    }


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    product = _get_user_product(db, current_user, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if data.name is not None:
        product.name = data.name.strip()
    if data.description is not None:
        product.description = data.description
    if data.price is not None:
        product.price = data.price
    if data.currency is not None:
        product.currency = data.currency.upper()[:10]
    if data.images is not None:
        product.images = json.dumps(data.images)
    if data.category is not None:
        product.category = data.category.strip() or None
    if data.condition is not None:
        product.condition = data.condition.strip() or "new"
    if data.availability is not None:
        product.availability = data.availability.strip() or "single"
    if data.extra_details is not None:
        product.extra_details = json.dumps(data.extra_details)
    if data.schedule_date is not None:
        from app.services.product_csv import parse_schedule_date

        if data.schedule_date:
            parsed = parse_schedule_date(data.schedule_date)
            if not parsed:
                raise HTTPException(status_code=400, detail="Invalid schedule_date — use YYYY-MM-DD or DD/MM/YYYY")
            product.schedule_date = parsed
            product.schedule_day = None
        else:
            product.schedule_date = None
    if data.schedule_day is not None:
        product.schedule_day = data.schedule_day or None
    if data.schedule_time is not None:
        product.schedule_time = data.schedule_time or None

    product.content_hash = product_content_hash(product.name, product.description, product.price)
    _apply_schedule_status(product)
    db.commit()
    db.refresh(product)
    return _to_response(product)


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    product = _get_user_product(db, current_user, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"deleted": 1}


@router.delete("")
def delete_products_bulk(
    data: ProductBulkDelete,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not data.ids:
        return {"deleted": 0}
    deleted = (
        _products_query(db, current_user)
        .filter(ProductPost.id.in_(data.ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


MAX_PRODUCT_RETRIES = 5


@router.post("/{product_id}/retry", response_model=ProductResponse)
def retry_failed_product(
    product_id: int,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    product = _get_user_product(db, current_user, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != ProductStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed products can be retried")
    if product.retry_count >= MAX_PRODUCT_RETRIES:
        raise HTTPException(status_code=400, detail=f"Maximum retries ({MAX_PRODUCT_RETRIES}) reached")

    from app.services.product_posting_service import _now_local

    now = _now_local()
    product.error_message = None
    product.schedule_date = now.strftime("%Y-%m-%d")
    product.schedule_day = None
    product.schedule_time = f"{now.hour:02d}:{now.minute:02d}"
    product.status = ProductStatus.SCHEDULED
    db.commit()
    db.refresh(product)
    return _to_response(product)


@router.post("/{product_id}/publish", response_model=ProductResponse)
async def publish_product_now(
    product_id: int,
    _: None = Depends(require_db_ready),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.services.product_posting_service import publish_product

    product = _get_user_product(db, current_user, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status in (ProductStatus.PUBLISHED, ProductStatus.PUBLISHING, ProductStatus.DUPLICATE):
        raise HTTPException(status_code=400, detail="Product cannot be published in its current state")
    if product.retry_count >= MAX_PRODUCT_RETRIES:
        raise HTTPException(status_code=400, detail=f"Maximum retries ({MAX_PRODUCT_RETRIES}) reached")

    try:
        await publish_product(db, product)
    except Exception as exc:
        db.refresh(product)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.refresh(product)
    return _to_response(product)

