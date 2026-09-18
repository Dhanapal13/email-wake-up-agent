from typing import List, Optional
from app.config import load_config


class CalendarService:
    """
    Simple stub calendar.
    In production replace with Google Calendar / Cal.com SDK.
    The interface stays identical so the agent does not change.
    """

    _idx: int = 0

    @classmethod
    def _slots(cls) -> List[str]:
        return load_config()["calendar"]["available_slots"]

    @classmethod
    def propose_next(cls, exclude: Optional[str] = None) -> str:
        slots = cls._slots()
        for _ in range(len(slots)):
            slot = slots[cls._idx % len(slots)]
            cls._idx += 1
            if slot != exclude:
                return slot
        return slots[0]

    @classmethod
    def propose_several(cls, n: int = 3) -> List[str]:
        return [cls.propose_next() for _ in range(n)]

    @classmethod
    def book(cls, slot: str) -> bool:
        # Stub always succeeds. Real implementation would create the event.
        return True

    @classmethod
    def cancel(cls, slot: str) -> bool:
        return True