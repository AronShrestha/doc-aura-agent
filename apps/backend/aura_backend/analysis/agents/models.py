from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class AgentRequest:
    agent_name: str
    task: str
    context: dict[str, Any]
    required: bool = True


@dataclass(slots=True)
class AgentResult:
    agent_name: str
    status: Literal["succeeded", "failed"]
    output: dict[str, Any]
    raw_text: str = ""
    error: str | None = None


@dataclass(slots=True)
class VisualContext:
    path: str
    media_type: str
    description: str
    documentation_relevance: str
    confidence: float = 0.0


@dataclass(slots=True)
class PlannedDoc:
    doc_id: str
    title: str
    category: str
    diataxis_type: Literal["reference", "explanation", "how-to"]
    target_path: str
    source_artifact_ids: list[str] = field(default_factory=list)
    uses_vlm_context: bool = False
    priority: int = 50
    writer: Literal["artifact", "system"] = "system"
    rationale: str = ""


@dataclass(slots=True)
class DocumentationPlan:
    docs: list[PlannedDoc]
    rationale: str


@dataclass(slots=True)
class VerificationReport:
    passed: bool
    citation_coverage: float
    unsupported_claims: int
    section_completeness: float
    issues: list[str] = field(default_factory=list)
