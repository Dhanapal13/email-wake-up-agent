# Email Wake-up Agent
An autonomous Email Wake-Up Agent with following capabilities.
 

- Starts and continues email conversations with prospects about a contract/gig opportunity.

- Primary goal: get the prospect to book a call.

- Must negotiate rates within a hard budget ceiling, handle objections, and never lose context.
-  Critically must handle the reschedule loop cleanly any number of times (prospect books → later cancels → agent re-opens negotiation and books a new slot while remembering everything.  







## High-Level System Architecture

```mermaid

flowchart TB
    subgraph External["External World"]
        Prospect["Prospect<br/>(Email Client)"]
        TestInbox["Test Inbox<br/>(Gmail / Resend / Mailgun)"]
    end

    subgraph Ingress["Inbound Path"]
        Webhook["FastAPI /webhook/email"]
        IMAP["IMAP Poller<br/>(optional)"]
    end

    subgraph Core["Email Wake-Up Agent"]
        direction TB
        Config["config.yaml<br/>• Gig description<br/>• Budget ceiling<br/>• Tone<br/>• Model<br/>• Available slots"]
        
        subgraph Agent["LangGraph Agent"]
            Perceive["perceive<br/>• Intent classification<br/>• Rate extraction"]
            Reason["reason<br/>• Full history + budget<br/>• Decide reply + action"]
            Act["act<br/>• Send email<br/>• Persist<br/>• Update booking"]
        end

        Memory[("SQLite Thread Store<br/>Exact chronological<br/>messages + metadata")]
        Calendar["CalendarService<br/>(Stub → real later)<br/>propose / book"]
        EmailClient["EmailClient<br/>SMTP Outbound<br/>+ Webhook/IMAP Inbound"]
    end

    Prospect -->|"Reply"| TestInbox
    TestInbox -->|"Webhook / IMAP"| Ingress
    Ingress --> Perceive
    Config --> Reason
    Memory <-->|"Load full history<br/>Append every message"| Agent
    Perceive --> Reason
    Reason --> Act
    Act --> EmailClient
    Act --> Calendar
    EmailClient -->|"Outbound email"| TestInbox
    TestInbox -->|"Delivered"| Prospect

    style Agent fill:#1e3a5f,stroke:#4a9eff,color:#fff
    style Memory fill:#2d4a22,stroke:#6bcb4a,color:#fff
    style Config fill:#4a3728,stroke:#e8a838,color:#fff
```


## LangGraph Agent Loop (Perception → Reasoning → Action)

```mermaid
stateDiagram-v2
    [*] --> LoadHistory: New inbound email arrives

    LoadHistory --> Perceive: Load entire thread from SQLite

    state Perceive {
        [*] --> ClassifyIntent
        ClassifyIntent --> ExtractRate: interested | curious | objecting<br/>declining | silent | reschedule | booked
        ExtractRate --> [*]
    }

    Perceive --> Reason

    state Reason {
        [*] --> BuildContext
        BuildContext --> LLMDecide: System prompt + full history<br/>+ budget + current booking status
        LLMDecide --> DecideAction
        DecideAction --> [*]
    }

    Reason --> Act

    state Act {
        [*] --> PersistOutbound
        PersistOutbound --> SendEmail
        SendEmail --> UpdateBookingStatus
        UpdateBookingStatus --> [*]
    }

    Act --> [*]: Reply sent & state saved

    note right of Reason
        Budget hard check:
        if quoted_rate > ceiling → walk_away = true
    end note

```

## Booking / Reschedule State Machine (Critical Path)

```mermaid
stateDiagram-v2
    [*] --> NONE: Thread starts

    NONE --> PROPOSED: Prospect shows interest<br/>(intent = interested/curious)
    PROPOSED --> CONFIRMED: Prospect accepts slot
    PROPOSED --> NONE: Prospect rejects / silent too long

    CONFIRMED --> CANCELLED: Prospect says “can’t make it”<br/>(intent = reschedule)
    CANCELLED --> PROPOSED: Agent re-proposes new slot<br/>(full history preserved)
    PROPOSED --> CONFIRMED: Prospect accepts new slot

    CONFIRMED --> CONFIRMED: Normal confirmation
    CANCELLED --> CANCELLED: Repeated cancellations (N times)

    NONE --> WALK_AWAY: Rate > budget or clear decline
    PROPOSED --> WALK_AWAY: Rate > budget after negotiation
    CONFIRMED --> WALK_AWAY: (rare) final hard no

    WALK_AWAY --> [*]: Polite close, thread archived

    note right of CANCELLED
        Key design point:
        Full chronological history
        is always reloaded.
        Agent never starts from zero.
    end note
```


How to run the project:

cd email-wakeup-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start Ollama (required for real LLM replies)
ollama pull llama3.1:8b
ollama serve

# API
uv run uvicorn app.main:app --reload --port 8000

# Generate the three required transcripts
python -m scripts.demo_transcripts