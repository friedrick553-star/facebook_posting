from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_serializer

from app.core.datetime_json import serialize_api_datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminSetupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_primary: bool = False
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = "user"


class UserAdminUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6)


class FacebookSessionImport(BaseModel):
    cookies: str = Field(min_length=10, description="document.cookie, JSON array, or Playwright storage_state")


class FacebookSessionStatus(BaseModel):
    has_session: bool
    cookie_count: int = 0


class FilterKeywordSchema(BaseModel):
    id: int | None = None
    keyword: str
    keyword_type: str


class FilterCreate(BaseModel):
    name: str
    is_active: bool = True
    country: str | None = None
    city: str | None = None
    radius_km: int | None = None
    brands: list[str] = []
    models: list[str] = []
    fuel_types: list[str] = []
    transmission_types: list[str] = []
    price_min: float | None = None
    price_max: float | None = None
    mileage_min: int | None = None
    mileage_max: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    min_match_score: float = 80.0
    search_url: str | None = None
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []


class FilterUpdate(FilterCreate):
    name: str | None = None


class FilterResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    country: str | None
    city: str | None
    radius_km: int | None
    brands: list[str]
    models: list[str]
    fuel_types: list[str]
    transmission_types: list[str]
    price_min: float | None
    price_max: float | None
    mileage_min: int | None
    mileage_max: int | None
    year_min: int | None
    year_max: int | None
    min_match_score: float
    search_url: str | None
    include_keywords: list[str]
    exclude_keywords: list[str]
    created_at: datetime
    updated_at: datetime


class FilterTemplateCreate(BaseModel):
    name: str
    filter_data: FilterCreate


class FilterTemplateResponse(BaseModel):
    id: int
    name: str
    config_json: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: int
    external_id: str
    source: str
    url: str
    title: str
    price: float | None
    currency: str
    mileage: int | None
    year: int | None
    brand: str | None
    model: str | None
    fuel_type: str | None
    transmission: str | None
    description: str | None
    location: str | None
    seller_name: str | None
    images: list[str]
    posted_time: str | None
    match_score: float
    status: str
    match_details: dict[str, Any] | None
    is_duplicate: bool
    notification_sent: bool
    found_at: datetime

    model_config = {"from_attributes": True}


class NotificationRecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = None
    is_active: bool = True


class NotificationRecipientResponse(BaseModel):
    id: int
    email: str
    name: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    id: int
    listing_id: int
    recipient_email: str
    status: str
    delivery_result: str | None
    sent_at: datetime | None
    created_at: datetime
    listing_title: str | None = None

    model_config = {"from_attributes": True}


class MonitoringSettingsUpdate(BaseModel):
    is_enabled: bool | None = None
    refresh_interval_seconds: int | None = None
    refresh_interval_min_seconds: int | None = None
    refresh_interval_max_seconds: int | None = None
    test_full_flow: bool | None = None


class MonitoringSettingsResponse(BaseModel):
    is_enabled: bool
    refresh_interval_seconds: int
    refresh_interval_min_seconds: int
    refresh_interval_max_seconds: int
    last_scan_at: datetime | None
    next_scan_at: datetime | None
    is_scanning: bool
    test_full_flow: bool = False


class ApplicationSettingsUpdate(BaseModel):
    settings: dict[str, str]


class ActivityLogResponse(BaseModel):
    id: int
    category: str
    level: str
    message: str
    details: str | None
    source: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime) -> str:
        return serialize_api_datetime(v) or ""


class LogsBulkDelete(BaseModel):
    ids: list[int]


class DashboardStats(BaseModel):
    total_listings: int
    matched_listings: int
    today_listings: int
    notifications_sent: int
    active_filters: int
    system_status: str
    last_scan_at: datetime | None
    next_scan_at: datetime | None
    is_scanning: bool
    monitoring_enabled: bool


class ChartDataPoint(BaseModel):
    date: str
    count: int


class DashboardCharts(BaseModel):
    listings_per_day: list[ChartDataPoint]
    matches_per_day: list[ChartDataPoint]
    notifications_per_day: list[ChartDataPoint]


class TestEmailRequest(BaseModel):
    email: EmailStr | None = None


class ManualScanResponse(BaseModel):
    status: str
    processed: int = 0
    matched: int = 0
    notified: int = 0
    duplicates: int = 0
    errors: int = 0


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price: float | None
    currency: str
    images: list[str]
    category: str | None = None
    condition: str = "new"
    availability: str = "single"
    extra_details: dict[str, str] = {}
    schedule_date: str | None
    schedule_day: str | None
    schedule_time: str | None
    status: str
    facebook_url: str | None
    error_message: str | None
    retry_count: int
    batch_label: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("published_at", "created_at", "updated_at")
    def _ser_product_datetimes(self, v: datetime | None) -> str | None:
        return serialize_api_datetime(v)


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    images: list[str] | None = None
    category: str | None = None
    condition: str | None = None
    availability: str | None = None
    extra_details: dict[str, str] | None = None
    schedule_date: str | None = None
    schedule_day: str | None = None
    schedule_time: str | None = None


class ProductStatsResponse(BaseModel):
    total: int
    pending: int
    scheduled: int
    published: int
    failed: int
    missed: int = 0  # deprecated — past slots count toward failed
    duplicate: int
    missing: int = 0


class PaginatedProductsResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductBulkDelete(BaseModel):
    ids: list[int]
