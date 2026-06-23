from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Filter(Base):
    __tablename__ = "filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    radius_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brands: Mapped[str | None] = mapped_column(Text, nullable=True)
    models: Mapped[str | None] = mapped_column(Text, nullable=True)
    fuel_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    transmission_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    mileage_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_match_score: Mapped[float] = mapped_column(Float, default=80.0, nullable=False)
    search_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    include_keywords = relationship(
        "FilterKeyword", back_populates="filter", cascade="all, delete-orphan",
        foreign_keys="FilterKeyword.filter_id"
    )
    exclude_keywords = relationship(
        "FilterKeyword", cascade="all, delete-orphan",
        foreign_keys="FilterKeyword.filter_id",
        overlaps="include_keywords",
        primaryjoin="and_(Filter.id==FilterKeyword.filter_id, FilterKeyword.keyword_type=='exclude')",
        viewonly=True,
    )
    listings = relationship("Listing", back_populates="filter")


class FilterKeyword(Base):
    __tablename__ = "filter_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filter_id: Mapped[int] = mapped_column(ForeignKey("filters.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    keyword_type: Mapped[str] = mapped_column(String(20), nullable=False)  # include | exclude
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    filter = relationship("Filter", back_populates="include_keywords", foreign_keys=[filter_id])


class FilterTemplate(Base):
    __tablename__ = "filter_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
