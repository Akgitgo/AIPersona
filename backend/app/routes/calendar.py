from fastapi import APIRouter
from app.models import BookingRequest, SlotRequest
from app.integrations import calcom

router = APIRouter()


@router.post("/slots")
async def available_slots(req: SlotRequest):
    slots = await calcom.get_available_slots(
        days_ahead=req.days_ahead,
        timezone_str=req.timezone,
    )
    return {"slots": [s.model_dump() for s in slots], "timezone": req.timezone}


@router.post("/book")
async def book_meeting(req: BookingRequest):
    result = await calcom.create_booking(req)
    return result.model_dump()
