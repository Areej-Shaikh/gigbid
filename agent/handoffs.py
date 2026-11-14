"""Typed hand-offs between agents (C3). Agents exchange these objects, never free text."""
from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = Field(default_factory=list, description="Concrete things to deliver")
    requirements: list[str] = Field(default_factory=list, description="Separate requirements, one idea each")
    skills: list[str] = Field(default_factory=list)
    budget_type: str = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str = ""
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated")


class RiskReport(BaseModel):
    level: Literal["low", "medium", "high"]
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    client_summary: str = ""


class RequirementEvidence(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    best_score: float = 0
    covered: bool = False


class FitReport(BaseModel):
    fit_score: float = Field(ge=0, le=1)
    matrix: list[RequirementEvidence] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)


class PriceQuote(BaseModel):
    amount: float
    budget_type: str
    rationale: list[str] = Field(default_factory=list)
    market: dict = Field(default_factory=dict)
    connects_cost: int = 0
    connects_balance: int | None = None
    connects_worth_it: bool = True


class DraftText(BaseModel):
    """What the Writer LLM returns. Claims are cited inline as [evidence_id]."""
    cover_letter: str
    screening_answers: list[str] = Field(default_factory=list)


class ClaimCheck(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["supported", "partial", "unsupported"]
    note: str = ""


class VerificationReport(BaseModel):
    checks: list[ClaimCheck] = Field(default_factory=list)
    unsupported_before: int = 0
    unsupported_after: int = 0
    removed: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    instructions: str = ""


class ComplianceVerdict(BaseModel):
    passed: bool
    blocked: bool = False
    violations: list[str] = Field(default_factory=list)
    cover_letter: str = ""
    screening_answers: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    """What the human sends back from the UI to resume the graph."""
    action: Literal["approve", "edit", "reject"]
    cover_letter: str | None = None
    screening_answers: list[str] | None = None
    reason: str | None = None


# ---------------- conversation graph (Client Liaison) ----------------
class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    summary: str = Field("", description="One sentence: what the client wants")
    reasons: list[str] = Field(default_factory=list)


class ReplyDraft(BaseModel):
    """What the Client Liaison LLM returns."""
    text: str


class MessageApproval(BaseModel):
    """What the human sends back from the Messages screen to resume the conversation graph."""
    action: Literal["approve", "edit", "reject"]
    text: str | None = None          # edited reply
    slot: str | None = None          # interview slot the user picked (ISO start)
    reason: str | None = None
