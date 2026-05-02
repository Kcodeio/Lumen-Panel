"""
Temporary setup wizard.

Runs as a separate process during install. Collects admin credentials and
network config from a one-page form, writes them to the panel's database,
then drops a marker file at $LUMEN_DATA_DIR/.setup-complete which tells the
installer to stop the wizard and proceed.
"""
from __future__ import annotations

import json
import os
import secrets
import string
import sys
import uuid as uuid_lib
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from pydantic import EmailStr, ValidationError, validate_email
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
INSTALL_DIR = Path(os.environ.get("LUMEN_INSTALL_DIR", "/opt/lumen"))
CONFIG_DIR = Path(os.environ.get("LUMEN_CONFIG_DIR", "/etc/lumen"))
DATA_DIR = Path(os.environ.get("LUMEN_DATA_DIR", "/var/lib/lumen"))
SETUP_PORT = int(os.environ.get("LUMEN_PORT_SETUP", "8080"))
DEFAULT_DOMAIN = os.environ.get("LUMEN_DEFAULT_DOMAIN", "127.0.0.1")
VERSION = "1.0.0"

DB_PATH = DATA_DIR / "db" / "panel.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DB_PATH}"

# ---------------------------------------------------------------------------
# Local ORM (mirror of the real backend's User table so we can write to the
# same SQLite file). Schema must match backend.app.models.user.User.
# ---------------------------------------------------------------------------
Base = declarative_base()


class User(Base):  # type: ignore[misc]
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(dt_timezone.utc),
        nullable=False,
    )


engine = create_engine(DB_URL, connect_args={"check_same_thread": False}, future=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Lumen Setup Wizard", version=VERSION)


# Subset of common timezones; users can change later in the panel
COMMON_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Istanbul",
    "Africa/Cairo",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        # Make sure it has a digit and a letter
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def _write_admin_credentials(email: str, password: str) -> None:
    admin_file = CONFIG_DIR / "admin.txt"
    admin_file.parent.mkdir(parents=True, exist_ok=True)
    admin_file.write_text(
        f"# Generated {datetime.now(dt_timezone.utc).isoformat()}\n"
        f"email={email}\n"
        f"password={password}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(admin_file, 0o600)
    except PermissionError:
        pass


def _write_setup_summary(payload: dict) -> None:
    summary_file = DATA_DIR / "setup-summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(summary_file, 0o600)
    except PermissionError:
        pass


def _mark_complete() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / ".setup-complete").write_text("done\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def get_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "version": VERSION,
            "year": datetime.now().year,
            "completed": False,
            "error": None,
            "form": {},
            "default_domain": DEFAULT_DOMAIN,
            "timezones": COMMON_TIMEZONES,
            "domain": DEFAULT_DOMAIN,
            "generated_password": None,
        },
    )


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(""),
    password_confirm: str = Form(""),
    domain: str = Form(...),
    port_start: int = Form(25565),
    port_end: int = Form(25600),
    timezone: str = Form("UTC"),
    create_default_mc: str = Form(""),
    enable_telemetry: str = Form(""),
) -> HTMLResponse:
    form_state = {
        "email": email,
        "domain": domain,
        "port_start": port_start,
        "port_end": port_end,
        "timezone": timezone,
        "create_default_mc": bool(create_default_mc),
        "enable_telemetry": bool(enable_telemetry),
    }

    error: str | None = None

    # Validate email
    try:
        validate_email(email)
    except (ValidationError, Exception):
        error = "Invalid email address."

    # Validate ports
    if not error and not (1024 <= port_start < port_end <= 65535):
        error = "Port range must satisfy 1024 ≤ start < end ≤ 65535."

    # Validate timezone (basic - accept anything from our list or any plausible tz)
    if not error and timezone not in COMMON_TIMEZONES and "/" not in timezone:
        error = "Unknown timezone."

    # Password handling
    generated = False
    if not error:
        if password == "" and password_confirm == "":
            password = _generate_password()
            generated = True
        else:
            if len(password) < 8:
                error = "Password must be at least 8 characters."
            elif password != password_confirm:
                error = "Passwords do not match."

    if error:
        return templates.TemplateResponse(
            "setup.html",
            {
                "request": request,
                "version": VERSION,
                "year": datetime.now().year,
                "completed": False,
                "error": error,
                "form": form_state,
                "default_domain": DEFAULT_DOMAIN,
                "timezones": COMMON_TIMEZONES,
                "domain": domain or DEFAULT_DOMAIN,
                "generated_password": None,
            },
            status_code=400,
        )

    # Persist admin user
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.password_hash = pwd.hash(password)
            existing.is_admin = True
            existing.is_active = True
        else:
            db.add(
                User(
                    email=email,
                    password_hash=pwd.hash(password),
                    is_admin=True,
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()

    # Append optional knobs to panel.env without overwriting existing keys
    panel_env_path = CONFIG_DIR / "panel.env"
    extra_lines = [
        f"LUMEN_PUBLIC_DOMAIN={domain}",
        f"LUMEN_TIMEZONE={timezone}",
        f"LUMEN_TELEMETRY={'1' if form_state['enable_telemetry'] else '0'}",
        f"LUMEN_GAME_PORT_START={port_start}",
        f"LUMEN_GAME_PORT_END={port_end}",
    ]
    if panel_env_path.exists():
        existing_text = panel_env_path.read_text(encoding="utf-8")
        # Replace any keys we're managing here, append new ones
        kept_lines = []
        managed_keys = {line.split("=", 1)[0] for line in extra_lines}
        for line in existing_text.splitlines():
            if line.split("=", 1)[0] in managed_keys:
                continue
            kept_lines.append(line)
        kept_lines.extend(extra_lines)
        panel_env_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")

    # Write side-files
    _write_admin_credentials(email, password)
    _write_setup_summary(
        {
            "email": email,
            "domain": domain,
            "port_start": port_start,
            "port_end": port_end,
            "timezone": timezone,
            "create_default_mc": form_state["create_default_mc"],
            "enable_telemetry": form_state["enable_telemetry"],
            "completed_at": datetime.now(dt_timezone.utc).isoformat(),
            "setup_id": str(uuid_lib.uuid4()),
        }
    )

    # Default Minecraft marker
    if form_state["create_default_mc"]:
        (DATA_DIR / ".create-default-mc").write_text("1\n", encoding="utf-8")

    # Mark complete (the installer polls for this file)
    _mark_complete()

    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "version": VERSION,
            "year": datetime.now().year,
            "completed": True,
            "error": None,
            "form": form_state,
            "default_domain": DEFAULT_DOMAIN,
            "timezones": COMMON_TIMEZONES,
            "domain": domain,
            "generated_password": password if generated else None,
        },
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SETUP_PORT,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
