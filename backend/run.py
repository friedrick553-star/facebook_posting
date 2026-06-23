"""
Reliable server startup — single instance, one port, no double-bind.
Usage: python run.py
"""
from __future__ import annotations

import atexit
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from app.playwright_browsers import configure_playwright_browsers_path

configure_playwright_browsers_path()

import uvicorn

from app.config import get_settings

PID_FILE = Path(__file__).resolve().parent / "data" / "backend.pid"


def get_listening_pids(target_port: int) -> set[int]:
    pids: set[int] = set()
    if sys.platform != "win32":
        return pids
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    port_pattern = re.compile(rf":{target_port}\s")
    for line in result.stdout.splitlines():
        if "LISTENING" not in line or not port_pattern.search(line):
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return pids


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return str(pid) in result.stdout and "No tasks" not in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def can_bind(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def free_port(target_port: int, except_pid: int | None = None) -> None:
    if sys.platform != "win32":
        return
    my_pid = os.getpid()
    for attempt in range(6):
        pids = get_listening_pids(target_port)
        pids.discard(my_pid)
        if except_pid:
            pids.discard(except_pid)
        if not pids:
            break
        for pid in pids:
            print(f"Port {target_port} in use by PID {pid} — stopping...")
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
        time.sleep(2 if attempt == 0 else 1.5)


def wait_until_port_free(port: int, timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if can_bind(port):
            return True
        time.sleep(0.5)
    return can_bind(port)


def read_stored_pid() -> int | None:
    try:
        if PID_FILE.exists():
            return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        pass
    return None


def write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid_file() -> None:
    try:
        stored = read_stored_pid()
        if stored == os.getpid() and PID_FILE.exists():
            PID_FILE.unlink()
    except OSError:
        pass


def ensure_single_instance(port: int) -> None:
    stored = read_stored_pid()
    if stored and stored != os.getpid() and is_pid_alive(stored):
        if stored in get_listening_pids(port):
            print(f"\nBackend is already running (PID {stored}) on http://127.0.0.1:{port}")
            print("Run stop-backend.bat first if you want to restart.\n")
            sys.exit(0)

    free_port(port)
    if not wait_until_port_free(port):
        print(f"\nERROR: Port {port} is still in use.")
        print("Run stop-backend.bat, close all backend CMD windows, then try again.\n")
        sys.exit(1)


if __name__ == "__main__":
    settings = get_settings()
    port = settings.API_PORT

    ensure_single_instance(port)
    write_pid_file()
    atexit.register(remove_pid_file)

    print(f"Starting backend on http://127.0.0.1:{port}")
    if settings.ADMIN_EMAIL.strip():
        print(f"Admin login email: {settings.ADMIN_EMAIL.strip()}")
    else:
        print("Admin not configured — open http://localhost:5174 to set email and password on first visit")
    print("Connecting database first, then API will be ready...")

    use_reload = os.getenv("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")
    if sys.platform == "win32":
        use_reload = False

    try:
        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=port,
            reload=use_reload,
            log_level="info",
        )
    finally:
        remove_pid_file()
