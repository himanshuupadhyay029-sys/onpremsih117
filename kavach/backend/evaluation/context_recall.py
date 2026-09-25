"""context_recall.py — Did retrieval surface the information the authoritative answer needs?

Python: split the Ground Truth into sentence-level units (statements that merely note the
source lacks information are not retrievable facts and are skipped).
LLM: judge whether each unit is attributable to the retrieved context.
Python: context_recall = attributed_units / total_units. Ground Truth is mandatory.
"""

import re
from typing import List, Optional

from backend.evaluation.llm import parse_indexed_verdicts
from backend.evaluation.schemas import GroundTruthResult, MetricResult, RetrievedPassage, render_context

NAME = "context_recall"

SYSTEM_PROMPT = "You are a strict evidence attribution judge. You answer only with valid JSON."

ATTRIBUTION_PROMPT = """RETRIEVED CONTEXT:
{context}

REFERENCE STATEMENTS:
{statements}

For each numbered reference statement decide whether the information it contains can be attributed to the RETRIEVED CONTEXT (stated in it or directly inferable from it). If a statement's key facts (numbers, names, conditions, steps) are absent from the context, it is NOT attributed.

Return JSON: {{"verdicts": [{{"index": 1, "attributed": true, "reason": "short reason"}}]}} with exactly one verdict per statement."""

_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_ABSENCE = re.compile(
    r"\b(?:source|document|text|context|it)\s+(?:does not|doesn't|do not|did not)\s+"
    r"(?:contain|specify|mention|state|provide|include|say|describe|cover|define|list|give)\b",
    re.IGNORECASE,
)


def split_ground_truth(ground_truth: str) -> List[str]:
    units: List[str] = []
    for line in ground_truth.splitlines():
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        for sentence in _SENTENCE_BOUNDARY.split(line):
            sentence = sentence.strip()
            if len(re.findall(r"\w+", sentence)) < 2 or _ABSENCE.search(sentence):
                continue
            units.append(sentence)
    return units


def judge_attribution(llm, units: List[str], context: str) -> List[bool]:
    numbered = "\n".join(f"{i}. {u}" for i, u in enumerate(units, start=1))
    data = llm.generate_json(ATTRIBUTION_PROMPT.format(context=context, statements=numbered), SYSTEM_PROMPT)
    return parse_indexed_verdicts(data, "attributed", len(units))


def compute_score(verdicts: List[bool]) -> float:
    if not verdicts:
        raise ValueError("Context recall is undefined for zero ground-truth units")
    return sum(1 for v in verdicts if v) / len(verdicts)


def evaluate_context_recall(
    llm,
    ground_truth: Optional[GroundTruthResult],
    passages: List[RetrievedPassage],
) -> MetricResult:
    if ground_truth is None or not ground_truth.ok:
        reason = ground_truth.error if ground_truth and ground_truth.error else "Ground truth unavailable"
        return MetricResult.failed(NAME, f"Context recall requires ground truth: {reason}")
    try:
        units = split_ground_truth(ground_truth.ground_truth)
        if not units:
            return MetricResult.not_applicable(NAME, "The source contains no facts that answer this query.")
        verdicts = judge_attribution(llm, units, render_context(passages))
        return MetricResult.completed(
            NAME,
            compute_score(verdicts),
            total_units=len(units),
            attributed_units=sum(verdicts),
        )
    except Exception as exc:
        return MetricResult.failed(NAME, f"Context recall evaluation failed: {exc}")
