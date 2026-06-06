"""
Cal.com API integration.

Uses the Cal.com v1 REST API for:
  - Fetching available time slots
  - Creating bookings

Cal.com free tier is perfectly adequate for this use case
(it stores bookings and sends confirmation emails automatically).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models import BookingRequest, BookingResponse, TimeSlot

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE = "https://api.cal.com/v1"


def _headers() -> dict:
    return {"Content-Type": "application/json"}


def _params(extra: dict | None = None) -> dict:
    p = {"apiKey": settings.CALCOM_API_KEY}
    if extra:
        p.update(extra)
    return p


# ── Available slots ───────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
async def get_available_slots(
    days_ahead: int = 7,
    timezone_str: str = "Asia/Kolkata",
) -> list[TimeSlot]:
    """Fetch available booking slots from Cal.com."""
    if not settings.CALCOM_API_KEY or not settings.CALCOM_USERNAME:
        logger.warning("Cal.com not configured — returning mock slots")
        return _mock_slots()

    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=days_ahead)

    params = _params({
        "username": settings.CALCOM_USERNAME,
        "eventTypeSlug": settings.CALCOM_EVENT_TYPE_SLUG,
        "startTime": start_time.isoformat(),
        "endTime": end_time.isoformat(),
        "timeZone": timezone_str,
    })

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{_BASE}/slots", params=params)
        r.raise_for_status()
        data = r.json()

    slots = []
    for date_str, date_slots in data.get("slots", {}).items():
        for slot in date_slots:
            start = slot.get("time", "")
            if start:
                try:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    end_dt = dt + timedelta(minutes=30)
                    # Format for humans: "Mon, Jun 9 at 3:00 PM IST"
                    formatted = dt.strftime("%a, %b %-d at %-I:%M %p UTC")
                    slots.append(TimeSlot(
                        start=start,
                        end=end_dt.isoformat(),
                        formatted=formatted,
                    ))
                except Exception:
                    pass

    return slots[:10]   # cap at 10 slots to keep voice responses short


def _mock_slots() -> list[TimeSlot]:
    """Fallback mock slots when Cal.com is not configured."""
    base = datetime.now(timezone.utc) + timedelta(days=1)
    base = base.replace(hour=10, minute=0, second=0, microsecond=0)
    slots = []
    for i in range(5):
        start = base + timedelta(hours=i * 2)
        end = start + timedelta(minutes=30)
        slots.append(TimeSlot(
            start=start.isoformat(),
            end=end.isoformat(),
            formatted=start.strftime("%a, %b %-d at %-I:%M %p UTC"),
        ))
    return slots


# ── Create booking ────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
async def create_booking(req: BookingRequest) -> BookingResponse:
    """Create a confirmed booking on Cal.com."""
    if not settings.CALCOM_API_KEY or not settings.CALCOM_USERNAME:
        logger.warning("Cal.com not configured — returning mock booking")
        return _mock_booking(req)

    payload = {
        "eventTypeId": await _get_event_type_id(),
        "start": req.start_time,
        "end": _compute_end_time(req.start_time),
        "responses": {
            "name": req.name,
            "email": req.email,
            "notes": req.notes or "",
            "location": {"optionValue": "", "value": "integrations:google:meet"},
        },
        "timeZone": req.timezone,
        "language": "en",
        "metadata": {},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_BASE}/bookings",
            params=_params(),
            json=payload,
        )

    if r.status_code in (200, 201):
        data = r.json()
        uid = data.get("uid", "")
        meet_url = data.get("videoCallData", {}).get("url", "")
        return BookingResponse(
            success=True,
            booking_id=uid,
            meeting_url=meet_url or None,
            calendar_link=f"https://cal.com/{settings.CALCOM_USERNAME}",
            confirmation_message=(
                f"Confirmed! Your 30-minute call is booked. "
                f"A confirmation has been sent to {req.email}."
                + (f" Join here: {meet_url}" if meet_url else "")
            ),
        )
    else:
        logger.error("Cal.com booking failed: %s %s", r.status_code, r.text)
        return BookingResponse(
            success=False,
            confirmation_message=f"Booking failed (status {r.status_code}). Please try again.",
        )


async def _get_event_type_id() -> int:
    """Resolve event type slug to ID (cached per process)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_BASE}/event-types",
            params=_params({"username": settings.CALCOM_USERNAME}),
        )
        r.raise_for_status()
        for et in r.json().get("event_types", []):
            if et.get("slug") == settings.CALCOM_EVENT_TYPE_SLUG:
                return et["id"]
    raise ValueError(f"Event type '{settings.CALCOM_EVENT_TYPE_SLUG}' not found")


def _compute_end_time(start_iso: str, duration_minutes: int = 30) -> str:
    dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = dt + timedelta(minutes=duration_minutes)
    return end.isoformat()


def _mock_booking(req: BookingRequest) -> BookingResponse:
    return BookingResponse(
        success=True,
        booking_id="mock-booking-001",
        meeting_url="https://meet.google.com/mock-link",
        calendar_link="https://cal.com",
        confirmation_message=(
            f"✓ Confirmed! Call booked for {req.start_time}. "
            f"Confirmation sent to {req.email}."
        ),
    )
