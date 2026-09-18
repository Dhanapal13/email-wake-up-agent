import json
import re
import logging
from datetime import datetime
from typing import Dict, Any

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from app.agent.state import AgentState, Message
from app.memory.store import append_message, upsert_thread_meta
from app.calendar.service import CalendarService
from app.email.parser import extract_rate, is_cancellation, is_acceptance
from app.email.client import email_client
from app.config import load_config

logger = logging.getLogger(__name__)

# Lazy LLM init so the module can be imported even if Ollama is down
_llm = None


def get_llm():
    global _llm
    if _llm is None:
        cfg = load_config()["model"]
        _llm = ChatOllama(
            model=cfg["name"],
            temperature=cfg.get("temperature", 0.4),
        )
    return _llm


def _safe_json_extract(text: str) -> Dict[str, Any]:
    """Extract the first JSON object from LLM output."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


def perceive(state: AgentState) -> AgentState:
    """
    Perception node:
    - Classify intent of the latest user message
    - Extract any quoted hourly rate
    - Detect cancellation / acceptance heuristics
    """
    messages = state["messages"]
    if not messages:
        state["intent"] = "silent"
        return state

    last_user = None
    for m in reversed(messages):
        if m.role == "user":
            last_user = m
            break

    if not last_user:
        state["intent"] = "silent"
        return state

    text = last_user.content

    # Fast path heuristics (cheap & reliable)
    if is_cancellation(text):
        state["intent"] = "reschedule"
        state["booking_status"] = "CANCELLED"
        return state

    if is_acceptance(text) and state.get("booking_status") == "PROPOSED":
        state["intent"] = "booked"
        return state

    rate = extract_rate(text)
    if rate is not None:
        state["quoted_rate"] = rate

    # LLM classification for the harder cases
    history = "\n".join(f"{m.role}: {m.content}" for m in messages[-6:])
    prompt = f"""You are an expert at classifying sales-email intent.
Latest prospect message and recent context:

{history}

Classify the LATEST prospect message into exactly one of these labels:
interested | curious | objecting | declining | silent | reschedule | booked

Also extract any hourly rate they mentioned (number only or null).

Respond with ONLY valid JSON:
{{"intent": "...", "quoted_rate": number_or_null}}
"""
    try:
        resp = get_llm().invoke([HumanMessage(content=prompt)])
        data = _safe_json_extract(resp.content)
        state["intent"] = data.get("intent", "curious")
        if data.get("quoted_rate") is not None:
            state["quoted_rate"] = float(data["quoted_rate"])
    except Exception as e:
        logger.warning("LLM perceive failed, falling back: %s", e)
        state["intent"] = "curious"

    return state


def reason(state: AgentState) -> AgentState:
    """
    Reasoning node:
    - Build full context (history + budget + booking status)
    - Decide whether to walk away, propose, confirm, or re-propose
    - Generate the natural language reply
    """
    cfg = state["config"]
    gig = cfg["gig"]
    budget = state["budget_ceiling"]
    status = state["booking_status"]
    intent = state.get("intent") or "curious"
    quoted = state.get("quoted_rate")

    # Hard budget guard
    if quoted is not None and quoted > budget:
        state["should_walk_away"] = True
        state["booking_status"] = "WALK_AWAY"

    history = "\n".join(f"{m.role.upper()}: {m.content}" for m in state["messages"])

    system = f"""You are {cfg['email']['from_name']} from {gig['company']}.
You are reaching out about a contract opportunity.

GIG:
Title: {gig['title']}
{gig['description']}

HARD RULES (never break these):
- Budget ceiling is ${budget}/hr. NEVER offer or accept more.
- If the prospect's rate is above the ceiling, politely walk away.
- Tone: {gig['tone']}
- Keep full memory of everything said earlier. Never contradict prior commitments.
- Primary goal: get a call booked.
- Be concise (3-6 sentences max). Sound like a sharp human, not a bot.

Current booking status: {status}
Previously confirmed slot: {state.get('confirmed_slot') or 'none'}
Previously proposed slot: {state.get('proposed_slot') or 'none'}
Prospect intent this turn: {intent}
Quoted rate this turn: {quoted or 'none'}
"""

    # Extra guidance based on state
    if state.get("should_walk_away"):
        system += "\nThe prospect is outside budget or clearly declining. Write a short, polite closing message and do not propose any further calls."
    elif status == "CANCELLED" or intent == "reschedule":
        system += "\nThe prospect cancelled a previously agreed slot. Acknowledge it gracefully, keep all prior context, and propose 2-3 new concrete times."
    elif intent in ("interested", "curious") and status in ("NONE", "CANCELLED"):
        system += "\nThe prospect is open. Propose 2-3 specific time slots and ask which works."
    elif intent == "booked" or (intent == "interested" and status == "PROPOSED"):
        system += "\nThe prospect appears to accept a slot. Confirm the booking warmly and give a one-line calendar hold confirmation."
    elif intent == "objecting":
        system += "\nAddress the objection briefly, stay within budget, and gently steer back toward scheduling a short call."
    elif intent == "declining":
        system += "\nRespect the decline. Write a short gracious close."

    messages_for_llm = [
        SystemMessage(content=system),
        HumanMessage(content=f"Full conversation so far:\n\n{history}\n\nWrite the next email reply only (no subject line, no JSON)."),
    ]

    try:
        reply = get_llm().invoke(messages_for_llm).content.strip()
    except Exception as e:
        logger.error("LLM reason failed: %s", e)
        reply = (
            "Thanks for the note — I’m having a brief technical hiccup on my side. "
            "I’ll follow up shortly with clear next steps."
        )

    # Update booking status based on intent + reply content
    if state.get("should_walk_away") or intent == "declining":
        state["booking_status"] = "WALK_AWAY"
    elif intent == "booked" or (is_acceptance(reply) and status == "PROPOSED"):
        # If we were proposing and they accepted, lock it
        slot = state.get("proposed_slot") or CalendarService.propose_next()
        state["confirmed_slot"] = slot
        state["booking_status"] = "CONFIRMED"
        CalendarService.book(slot)
    elif status in ("NONE", "CANCELLED") and intent in ("interested", "curious", "reschedule"):
        new_slot = CalendarService.propose_next(exclude=state.get("confirmed_slot"))
        state["proposed_slot"] = new_slot
        state["booking_status"] = "PROPOSED"
        # Inject the concrete slot into the reply if the LLM forgot
        if new_slot not in reply:
            reply += f"\n\nWould any of these work for a quick 30-min call?\n- {new_slot}\n- {CalendarService.propose_next()}\n- {CalendarService.propose_next()}"

    # Record the assistant message
    assistant_msg = Message(
        role="assistant",
        content=reply,
        timestamp=datetime.utcnow().isoformat(),
        meta={
            "intent_seen": intent,
            "booking_status": state["booking_status"],
            "proposed_slot": state.get("proposed_slot"),
            "confirmed_slot": state.get("confirmed_slot"),
        },
    )
    state["messages"].append(assistant_msg)
    state["last_reply"] = reply
    return state


def act(state: AgentState) -> AgentState:
    """
    Action node:
    - Persist the outbound message
    - Update thread metadata
    - Send the email (mock or real)
    """
    thread_id = state["thread_id"]
    last = state["messages"][-1]

    # Persist
    append_message(thread_id, last)
    upsert_thread_meta(
        thread_id,
        booking_status=state["booking_status"],
        confirmed_slot=state.get("confirmed_slot"),
        proposed_slot=state.get("proposed_slot"),
        last_quoted_rate=state.get("quoted_rate"),
        walk_away=state.get("should_walk_away", False),
    )

    # Send (prospect email should be known; for demo we use a placeholder)
    # In real usage the webhook payload carries from_email
    to_email = state.get("config", {}).get("_prospect_email", "prospect@example.com")
    subject = f"Re: {state['config']['gig']['title']}"
    # Fire-and-forget in the async endpoint; here we just call the sync-compatible path
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule it
            asyncio.create_task(email_client.send(to_email, subject, last.content, thread_id=thread_id))
        else:
            loop.run_until_complete(email_client.send(to_email, subject, last.content, thread_id=thread_id))
    except Exception:
        # Fallback – just print
        print(f"[ACT] Would send to {to_email}:\n{last.content}\n")

    return state