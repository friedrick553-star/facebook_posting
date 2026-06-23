import json

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models import (
    ApplicationSetting,
    Filter,
    FilterKeyword,
    FilterTemplate,
    MonitoringSetting,
    NotificationRecipient,
    User,
    UserRole,
)


DEFAULT_FILTER = {
    "name": "Zurich Vehicle Search",
    "is_active": True,
    "country": "Switzerland",
    "city": "Zurich",
    "radius_km": 65,
    "brands": [
        "Volkswagen", "VW", "Audi", "BMW", "Mercedes", "Mercedes-Benz",
        "Skoda", "Seat", "Ford", "Opel", "Renault", "Peugeot", "Toyota",
        "Honda", "Hyundai", "Fiat", "Volvo", "Suzuki", "Mini", "Dacia",
    ],
    "models": [
        "VW Golf", "Golf", "Passat", "Polo", "Tiguan", "Touran",
        "Audi A3", "Audi A4", "A3", "A4", "A6",
        "Skoda Octavia", "Octavia", "Superb", "Fabia",
        "Seat Leon", "Leon", "Ibiza",
        "BMW 3", "BMW 5", "Serie 3", "Serie 5",
        "Focus", "Fiesta", "Corolla", "Yaris",
    ],
    "fuel_types": [],
    "transmission_types": [],
    "price_min": 3000,
    "price_max": 7000,
    "mileage_min": None,
    "mileage_max": None,
    "year_min": None,
    "year_max": None,
    "min_match_score": 80.0,
    "include_keywords": [],
    "exclude_keywords": [
        "Motorschaden", "Defekt", "Bastlerfahrzeug", "Export",
        "Unfallfahrzeug", "Kein MFK", "Ersatzteile", "Schlachtfahrzeug",
    ],
}


def ensure_admin_user(db: Session, admin_email: str, admin_password: str) -> User | None:
    """Create or sync admin from backend .env (startup seed only — not on every login)."""
    if not admin_email or not admin_password:
        return None

    email = admin_email.strip().lower()
    admin = db.query(User).filter(User.is_primary == True).first()
    if not admin:
        admin = db.query(User).filter(User.role == UserRole.ADMIN).order_by(User.id.asc()).first()
    if not admin:
        admin = User(
            email=email,
            hashed_password=get_password_hash(admin_password),
            full_name="Administrator",
            role=UserRole.ADMIN,
            is_primary=True,
        )
        db.add(admin)
    else:
        admin.email = email
        admin.is_primary = True
        if not verify_password(admin_password, admin.hashed_password):
            admin.hashed_password = get_password_hash(admin_password)
    for other in db.query(User).filter(User.id != admin.id, User.is_primary == True).all():
        other.is_primary = False
    db.commit()
    db.refresh(admin)
    return admin


def seed_database(db: Session, admin_email: str, admin_password: str) -> None:
    admin = ensure_admin_user(db, admin_email, admin_password)
    if not admin_email or not admin_password:
        return

    if admin and not db.query(MonitoringSetting).filter(MonitoringSetting.user_id == admin.id).first():
        db.add(MonitoringSetting(
            user_id=admin.id,
            is_enabled=False,
            refresh_interval_seconds=45,
            refresh_interval_min_seconds=30,
            refresh_interval_max_seconds=45,
        ))
        db.commit()

    if not db.query(Filter).first():
        f = Filter(
            name=DEFAULT_FILTER["name"],
            is_active=DEFAULT_FILTER["is_active"],
            country=DEFAULT_FILTER["country"],
            city=DEFAULT_FILTER["city"],
            radius_km=DEFAULT_FILTER["radius_km"],
            brands=json.dumps(DEFAULT_FILTER["brands"]),
            models=json.dumps(DEFAULT_FILTER["models"]),
            fuel_types=json.dumps(DEFAULT_FILTER["fuel_types"]),
            transmission_types=json.dumps(DEFAULT_FILTER["transmission_types"]),
            price_min=DEFAULT_FILTER["price_min"],
            price_max=DEFAULT_FILTER["price_max"],
            mileage_max=DEFAULT_FILTER["mileage_max"],
            min_match_score=DEFAULT_FILTER["min_match_score"],
        )
        db.add(f)
        db.commit()
        db.refresh(f)

        for kw in DEFAULT_FILTER["include_keywords"]:
            db.add(FilterKeyword(filter_id=f.id, keyword=kw, keyword_type="include"))
        for kw in DEFAULT_FILTER["exclude_keywords"]:
            db.add(FilterKeyword(filter_id=f.id, keyword=kw, keyword_type="exclude"))

    default_settings = {
        "notifications_enabled": "true",
        "app_theme": "light",
        "playwright_headless": "false",
    }
    for key, value in default_settings.items():
        if not db.query(ApplicationSetting).filter(ApplicationSetting.key == key).first():
            category = (
                "notification" if key == "notifications_enabled"
                else "browser" if key == "playwright_headless"
                else "general"
            )
            db.add(ApplicationSetting(key=key, value=value, category=category))

    db.commit()
