import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, sa_enum


class ListingStatus(str, enum.Enum):
    NEW = "new"
    MATCHED = "matched"
    NOTIFIED = "notified"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="facebook", index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="CHF", nullable=False)
    mileage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[ListingStatus] = mapped_column(sa_enum(ListingStatus), default=ListingStatus.NEW, nullable=False)
    filter_id: Mapped[int | None] = mapped_column(ForeignKey("filters.id"), nullable=True)
    match_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    filter = relationship("Filter", back_populates="listings")
    notifications = relationship("Notification", back_populates="listing", cascade="all, delete-orphan")
