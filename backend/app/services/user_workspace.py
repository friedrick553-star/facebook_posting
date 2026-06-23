"""Per-user data dirs (cookies, profile) — posting flow unchanged; paths resolved via context."""
from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path

from app.config import Settings, get_settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


_current_user_id: ContextVar[int | None] = ContextVar("workspace_user_id", default=None)


def set_workspace_user_id(user_id: int | None) -> Token:
    return _current_user_id.set(user_id)


def reset_workspace_user_id(token: Token) -> None:
    _current_user_id.reset(token)


def get_workspace_user_id() -> int | None:
    return _current_user_id.get()


def user_data_root(user_id: int, cfg: Settings | None = None) -> Path:
    root = _BACKEND_ROOT / "data" / "users" / str(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_session_file(user_id: int, cfg: Settings | None = None) -> Path:
    path = user_data_root(user_id, cfg) / "facebook_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def user_profile_dir(user_id: int, cfg: Settings | None = None) -> Path:
    path = user_data_root(user_id, cfg) / "facebook_chrome_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_session_file(cfg: Settings | None = None) -> Path:
    cfg = cfg or get_settings()
    uid = get_workspace_user_id()
    if uid is not None:
        return user_session_file(uid, cfg)
    path = _BACKEND_ROOT / cfg.FACEBOOK_SESSION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_profile_dir(cfg: Settings | None = None) -> Path:
    cfg = cfg or get_settings()
    uid = get_workspace_user_id()
    if uid is not None:
        return user_profile_dir(uid, cfg)
    path = _BACKEND_ROOT / cfg.FACEBOOK_PROFILE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
