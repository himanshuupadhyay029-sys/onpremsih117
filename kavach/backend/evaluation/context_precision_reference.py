"""context_precision_reference.py — Context Precision, calibrated, with reference (Ground Truth).

LLM: judge each retrieved passage, in KAVACH's final rank order, as relevant (1) or
irrelevant (0) to arriving at the authoritative Ground Truth. Calibration: a passage that
supplies only part of the evidence needed is still relevant.
Python: MAP@K over the ranked verdicts. Passages are never re-ordered.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from backend.evaluation.llm import as_verdict
from backend.evaluation.schemas import GroundTruthResult, MetricResult, RetrievedPassage

NAME = "context_precision"

SYSTEM_PROMPT = "You are a calibrated retrieval relevance judge. You answer only with valid JSON."

RELEVANCE_PROMPT = """QUESTION:
{query}

REFERENCE ANSWER (authoritative):
{ground_truth}

RETRIEVED PASSAGE:
{passage}

Is this passage useful for arriving at the REFERENCE ANSWER to the QUESTION?
- Relevant (1): the passage contains at least one piece of information the reference answer relies on, even if it covers only part of the answer (partial evidence counts).
- Irrelevant (0): nothing in the passage contributes to the reference answer, even if it is on a related topic.

Return JSON: {{"relevant": 1, "reason": "short reason"}} using 1 or 0."""


def judge_passage(llm, query: str, ground_truth: str, passage: RetrievedPassage) -> bool:
    prompt = RELEVANCE_PROMPT.format(query=query, ground_truth=ground_truth, passage=passage.text.strip())
    data = llm.generate_json(prompt, SYSTEM_PROMPT)
    if "relevant" not in data:
        raise ValueError(f"Relevance output for passage {passage.rank} is missing 'relevant'")
    return as_verdict(data["relevant"])


def compute_score(verdicts: List[bool]) -> float:
    """MAP@K: mean of precision@k taken at every relevant rank k; 0.0 when nothing is relevant."""
    if not verdicts:
        raise ValueError("Context precision is undefined without retrieved passages")
    relevant_total = sum(1 for v in verdicts if v)
    if relevant_total == 0:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for k, is_relevant in enumerate(verdicts, start=1):
        if is_relevant:
            hits += 1
            precision_sum += hits / k
    return precision_sum / relevant_total


def evaluate_context_precision(
    llm,
    query: str,
    passages: List[RetrievedPassage],
    ground_truth: Optional[GroundTruthResult],
) -> MetricResult:
    if ground_truth is None or not ground_truth.ok:
        reason = ground_truth.error if ground_truth and ground_truth.error else "Ground truth unavailable"
        return MetricResult.failed(NAME, f"Context precision requires ground truth: {reason}")
    if not passages:
        return MetricResult.not_applicable(NAME, "No passages were retrieved.")
    try:
        workers = max(1, min(len(passages), getattr(llm, "parallelism", 1)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="eval-cp") as pool:
            verdicts = list(pool.map(lambda p: judge_passage(llm, query, ground_truth.ground_truth, p), passages))
        return MetricResult.completed(
            NAME,
            compute_score(verdicts),
            k=len(verdicts),
            relevant_passages=sum(verdicts),
        )
    except Exception as exc:
        return MetricResult.failed(NAME, f"Context precision evaluation failed: {exc}")
