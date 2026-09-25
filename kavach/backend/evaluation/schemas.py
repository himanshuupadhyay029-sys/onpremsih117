"""schemas.py — Data contracts for the KAVACH RAG evaluation layer."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

METRIC_NAMES = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")

STATUS_DISABLED = "disabled"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class RetrievedPassage:
    """One passage of the exact context KAVACH packed into the answer prompt, in final rank order."""

    rank: int
    text: str
    source_filename: str
    breadcrumb: str = ""
    chunk_id: Optional[str] = None
    parent_id: Optional[str] = None
    score: Optional[float] = None
    step_num: Optional[int] = None


def render_context(passages: List[RetrievedPassage]) -> str:
    """Renders passages in their original rank order, as the answer generator saw them."""
    blocks = []
    for p in passages:
        header = f"[{p.rank}] {p.source_filename}"
        if p.breadcrumb and p.breadcrumb != p.source_filename:
            header += f" ({p.breadcrumb})"
        blocks.append(f"{header}\n{p.text.strip()}")
    return "\n\n".join(blocks)


@dataclass
class EvaluationInput:
    query: str
    answer: str
    passages: List[RetrievedPassage]
    source_filenames: List[str]
    user_id: Optional[str] = None


@dataclass
class GroundTruthResult:
    ground_truth: str
    status: str  # "ok" | "failed"
    error: Optional[str] = None
    source_truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.ground_truth.strip())


@dataclass
class MetricResult:
    name: str
    score: Optional[float]
    status: str  # completed | failed | not_applicable
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def completed(cls, name: str, score: float, **details: Any) -> "MetricResult":
        return cls(name=name, score=round(float(score), 4), status=STATUS_COMPLETED, details=details)

    @classmethod
    def failed(cls, name: str, error: str) -> "MetricResult":
        return cls(name=name, score=None, status=STATUS_FAILED, error=error)

    @classmethod
    def not_applicable(cls, name: str, reason: str) -> "MetricResult":
        return cls(name=name, score=None, status=STATUS_NOT_APPLICABLE, error=reason)

    def to_event(self) -> Dict[str, Any]:
        return {
            "type": "evaluation_metric",
            "metric": self.name,
            "score": self.score,
            "status": self.status,
            "error": self.error,
        }


def disabled_evaluation() -> Dict[str, Any]:
    return {"enabled": False, "status": STATUS_DISABLED}


def _empty_errors() -> Dict[str, Optional[str]]:
    return {"ground_truth": None, **{name: None for name in METRIC_NAMES}}


def running_evaluation() -> Dict[str, Any]:
    return {
        "enabled": True,
        "status": STATUS_RUNNING,
        "metrics": {name: None for name in METRIC_NAMES},
        "metric_status": {name: STATUS_RUNNING for name in METRIC_NAMES},
        "errors": _empty_errors(),
    }


def not_applicable_evaluation(reason: str) -> Dict[str, Any]:
    return {
        "enabled": True,
        "status": STATUS_NOT_APPLICABLE,
        "reason": reason,
        "metrics": {name: None for name in METRIC_NAMES},
        "metric_status": {name: STATUS_NOT_APPLICABLE for name in METRIC_NAMES},
        "errors": _empty_errors(),
    }


def failed_evaluation(error: str) -> Dict[str, Any]:
    errors = {key: error for key in _empty_errors()}
    return {
        "enabled": True,
        "status": STATUS_FAILED,
        "metrics": {name: None for name in METRIC_NAMES},
        "metric_status": {name: STATUS_FAILED for name in METRIC_NAMES},
        "errors": errors,
    }


def assemble_evaluation(ground_truth: GroundTruthResult, results: Dict[str, MetricResult]) -> Dict[str, Any]:
    """Builds the public evaluation object. Failed/not-applicable metrics are None, never 0.0."""
    metrics = {name: results[name].score for name in METRIC_NAMES}
    metric_status = {name: results[name].status for name in METRIC_NAMES}
    errors = _empty_errors()
    errors["ground_truth"] = None if ground_truth.ok else (ground_truth.error or "Ground truth generation failed")
    for name in METRIC_NAMES:
        errors[name] = results[name].error

    any_completed = any(status == STATUS_COMPLETED for status in metric_status.values())
    all_failed = all(status == STATUS_FAILED for status in metric_status.values())
    overall = STATUS_FAILED if all_failed else (STATUS_COMPLETED if any_completed else STATUS_NOT_APPLICABLE)
    return {
        "enabled": True,
        "status": overall,
        "metrics": metrics,
        "metric_status": metric_status,
        "errors": errors,
    }
