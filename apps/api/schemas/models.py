"""Request / response models. The TypeScript client is generated from these (OpenAPI)."""
from typing import Any, Literal

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    username: str


class JobCard(BaseModel):
    job_id: str
    title: str
    skills: list[str] = []
    budget_type: str
    budget_min: float | None = None
    budget_max: float | None = None
    connects_cost: int
    posted_at: str = ""
    # filled after analysis
    status: str | None = None
    action: str | None = None
    fit: float | None = None
    risk: str | None = None
    risk_flags: list[str] = []
    price: float | None = None


class JobList(BaseModel):
    jobs: list[JobCard]


class RunSummary(BaseModel):
    job_id: str
    title: str
    status: str
    action: str | None = None
    fit: float | None = None
    risk: str | None = None
    price: float | None = None
    connects_spent: int = 0
    tokens: int = 0
    duration_s: float | None = None
    reject_reason: str | None = None
    updated: str


class RunList(BaseModel):
    runs: list[RunSummary]


class RunState(BaseModel):
    job_id: str
    status: str
    running: bool
    next: list[str]
    interrupt: dict[str, Any] | None = None
    values: dict[str, Any]


class ResumeIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = None
    screening_answers: list[str] | None = None
    reason: str | None = None


class Started(BaseModel):
    job_id: str
    started: bool
    message: str


class Health(BaseModel):
    api: str
    marketplace: str
    llm_profile: str


class Message(BaseModel):
    message_id: str
    client_id: str
    job_id: str | None = None
    sender: str
    text: str
    sent_at: str


class MessageList(BaseModel):
    messages: list[Message]


class Analytics(BaseModel):
    analysed: int
    by_status: dict[str, int]
    by_action: dict[str, int]
    submitted: int
    connects_spent: int
    avg_tokens_per_job: float
    p50_latency_s: float | None
    p95_latency_s: float | None
    top_reject_reasons: list[str]
    top_skip_reasons: list[str]


class Settings(BaseModel):
    username: str
    persona: str
    headline: str
    hourly_rate: float
    skills: list[str]
    llm_profile: str
    models: dict[str, str]
    user: dict[str, Any]
    decision: dict[str, Any]
    budgets: dict[str, Any]


# ---------------- conversations (Client Liaison) ----------------
class ConversationSummary(BaseModel):
    client_id: str
    job_id: str | None = None
    last_text: str
    last_sender: str
    last_at: str
    unanswered: int                       # client messages after our last reply
    status: str | None = None             # conversation graph status (awaiting_approval, sent, ...)
    intent: str | None = None


class ConversationList(BaseModel):
    conversations: list[ConversationSummary]


class ConversationState(BaseModel):
    client_id: str
    status: str
    running: bool
    next: list[str]
    interrupt: dict[str, Any] | None = None
    messages: list[Message]
    values: dict[str, Any]


class MessageResumeIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str | None = None
    slot: str | None = None
    reason: str | None = None


# ---------------- long-term memory ----------------
class MemoryItem(BaseModel):
    key: str
    rule: str | None = None               # style memory
    kind: str | None = None
    jobs: list[str] = []
    count: int | None = None
    promoted_by: str | None = None
    category: str | None = None           # outcome memory
    samples: int | None = None
    positive: int | None = None
    reply_rate: float | None = None
    winning_evidence: list[str] = []
    updated_at: str


class MemoryView(BaseModel):
    style: list[MemoryItem]
    outcome: list[MemoryItem]
    style_candidates: list[MemoryItem]
    promotion_rules: dict[str, Any]       # the thresholds, so the user can see WHY something was learned


class SyncResult(BaseModel):
    proposals: int
    outcomes_recorded: int
    categories_promoted: list[str]
