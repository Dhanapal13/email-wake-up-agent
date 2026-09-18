from typing import Annotated, List, Optional, Literal, Dict, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from datetime import datetime


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    meta: Dict[str, Any] = Field(default_factory=dict)


class AgentState(TypedDict):
    thread_id: str
    messages: Annotated[List[Message], add_messages]
    intent: Optional[str]
    quoted_rate: Optional[float]
    budget_ceiling: float
    booking_status: Literal["NONE", "PROPOSED", "CONFIRMED", "CANCELLED", "WALK_AWAY"]
    proposed_slot: Optional[str]
    confirmed_slot: Optional[str]
    should_walk_away: bool
    config: Dict[str, Any]
    last_reply: Optional[str]          # convenience for the API response