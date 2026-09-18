"""
FastAPI entrypoint.
- POST /webhook/email          → process an inbound reply
- POST /start                  → initiate outreach to a new prospect
- GET  /thread/{thread_id}     → inspect full history (useful for demos)
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

from app.config import load_config
from app.memory.store import (
    init_db,
    append_message,
    load_thread,
    upsert_thread_meta,
    get_thread_meta,
)
from app.agent.state import Message, AgentState
from app.agent.graph import agent_graph
from app.email.client import email_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialise DB on startup
init_db()
cfg = load_config()


class InboundEmail(BaseModel):
    thread_id: str
    from_email: EmailStr
    subject: str = ""
    body: str


class StartOutreach(BaseModel):
    thread_id: str
    prospect_email: EmailStr
    prospect_name: Optional[str] = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Email Wake-Up Agent started")
    logger.info("Budget ceiling: $%s/hr", cfg["gig"]["budget_ceiling_usd"])
    yield


app = FastAPI(
    title="Email Wake-Up Agent",
    description="Autonomous email agent that negotiates and books calls",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/start")
async def start_outreach(payload: StartOutreach):
    """
    Kick off a new conversation (first outreach email).
    """
    thread_id = payload.thread_id
    meta = get_thread_meta(thread_id)
    if meta["booking_status"] != "NONE" and load_thread(thread_id):
        raise HTTPException(400, "Thread already exists")

    # Seed a system-level context message (never shown to prospect)
    seed = Message(
        role="system",
        content=f"Starting outreach to {payload.prospect_name or payload.prospect_email}",
        meta={"event": "start"},
    )
    append_message(thread_id, seed)
    upsert_thread_meta(thread_id, prospect_email=payload.prospect_email)

    # Build initial state and let the agent write the first email
    state: AgentState = {
        "thread_id": thread_id,
        "messages": load_thread(thread_id),
        "intent": "curious",          # we are initiating
        "quoted_rate": None,
        "budget_ceiling": float(cfg["gig"]["budget_ceiling_usd"]),
        "booking_status": "NONE",
        "proposed_slot": None,
        "confirmed_slot": None,
        "should_walk_away": False,
        "config": {**cfg, "_prospect_email": payload.prospect_email},
        "last_reply": None,
    }

    # Force the reason node to generate an opening message
    # (we skip perceive because there is no inbound yet)
    from app.agent.nodes import reason, act
    state = reason(state)
    state = act(state)

    return {
        "thread_id": thread_id,
        "status": "outreach_sent",
        "reply": state.get("last_reply"),
    }


@app.post("/webhook/email")
async def inbound_email(email: InboundEmail):
    """
    Main entry point for every prospect reply.
    """
    thread_id = email.thread_id

    # 1. Persist inbound
    inbound_msg = Message(
        role="user",
        content=email.body,
        timestamp=datetime.utcnow().isoformat(),
        meta={"from": email.from_email, "subject": email.subject},
    )
    append_message(thread_id, inbound_msg)
    upsert_thread_meta(thread_id, prospect_email=email.from_email)

    # 2. Load full history + current meta
    history = load_thread(thread_id)
    meta = get_thread_meta(thread_id)

    state: AgentState = {
        "thread_id": thread_id,
        "messages": history,
        "intent": None,
        "quoted_rate": meta.get("last_quoted_rate"),
        "budget_ceiling": float(cfg["gig"]["budget_ceiling_usd"]),
        "booking_status": meta.get("booking_status") or "NONE",
        "proposed_slot": meta.get("proposed_slot"),
        "confirmed_slot": meta.get("confirmed_slot"),
        "should_walk_away": meta.get("walk_away", False),
        "config": {**cfg, "_prospect_email": email.from_email},
        "last_reply": None,
    }

    # 3. Run the full graph: perceive → reason → act
    result = agent_graph.invoke(state)

    return {
        "thread_id": thread_id,
        "intent": result.get("intent"),
        "booking_status": result.get("booking_status"),
        "proposed_slot": result.get("proposed_slot"),
        "confirmed_slot": result.get("confirmed_slot"),
        "walk_away": result.get("should_walk_away"),
        "reply": result.get("last_reply"),
    }


@app.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    """Inspect a full conversation (great for demos & debugging)."""
    messages = load_thread(thread_id)
    meta = get_thread_meta(thread_id)
    return {
        "thread_id": thread_id,
        "meta": meta,
        "messages": [m.model_dump() for m in messages],
    }