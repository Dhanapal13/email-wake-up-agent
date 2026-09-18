"""
Optional tools the LLM can call.
Kept minimal – most logic lives in the nodes for clarity and control.
"""

from langchain_core.tools import tool
from app.calendar.service import CalendarService


@tool
def propose_meeting_slots(n: int = 3) -> str:
    """Propose n available meeting slots to the prospect."""
    slots = CalendarService.propose_several(n)
    return "Available slots:\n" + "\n".join(f"- {s}" for s in slots)


@tool
def book_slot(slot: str) -> str:
    """Book a specific calendar slot after the prospect confirms."""
    ok = CalendarService.book(slot)
    return f"Slot '{slot}' booked successfully." if ok else f"Could not book '{slot}'."