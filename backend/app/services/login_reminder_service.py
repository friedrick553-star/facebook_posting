"""Email when Facebook login is missing or the user is logged out."""
from __future__ import annotations

import logging
import time

from app.config import get_settings
from app.database import SessionLocal
from app.models import ApplicationSetting, LogCategory, LogLevel, NotificationRecipient
from app.services.email_service import email_service
from app.services.log_service import log_activity_isolated

logger = logging.getLogger(__name__)

LOGIN_REMINDER_AFTER_SECONDS = 300  # 5 minutes after browser opens
LOGOUT_EMAIL_COOLDOWN_SECONDS = 3600
_last_logout_email_at: float = 0.0

LOGIN_REMINDER_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; padding: 32px; background: #f4f6f9;">
  <div style="max-width: 520px; margin: 0 auto; background: white; padding: 28px; border-radius: 12px;">
    <h2 style="color: #1877f2; margin-top: 0;">Facebook login required</h2>
    <p>Facebook Posting is ON but Facebook is not logged in yet.</p>
    <p><strong>Open the visible Chromium window and log in to Facebook manually</strong> (including any 2FA).</p>
    <p style="color: #65676b; font-size: 14px;">Posting will continue automatically once login is complete.</p>
    <p style="color: #65676b; font-size: 12px; margin-top: 24px;">Facebook Posting</p>
  </div>
</body>
</html>
"""


def _notifications_enabled() -> bool:
    db = SessionLocal()
    try:
        row = db.query(ApplicationSetting).filter(ApplicationSetting.key == "notifications_enabled").first()
        return row is None or row.value != "false"
    finally:
        db.close()


def _reminder_recipients() -> list[str]:
    settings = get_settings()
    emails: list[str] = []
    admin = (settings.ADMIN_EMAIL or "").strip().lower()
    if admin and "@" in admin:
        emails.append(admin)

    db = SessionLocal()
    try:
        rows = db.query(NotificationRecipient).filter(NotificationRecipient.is_active == True).all()
        for row in rows:
            addr = (row.email or "").strip().lower()
            if addr and "@" in addr and addr not in emails:
                emails.append(addr)
    finally:
        db.close()
    return emails


async def send_facebook_logout_alert(*, force: bool = False) -> bool:
    """Email admin + alert recipients when Facebook is logged out (max once per hour)."""
    global _last_logout_email_at
    if not force and not _notifications_enabled():
        return False

    now = time.monotonic()
    if not force and now - _last_logout_email_at < LOGOUT_EMAIL_COOLDOWN_SECONDS:
        return False

    recipients = _reminder_recipients()
    if not recipients:
        log_activity_isolated(
            LogCategory.NOTIFICATION,
            "Login reminder skipped — no admin or alert email configured",
            level=LogLevel.WARNING,
            source="facebook",
        )
        return False

    settings = get_settings()
    smtp = settings.smtp_config_dict()
    subject = "Action required — log in to Facebook for Marketplace posting"
    sent_any = False
    errors: list[str] = []

    for to_email in recipients:
        ok, msg = await email_service.send_email(to_email, subject, LOGIN_REMINDER_HTML, smtp)
        if ok:
            sent_any = True
            logger.info("Facebook login reminder sent to %s", to_email)
        else:
            errors.append(f"{to_email}: {msg}")

    if sent_any:
        _last_logout_email_at = now
        log_activity_isolated(
            LogCategory.NOTIFICATION,
            "Facebook login reminder email sent — please log in manually in the browser",
            details={"recipients": recipients},
            source="facebook",
        )
    elif errors:
        log_activity_isolated(
            LogCategory.ERROR,
            "Could not send Facebook login reminder email",
            level=LogLevel.ERROR,
            details={"errors": errors},
            source="facebook",
        )
    return sent_any


async def send_facebook_login_reminder(*, force: bool = False) -> bool:
    """After 5 minutes waiting for manual login, or test from Settings."""
    return await send_facebook_logout_alert(force=force)
