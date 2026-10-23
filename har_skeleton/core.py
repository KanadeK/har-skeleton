"""Rebuild HAR from a small allowlist. Never mutate or copy arbitrary input objects."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__

MAX_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_ALLOWED_BYTES = 512 * 1024 * 1024
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
METHODS = frozenset(
    {"GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}
)
VERSIONS = frozenset({"HTTP/1.0", "HTTP/1.1", "HTTP/2", "HTTP/2.0", "HTTP/3", "h2", "h3"})
MIMES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
        "application/xml",
        "text/xml",
        "application/octet-stream",
        "application/pdf",
        "application/wasm",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "image/avif",
        "font/woff",
        "font/woff2",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
        "audio/mpeg",
        "video/mp4",
    }
)


class HarError(ValueError):
    """Invalid or unsupported input. Messages must not include raw capture text."""


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise HarError(f"{label} must be an object")
    return value


def _number(
    value: object, label: str, *, minimum: float = -1, integer: bool = False
) -> int | float:
    if type(value) not in (int, float):
        raise HarError(f"{label} must be a finite number")
    if (
        not minimum <= value <= 10**15
        or not math.isfinite(value)
        or (integer and int(value) != value)
    ):
        raise HarError(f"{label} is outside the supported numeric range")
    return int(value) if integer else value


def _date(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise HarError("startedDateTime must be an ISO 8601 timestamp with a timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise HarError("startedDateTime must be an ISO 8601 timestamp with a timezone") from exc


def _phase(timings: dict, key: str) -> int | float:
    required = key in {"send", "wait", "receive"}
    value = _number(
        timings.get(key, None if required else -1), f"timings.{key}", minimum=0 if required else -1
    )
    if value < 0 and value != -1:
        raise HarError("unknown timing phases must use -1")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise HarError("duplicate JSON object keys are not supported")
        result[key] = value
    return result


def load_har(path: str | Path, *, max_bytes: int = MAX_BYTES) -> dict:
    """Bound the bytes read, reject duplicate keys, NaN, and excessively nested input."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ALLOWED_BYTES:
        raise HarError("max_bytes must be between 1 and 536870912")
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HarError("input exceeds max_bytes")
        document = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(HarError("non-finite JSON number")),
        )
        return _object(document, "document")
    except HarError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise HarError("input must be valid UTF-8 JSON within the nesting limit") from exc


def build_skeleton(document: dict, *, max_entries: int = MAX_ENTRIES) -> tuple[dict, dict]:
    """Return a newly built HAR and counts. Raw URLs and alias mappings are never returned."""
    if type(max_entries) is not int or not 1 <= max_entries <= 1_000_000:
        raise HarError("max_entries must be between 1 and 1000000")
    log = _object(_object(document, "document").get("log"), "log")
    entries, pages = log.get("entries"), log.get("pages", [])
    if not isinstance(entries, list) or not isinstance(pages, list):
        raise HarError("log.entries and log.pages must be arrays")
    if len(entries) > max_entries or len(pages) > max_entries:
        raise HarError("capture exceeds max_entries")
    dates = [_date(_object(entry, "entry").get("startedDateTime")) for entry in entries]
    page_dates = [_date(_object(page, "page").get("startedDateTime")) for page in pages]
    base = min(dates + page_dates, default=EPOCH)

    def shifted(date: datetime) -> str:
        offset = date - base
        if offset > timedelta(days=366):
            raise HarError("capture spans more than 366 days")
        return (EPOCH + offset).isoformat(timespec="microseconds").replace("+00:00", "Z")

    page_ids: dict[str, str] = {}
    clean_pages = []
    for index, (page, date) in enumerate(zip(pages, page_dates, strict=True), 1):
        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id or page_id in page_ids:
            raise HarError("pages must have unique nonempty string IDs")
        alias = f"page-{index}"
        page_ids[page_id] = alias
        timings = _object(page.get("pageTimings", {}), "pageTimings")
        clean_pages.append(
            {
                "id": alias,
                "startedDateTime": shifted(date),
                "title": f"Page {index}",
                "pageTimings": {
                    key: _phase(timings, key)
                    for key in ("onContentLoad", "onLoad")
                    if key in timings
                },
            }
        )

    origins: dict[tuple, int] = {}
    endpoints: dict[tuple, int] = {}
    clean_entries = []
    for entry, date in zip(entries, dates, strict=True):
        request = _object(entry.get("request"), "request")
        response = _object(entry.get("response"), "response")
        timings = _object(entry.get("timings"), "timings")
        raw_url = request.get("url")
        if not isinstance(raw_url, str) or len(raw_url) > 65_536:
            raise HarError("request.url must be a supported absolute URL")
        try:
            url = urlsplit(raw_url)
            if url.scheme not in {"http", "https", "ws", "wss"} or not url.hostname:
                raise ValueError
            origin = (
                url.scheme,
                url.hostname.lower(),
                url.port
                if url.port is not None
                else (443 if url.scheme in {"https", "wss"} else 80),
            )
        except ValueError as exc:
            raise HarError("request.url must be a supported absolute URL") from exc
        host_id = origins.setdefault(origin, len(origins) + 1)
        path_id = endpoints.setdefault((host_id, url.path or "/"), len(endpoints) + 1)
        safe_url = f"{url.scheme}://host-{host_id}.invalid/resource-{path_id}"
        content = _object(response.get("content", {}), "content")
        raw_mime = content.get("mimeType", "")
        mime = raw_mime.split(";", 1)[0].strip().lower() if isinstance(raw_mime, str) else ""
        status = _number(response.get("status"), "response.status", minimum=0, integer=True)
        if status > 999:
            raise HarError("response.status must be between 0 and 999")
        method = request.get("method")
        http_request, http_response = request.get("httpVersion"), response.get("httpVersion")
        clean = {
            "startedDateTime": shifted(date),
            "time": _number(entry.get("time"), "entry.time", minimum=0),
            "request": {
                "method": method if isinstance(method, str) and method in METHODS else "OTHER",
                "url": safe_url,
                "httpVersion": http_request
                if isinstance(http_request, str) and http_request in VERSIONS
                else "",
                "headers": [],
                "cookies": [],
                "queryString": [],
                "headersSize": _number(
                    request.get("headersSize", -1), "request.headersSize", integer=True
                ),
                "bodySize": _number(request.get("bodySize", -1), "request.bodySize", integer=True),
            },
            "response": {
                "status": status,
                "statusText": "",
                "httpVersion": http_response
                if isinstance(http_response, str) and http_response in VERSIONS
                else "",
                "headers": [],
                "cookies": [],
                "content": {
                    "size": _number(content.get("size"), "content.size", minimum=0, integer=True),
                    "mimeType": mime if mime in MIMES else "application/octet-stream",
                },
                "redirectURL": "",
                "headersSize": _number(
                    response.get("headersSize", -1), "response.headersSize", integer=True
                ),
                "bodySize": _number(
                    response.get("bodySize", -1), "response.bodySize", integer=True
                ),
            },
            "cache": {},
            "timings": {
                key: _phase(timings, key)
                for key in ("blocked", "dns", "connect", "send", "wait", "receive", "ssl")
            },
        }
        if "pageref" in entry:
            reference = entry["pageref"]
            if not isinstance(reference, str) or reference not in page_ids:
                raise HarError("entry.pageref must reference a declared page")
            clean["pageref"] = page_ids[reference]
        clean_entries.append(clean)

    result = {
        "log": {
            "version": "1.2",
            "creator": {"name": "har-skeleton", "version": __version__},
            "pages": clean_pages,
            "entries": clean_entries,
        }
    }
    return result, {
        "entries": len(entries),
        "pages": len(pages),
        "origins": len(origins),
        "endpoints": len(endpoints),
    }


def write_new(path: str | Path, document: dict) -> None:
    """Exclusive creation: never overwrite an existing capture or follow an output symlink."""
    encoded = (json.dumps(document, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode(
        "utf-8"
    )
    with Path(path).open("xb") as stream:
        stream.write(encoded)
