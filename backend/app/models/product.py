import enum
import hashlib
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, sa_enum


class ProductStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    MISSING = "missing"


CATALOG_STATUSES = (
    ProductStatus.PENDING,
    ProductStatus.SCHEDULED,
    ProductStatus.PUBLISHING,
    ProductStatus.PUBLISHED,
    ProductStatus.FAILED,
)


def product_content_hash(name: str, description: str, price: float | None) -> str:
    raw = f"{name.strip().lower()}|{description.strip().lower()}|{price or 0}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ProductPost(Base):
    __tablename__ = "product_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    images: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    schedule_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_day: Mapped[str | None] = mapped_column(String(20), nullable=True)
    schedule_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        sa_enum(ProductStatus), default=ProductStatus.PENDING, nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    facebook_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    batch_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition: Mapped[str] = mapped_column(String(50), default="new", nullable=False)
    availability: Mapped[str] = mapped_column(String(50), default="single", nullable=False)
    extra_details: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
