"""First-run admin setup — browser UI writes credentials to .env and DB."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"


def is_admin_setup_needed(db: Session) -> bool:
    """True when no primary admin exists yet (first visit setup)."""
    return db.query(User).filter(User.is_primary == True).first() is None


def _env_line(key: str, value: str) -> str:
    if re.search(r'[\s#="\']', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def persist_admin_env(email: str, password: str) -> None:
    """Write ADMIN_EMAIL and ADMIN_PASSWORD to backend/.env."""
    updates = {
        "ADMIN_EMAIL": email.strip(),
        "ADMIN_PASSWORD": password,
    }
    if not _ENV_PATH.exists():
        lines = [_env_line(k, v) for k, v in updates.items()]
        _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    raw = _ENV_PATH.read_text(encoding="utf-8")
    lines = raw.splitlines()
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        matched = False
        for key, val in updates.items():
            if line.startswith(f"{key}="):
                new_lines.append(_env_line(key, val))
                seen.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in seen:
            new_lines.append(_env_line(key, val))

    trailing_newline = raw.endswith("\n") or not raw
    text = "\n".join(new_lines)
    if trailing_newline:
        text += "\n"
    _ENV_PATH.write_text(text, encoding="utf-8")


def reload_settings() -> None:
    get_settings.cache_clear()
