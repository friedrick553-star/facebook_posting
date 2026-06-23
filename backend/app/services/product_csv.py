"""Parse product CSV uploads for Facebook Marketplace posting."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

DAY_ALIASES = {
    "mon": "mon", "monday": "mon", "lun": "mon", "lunedì": "mon", "lunedì": "mon",
    "tue": "tue", "tuesday": "tue", "mar": "tue", "martedì": "tue", "martedi": "tue",
    "wed": "wed", "wednesday": "wed", "mer": "wed", "mercoledì": "wed", "mercoledi": "wed",
    "thu": "thu", "thursday": "thu", "gio": "thu", "giovedì": "thu", "giovedi": "thu",
    "fri": "fri", "friday": "fri", "ven": "fri", "venerdì": "fri", "venerdi": "fri",
    "sat": "sat", "saturday": "sat", "sab": "sat", "sabato": "sat",
    "sun": "sun", "sunday": "sun", "dom": "sun", "domenica": "sun",
}

CONDITION_ALIASES = {
    "new": "new", "nuovo": "new", "nuova": "new", "nuevo": "new",
    "used": "used", "usato": "used", "usata": "used", "usado": "used",
    "like_new": "new", "like new": "new", "come nuovo": "new",
}

AVAILABILITY_ALIASES = {
    "single": "single", "one": "single", "1": "single",
    "single item": "single", "list as single": "single", "list as a single item": "single",
    "articolo singolo": "single", "singolo": "single",
    "stock": "stock", "in stock": "stock", "in_stock": "stock", "disponibile": "stock",
}

HEADER_MAP = {
    "name": "name", "nome": "name", "title": "name", "titolo": "name", "product": "name",
    "description": "description", "descrizione": "description", "desc": "description",
    "price": "price", "prezzo": "price", "cost": "price",
    "currency": "currency", "valuta": "currency",
    "images": "images", "image": "images", "immagini": "images", "immagine": "images", "photos": "images",
    "schedule_day": "schedule_day", "day": "schedule_day", "giorno": "schedule_day", "weekday": "schedule_day",
    "schedule_time": "schedule_time", "time": "schedule_time", "ora": "schedule_time", "hour": "schedule_time",
    "category": "category", "categoria": "category", "cat": "category",
    "condition": "condition", "condizione": "condition", "cond": "condition",
    "availability": "availability", "disponibilita": "availability", "disponibilità": "availability", "stock_type": "availability",
    "details": "details", "more_details": "details", "extra_details": "details", "dettagli": "details",
    "brand": "brand", "marca": "brand",
}

REQUIRED_COLUMNS = (
    "name",
    "description",
    "price",
    "images",
    "category",
    "condition",
    "availability",
    "schedule_day",
    "schedule_time",
)

OPTIONAL_COLUMNS = ("details", "currency", "brand", "color")


@dataclass
class ParsedProductRow:
    name: str
    description: str
    price: float | None
    currency: str
    images: list[str]
    schedule_day: str | None
    schedule_time: str | None
    category: str | None = None
    condition: str = "new"
    availability: str = "single"
    extra_details: dict[str, str] = field(default_factory=dict)
    row_number: int = 0


@dataclass
class CsvRowIssue:
    row_number: int
    name: str
    missing_fields: list[str]


@dataclass
class CsvParseResult:
    valid_rows: list[ParsedProductRow]
    incomplete_rows: list[tuple[ParsedProductRow, list[str]]]
    errors: list[str]


def _normalize_header(h: str) -> str:
    key = h.strip().lower().replace(" ", "_")
    return HEADER_MAP.get(key, key)


def _parse_price(value: str) -> float | None:
    if not value or not str(value).strip():
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(value).strip())
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_images(value: str) -> list[str]:
    if not value or not str(value).strip():
        return []
    raw = str(value).strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        if "|" in raw:
            return [p.strip() for p in raw.split("|") if p.strip()]
        if ";" in raw:
            return [p.strip() for p in raw.split(";") if p.strip()]
        return [raw]
    parts = re.split(r"[|;]", raw)
    return [p.strip() for p in parts if p.strip()]


def _parse_day(value: str) -> str | None:
    if not value or not str(value).strip():
        return None
    key = str(value).strip().lower()
    return DAY_ALIASES.get(key, key[:3] if len(key) >= 3 else None)


def _parse_time(value: str) -> str | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip().replace(".", ":")
    m = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def _parse_condition(value: str) -> str:
    key = (value or "").strip().lower()
    if not key:
        return ""
    return CONDITION_ALIASES.get(key, "new" if key not in ("used", "usato") else "used")


def _parse_availability(value: str) -> str:
    key = (value or "").strip().lower()
    if not key:
        return ""
    return AVAILABILITY_ALIASES.get(key, "single")


def _parse_details(value: str) -> dict[str, str]:
    if not value or not str(value).strip():
        return {}
    raw = str(value).strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None and str(v).strip()}
        except json.JSONDecodeError:
            pass
    details: dict[str, str] = {}
    for part in re.split(r"[|;]", raw):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, _, v = part.partition("=")
        elif ":" in part:
            k, _, v = part.partition(":")
        else:
            continue
        k, v = k.strip(), v.strip()
        if k and v:
            details[k] = v
    return details


def _missing_fields_from_cells(cells: dict[str, str]) -> list[str]:
    missing: list[str] = []
    if not cells.get("name", "").strip():
        missing.append("name")
    if not cells.get("description", "").strip():
        missing.append("description")
    if _parse_price(cells.get("price", "")) is None:
        missing.append("price")
    if not _parse_images(cells.get("images", "")):
        missing.append("images")
    if not cells.get("category", "").strip():
        missing.append("category")
    if not cells.get("condition", "").strip():
        missing.append("condition")
    if not cells.get("availability", "").strip():
        missing.append("availability")
    if not _parse_day(cells.get("schedule_day", "")):
        missing.append("schedule_day")
    if not _parse_time(cells.get("schedule_time", "")):
        missing.append("schedule_time")
    return missing


def parse_products_csv(content: bytes, *, encoding: str = "utf-8-sig") -> CsvParseResult:
    errors: list[str] = []
    valid_rows: list[ParsedProductRow] = []
    incomplete_rows: list[tuple[ParsedProductRow, list[str]]] = []

    text = content.decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return CsvParseResult([], [], ["CSV file is empty or has no header row"])

    col_map = {_normalize_header(h): h for h in reader.fieldnames if h}
    missing_headers = [col for col in REQUIRED_COLUMNS if col not in col_map]
    if missing_headers:
        return CsvParseResult(
            [],
            [],
            [f"CSV missing required columns: {', '.join(missing_headers)}"],
        )

    for i, raw in enumerate(reader, start=2):
        def cell(field: str) -> str:
            src = col_map.get(field)
            return (raw.get(src) or "").strip() if src else ""

        raw_cells = {field: cell(field) for field in REQUIRED_COLUMNS}
        for opt in OPTIONAL_COLUMNS:
            raw_cells[opt] = cell(opt)

        if not raw_cells["name"]:
            errors.append(f"Row {i}: empty name — skipped")
            continue

        missing = _missing_fields_from_cells(raw_cells)
        description = raw_cells["description"]
        price = _parse_price(raw_cells["price"])
        currency = (raw_cells.get("currency") or "EUR").upper()[:10]
        images = _parse_images(raw_cells["images"])
        schedule_day = _parse_day(raw_cells["schedule_day"])
        schedule_time = _parse_time(raw_cells["schedule_time"])
        category = raw_cells["category"] or None
        condition = _parse_condition(raw_cells["condition"]) or "new"
        availability = _parse_availability(raw_cells["availability"]) or "single"
        extra_details = _parse_details(raw_cells.get("details", ""))
        brand = raw_cells.get("brand", "")
        if brand:
            extra_details.setdefault("Brand", brand)
        color = raw_cells.get("color", "")
        if color:
            extra_details.setdefault("Color", color)

        row = ParsedProductRow(
            name=raw_cells["name"],
            description=description,
            price=price,
            currency=currency,
            images=images,
            schedule_day=schedule_day,
            schedule_time=schedule_time,
            category=category,
            condition=condition,
            availability=availability,
            extra_details=extra_details,
            row_number=i,
        )

        if missing:
            incomplete_rows.append((row, missing))
        else:
            valid_rows.append(row)

    if not valid_rows and not incomplete_rows and not errors:
        errors.append("No product rows found in CSV")
    return CsvParseResult(valid_rows, incomplete_rows, errors)
