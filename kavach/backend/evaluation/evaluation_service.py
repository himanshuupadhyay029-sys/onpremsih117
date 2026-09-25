"""evaluation_service.py — Orchestrates the optional RAG evaluation of a finished KAVACH answer.

Order: Ground Truth (from the full authoritative source) first, then Faithfulness,
Answer Relevancy, Context Recall and Context Precision (with reference) in parallel.
Evaluation reads the exact ranked context the answer was generated from; it never
retrieves again and never alters the agent result it is given.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend import config
from backend.audit.logbook import log_event
from backend.evaluation.answer_relevancy import evaluate_answer_relevancy
from backend.evaluation.context_precision_reference import evaluate_context_precision
from backend.evaluation.context_recall import evaluate_context_recall
from backend.evaluation.faithfulness import evaluate_faithfulness
from backend.evaluation.ground_truth import build_ground_truth, load_authoritative_source
from backend.evaluation.schemas import (
    METRIC_NAMES,
    EvaluationInput,
    MetricResult,
    RetrievedPassage,
    assemble_evaluation,
    disabled_evaluation,
    failed_evaluation,
    not_applicable_evaluation,
    running_evaluation,
)

logger = logging.getLogger("kavach.evaluation")

EventCallback = Callable[[str, Dict[str, Any]], None]

_REFERENCED_SOURCES_FOOTER = re.compile(r"\n+\*\*Referenced Sources:\*\*[\s\S]*$")


def is_enabled() -> bool:
    return bool(config.ENABLE_EVALUATION)


def extract_retrieved_passages(agent_result: Dict[str, Any]) -> List[RetrievedPassage]:
    """Collects the final packed vault context, in the rank order used for answer generation.

    Only the latest attempt of each plan step counts, matching what the finalizer used.
    """
    latest_by_step: Dict[Any, Dict[str, Any]] = {}
    for output in agent_result.get("step_outputs") or []:
        latest_by_step[output.get("step_num")] = output

    passages: List[RetrievedPassage] = []
    for output in latest_by_step.values():
        if output.get("tool") != "search":
            continue
        for source in output.get("sources") or []:
            text = str(source.get("excerpt") or "").strip()
            if not text:
                continue
            passages.append(
                RetrievedPassage(
                    rank=len(passages) + 1,
                    text=text,
                    source_filename=source.get("filename") or source.get("source_filename") or "",
                    breadcrumb=source.get("breadcrumb") or "",
                    chunk_id=source.get("chunk_id"),
                    parent_id=source.get("parent_id"),
                    score=source.get("score"),
                    step_num=output.get("step_num"),
                )
            )
    return passages


def resolve_source_scope(vault_files: Optional[List[str]], passages: List[RetrievedPassage]) -> List[str]:
    """Documents the answer is expected to come from: the operator's explicit vault selection,
    otherwise the documents KAVACH's retrieval resolved for this query."""
    candidates = [f for f in (vault_files or []) if isinstance(f, str) and f.strip()]
    if not candidates:
        candidates = [p.source_filename for p in passages if p.source_filename]
    return list(dict.fromkeys(candidates))


def build_evaluation_input(
    agent_result: Dict[str, Any],
    user_id: Optional[str] = None,
    vault_files: Optional[List[str]] = None,
) -> Tuple[Optional[EvaluationInput], Optional[str]]:
    if agent_result.get("status") != "complete":
        return None, "Evaluation applies only to completed answers."
    answer = _REFERENCED_SOURCES_FOOTER.sub("", str(agent_result.get("result") or "")).strip()
    if not answer:
        return None, "No answer was generated."
    passages = extract_retrieved_passages(agent_result)
    if not passages:
        return None, "No Knowledge Vault context was retrieved for this answer."
    snapshot = agent_result.get("state_snapshot") or {}
    query = str(snapshot.get("original_task") or agent_result.get("task") or "").strip()
    return (
        EvaluationInput(
            query=query,
            answer=answer,
            passages=passages,
            source_filenames=resolve_source_scope(vault_files, passages),
            user_id=user_id,
        ),
        None,
    )


def run_evaluation(
    eval_input: EvaluationInput,
    llm=None,
    on_event: Optional[EventCallback] = None,
    source_loader=load_authoritative_source,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    if llm is None:
        from backend.evaluation.llm import EvaluationLLM

        llm = EvaluationLLM()

    def emit(event: str, payload: Dict[str, Any]) -> None:
        if on_event is None:
            return
        try:
            on_event(event, payload)
        except Exception as exc:
            logger.debug("Evaluation event emission failed: %s", exc)

    query, answer, passages = eval_input.query, eval_input.answer, eval_input.passages

    emit("evaluation_stage", {"type": "evaluation_stage", "stage": "ground_truth", "status": "running"})
    ground_truth = build_ground_truth(
        llm, query, eval_input.source_filenames, user_id=eval_input.user_id, source_loader=source_loader
    )
    emit(
        "evaluation_stage",
        {
            "type": "evaluation_stage",
            "stage": "ground_truth",
            "status": "completed" if ground_truth.ok else "failed",
            "error": ground_truth.error,
        },
    )

    metric_jobs: Dict[str, Callable[[], MetricResult]] = {
        "faithfulness": lambda: evaluate_faithfulness(llm, query, answer, passages),
        "answer_relevancy": lambda: evaluate_answer_relevancy(llm, query, answer),
        "context_recall": lambda: evaluate_context_recall(llm, ground_truth, passages),
        "context_precision": lambda: evaluate_context_precision(llm, query, passages, ground_truth),
    }
    results: Dict[str, MetricResult] = {}
    with ThreadPoolExecutor(max_workers=len(metric_jobs), thread_name_prefix="eval-metric") as pool:
        futures = {pool.submit(job): name for name, job in metric_jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = MetricResult.failed(name, f"{name} evaluation crashed: {exc}")
            results[name] = result
            emit("evaluation_metric", result.to_event())

    evaluation = assemble_evaluation(ground_truth, results)
    if ground_truth.source_truncated:
        evaluation["warnings"] = [
            f"Source document exceeded {config.EVALUATION_MAX_SOURCE_CHARS} characters and was truncated for ground truth generation."
        ]

    log_event(
        task_id=task_id,
        event_type="evaluation",
        actor="evaluator",
        summary="RAG evaluation "
        + evaluation["status"]
        + ": "
        + ", ".join(f"{m}={evaluation['metrics'][m]}" for m in METRIC_NAMES),
        metadata={
            "metrics": evaluation["metrics"],
            "metric_status": evaluation["metric_status"],
            "errors": evaluation["errors"],
            "source_documents": eval_input.source_filenames,
            "passages_evaluated": len(passages),
            "metric_details": {name: results[name].details for name in METRIC_NAMES},
        },
        external_calls=0,
        user_id=eval_input.user_id,
    )
    return evaluation


def prepare_evaluation(
    agent_result: Dict[str, Any],
    user_id: Optional[str] = None,
    vault_files: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Optional[EvaluationInput]]:
    """Returns (initial evaluation payload, input to evaluate or None). Makes no model calls."""
    if not is_enabled():
        return disabled_evaluation(), None
    try:
        eval_input, reason = build_evaluation_input(agent_result, user_id=user_id, vault_files=vault_files)
    except Exception as exc:
        return failed_evaluation(f"Could not prepare evaluation: {exc}"), None
    if eval_input is None:
        return not_applicable_evaluation(reason or "Evaluation not applicable."), None
    return running_evaluation(), eval_input


def complete_evaluation(
    eval_input: EvaluationInput,
    on_event: Optional[EventCallback] = None,
    task_id: Optional[str] = None,
    llm=None,
) -> Dict[str, Any]:
    """Runs the pipeline; never raises, so the user's answer is never affected."""
    try:
        return run_evaluation(eval_input, llm=llm, on_event=on_event, task_id=task_id)
    except Exception as exc:
        logger.warning("RAG evaluation failed: %s", exc)
        return failed_evaluation(f"Evaluation pipeline error: {exc}")


def evaluate_agent_result(
    agent_result: Dict[str, Any],
    user_id: Optional[str] = None,
    vault_files: Optional[List[str]] = None,
    on_event: Optional[EventCallback] = None,
    llm=None,
) -> Dict[str, Any]:
    """Synchronous entry point: returns the evaluation object for a finished agent result."""
    initial, eval_input = prepare_evaluation(agent_result, user_id=user_id, vault_files=vault_files)
    if eval_input is None:
        return initial
    return complete_evaluation(eval_input, on_event=on_event, task_id=agent_result.get("task_id"), llm=llm)
