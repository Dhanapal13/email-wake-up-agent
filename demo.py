#!/usr/bin/env python3
"""
Generate the three required sample transcripts:

1. Successful negotiation + booking
2. Cancellation + re-booking (reschedule loop)
3. Graceful walk-away (rate too high)

Run from project root:
    python -m scripts.demo_transcripts
"""

import json
import sys
from pathlib import Path

# Make sure the app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from app.memory.store import init_db, append_message, load_thread, upsert_thread_meta
from app.agent.state import Message
from app.agent.nodes import perceive, reason, act
from app.config import load_config

init_db()
cfg = load_config()


def run_turn(thread_id: str, user_text: str, prospect_email: str = "prospect@example.com"):
    """Simulate one full turn (inbound → graph → outbound)."""
    # Persist inbound
    append_message(
        thread_id,
        Message(role="user", content=user_text, meta={"from": prospect_email}),
    )
    upsert_thread_meta(thread_id, prospect_email=prospect_email)

    history = load_thread(thread_id)
    from app.memory.store import get_thread_meta
    meta = get_thread_meta(thread_id)

    state = {
        "thread_id": thread_id,
        "messages": history,
        "intent": None,
        "quoted_rate": meta.get("last_quoted_rate"),
        "budget_ceiling": float(cfg["gig"]["budget_ceiling_usd"]),
        "booking_status": meta.get("booking_status") or "NONE",
        "proposed_slot": meta.get("proposed_slot"),
        "confirmed_slot": meta.get("confirmed_slot"),
        "should_walk_away": meta.get("walk_away", False),
        "config": {**cfg, "_prospect_email": prospect_email},
        "last_reply": None,
    }

    state = perceive(state)
    state = reason(state)
    state = act(state)
    return state


def print_transcript(title: str, thread_id: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    for m in load_thread(thread_id):
        if m.role == "system":
            continue
        role = "PROSPECT" if m.role == "user" else "AGENT"
        print(f"\n[{role}]")
        print(m.content)
    print()


def scenario_success():
    tid = "demo-success-001"
    # Opening (simulate /start)
    append_message(tid, Message(role="system", content="Outreach started"))
    state = {
        "thread_id": tid,
        "messages": load_thread(tid),
        "intent": "curious",
        "quoted_rate": None,
        "budget_ceiling": 85.0,
        "booking_status": "NONE",
        "proposed_slot": None,
        "confirmed_slot": None,
        "should_walk_away": False,
        "config": {**cfg, "_prospect_email": "jane@example.com"},
        "last_reply": None,
    }
    state = reason(state)
    state = act(state)

    # Prospect shows interest
    run_turn(tid, "Hi Alex, thanks for reaching out. The role sounds interesting. What’s the rate range?")
    # Prospect accepts a reasonable rate + time
    run_turn(tid, "I usually work around $80/hr. The Tuesday 10am slot works perfectly for me.")
    print_transcript("1. SUCCESSFUL NEGOTIATION + BOOKING", tid)


def scenario_reschedule():
    tid = "demo-reschedule-001"
    append_message(tid, Message(role="system", content="Outreach started"))
    state = {
        "thread_id": tid,
        "messages": load_thread(tid),
        "intent": "curious",
        "quoted_rate": None,
        "budget_ceiling": 85.0,
        "booking_status": "NONE",
        "proposed_slot": None,
        "confirmed_slot": None,
        "should_walk_away": False,
        "config": {**cfg, "_prospect_email": "sam@example.com"},
        "last_reply": None,
    }
    state = reason(state)
    state = act(state)

    run_turn(tid, "This looks like a great fit. I’m available most afternoons next week.")
    run_turn(tid, "Thursday 15:00 UTC works – let’s lock it in.")
    # Cancellation
    run_turn(tid, "Hey, something came up and I can’t make the Thursday slot anymore. Really sorry.")
    # Re-book
    run_turn(tid, "The Friday morning option is perfect. See you then!")
    print_transcript("2. CANCELLATION + RE-BOOKING (reschedule loop)", tid)


def scenario_walkaway():
    tid = "demo-walkaway-001"
    append_message(tid, Message(role="system", content="Outreach started"))
    state = {
        "thread_id": tid,
        "messages": load_thread(tid),
        "intent": "curious",
        "quoted_rate": None,
        "budget_ceiling": 85.0,
        "booking_status": "NONE",
        "proposed_slot": None,
        "confirmed_slot": None,
        "should_walk_away": False,
        "config": {**cfg, "_prospect_email": "highrate@example.com"},
        "last_reply": None,
    }
    state = reason(state)
    state = act(state)

    run_turn(tid, "Thanks for the note. I’m interested but my rate is $120/hr.")
    run_turn(tid, "I can’t go below $110 unfortunately.")
    print_transcript("3. GRACEFUL WALK-AWAY (over budget)", tid)


if __name__ == "__main__":
    print("Generating the three required sample transcripts...\n")
    scenario_success()
    scenario_reschedule()
    scenario_walkaway()
    print("\nDone. Full histories are also stored in data/threads.db")