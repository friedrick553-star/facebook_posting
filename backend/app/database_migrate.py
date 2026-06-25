"""Lightweight column migrations for existing databases (SQLite + PostgreSQL)."""
from pathlib import Path

from sqlalchemy import func, inspect, text

from app.database import Base, SessionLocal, engine

LEGACY_INTERVAL_PRESETS = {
    (120, 180),
    (120, 300),
    (180, 420),
    (300, 600),
    (600, 900),
}


def ensure_user_scoped_columns() -> None:
    """Per-user products, monitoring, and session dirs."""
    import shutil

    from app.config import get_settings
    from app.models import MonitoringSetting, ProductPost, User, UserRole
    from app.services.user_workspace import user_session_file

    inspector = inspect(engine)
    settings = get_settings()
    backend_root = Path(__file__).resolve().parent.parent

    if inspector.has_table("product_posts"):
        existing = {c["name"] for c in inspector.get_columns("product_posts")}
        if "user_id" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_posts ADD COLUMN user_id INTEGER"))

    if inspector.has_table("monitoring_settings"):
        existing = {c["name"] for c in inspector.get_columns("monitoring_settings")}
        if "user_id" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE monitoring_settings ADD COLUMN user_id INTEGER"))

    db = SessionLocal()
    try:
        primary = db.query(User).filter(User.is_primary == True).first()
        if not primary:
            primary = db.query(User).filter(User.role == UserRole.ADMIN).order_by(User.id.asc()).first()
        if not primary:
            return

        if inspector.has_table("product_posts"):
            db.query(ProductPost).filter(ProductPost.user_id.is_(None)).update(
                {ProductPost.user_id: primary.id}, synchronize_session=False
            )

        if inspector.has_table("monitoring_settings"):
            orphan_rows = db.query(MonitoringSetting).filter(MonitoringSetting.user_id.is_(None)).all()
            for row in orphan_rows:
                row.user_id = primary.id
            db.commit()

        # Co-admin concept removed — non-primary admins become regular users.
        db.query(User).filter(
            User.is_primary == False,
            User.role == UserRole.ADMIN,
        ).update({User.role: UserRole.USER}, synchronize_session=False)

        if inspector.has_table("monitoring_settings"):
            legacy_session = backend_root / settings.FACEBOOK_SESSION_FILE
            if legacy_session.exists():
                target = user_session_file(primary.id, settings)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy_session, target)

        db.commit()
    finally:
        db.close()


def ensure_test_full_flow_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("monitoring_settings"):
        return
    existing = {c["name"] for c in inspector.get_columns("monitoring_settings")}
    if "test_full_flow" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    "ADD COLUMN test_full_flow BOOLEAN NOT NULL DEFAULT 0"
                )
            )


def ensure_monitoring_interval_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("monitoring_settings"):
        return
    existing = {c["name"] for c in inspector.get_columns("monitoring_settings")}
    with engine.begin() as conn:
        if "refresh_interval_min_seconds" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    "ADD COLUMN refresh_interval_min_seconds INTEGER NOT NULL DEFAULT 30"
                )
            )
        if "refresh_interval_max_seconds" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE monitoring_settings "
                    "ADD COLUMN refresh_interval_max_seconds INTEGER NOT NULL DEFAULT 45"
                )
            )


def ensure_product_posts_table() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("product_posts"):
        from app.models.product import ProductPost  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[ProductPost.__table__])


def ensure_schedule_date_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("product_posts"):
        return
    existing = {c["name"] for c in inspector.get_columns("product_posts")}
    if "schedule_date" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE product_posts ADD COLUMN schedule_date VARCHAR(10)"))


def ensure_product_listing_columns() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("product_posts"):
        return
    existing = {c["name"] for c in inspector.get_columns("product_posts")}
    with engine.begin() as conn:
        if "category" not in existing:
            conn.execute(text("ALTER TABLE product_posts ADD COLUMN category VARCHAR(255)"))
        if "condition" not in existing:
            conn.execute(text("ALTER TABLE product_posts ADD COLUMN condition VARCHAR(50) NOT NULL DEFAULT 'new'"))
        if "availability" not in existing:
            conn.execute(text("ALTER TABLE product_posts ADD COLUMN availability VARCHAR(50) NOT NULL DEFAULT 'single'"))
        if "extra_details" not in existing:
            conn.execute(text("ALTER TABLE product_posts ADD COLUMN extra_details TEXT NOT NULL DEFAULT '{}'"))


def ensure_users_primary_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return
    existing = {c["name"] for c in inspector.get_columns("users")}
    if "is_primary" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT 0")
            )

    from app.config import get_settings
    from app.models import User, UserRole

    settings = get_settings()
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    db = SessionLocal()
    try:
        primary = db.query(User).filter(User.is_primary == True).first()
        if not primary:
            candidate = None
            if admin_email:
                candidate = (
                    db.query(User)
                    .filter(func.lower(User.email) == admin_email)
                    .order_by(User.id.asc())
                    .first()
                )
            if not candidate:
                candidate = (
                    db.query(User)
                    .filter(User.role == UserRole.ADMIN)
                    .order_by(User.id.asc())
                    .first()
                )
            if candidate:
                candidate.is_primary = True
                db.commit()
    finally:
        db.close()


def migrate_legacy_monitoring_intervals() -> None:
    """Move old slow reload presets to the new default check interval."""
    from app.models import MonitoringSetting

    db = SessionLocal()
    try:
        row = db.query(MonitoringSetting).first()
        if not row:
            return
        current = (row.refresh_interval_min_seconds, row.refresh_interval_max_seconds)
        if current in LEGACY_INTERVAL_PRESETS:
            row.refresh_interval_min_seconds = 30
            row.refresh_interval_max_seconds = 45
            row.refresh_interval_seconds = 45
            db.commit()
    finally:
        db.close()
