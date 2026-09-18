import re
from typing import Optional


def extract_rate(text: str) -> Optional[float]:
    """
    Very lightweight rate extractor.
    Looks for patterns like $90/hr, 90 USD/hour, 85 per hour, etc.
    """
    patterns = [
        r"\$?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:/|per)?\s*(?:hr|hour|hourly)",
        r"(\d{2,3}(?:\.\d{1,2})?)\s*(?:USD|usd|dollars?)\s*(?:/|per)?\s*(?:hr|hour)?",
        r"(?:rate|budget|expect|looking for|charge)\s*(?:of|is|around|about)?\s*\$?\s*(\d{2,3})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def is_cancellation(text: str) -> bool:
    keywords = [
        "can't make it", "cannot make it", "won't be able", "have to cancel",
        "need to reschedule", "something came up", "won't work", "can't do",
        "have a conflict", "double booked", "need to move",
    ]
    lower = text.lower()
    return any(k in lower for k in keywords)


def is_acceptance(text: str) -> bool:
    keywords = [
        "sounds good", "that works", "i'm free", "let's do", "confirmed",
        "see you then", "book it", "yes, that time", "perfect", "works for me",
    ]
    lower = text.lower()
    return any(k in lower for k in keywords)