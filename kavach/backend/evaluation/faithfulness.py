"""faithfulness.py — Are the answer's factual claims supported by the retrieved context?

LLM: extract claims from the answer, then judge each claim against the retrieved context.
Python: faithfulness = supported_claims / total_claims. Ground Truth is not used.
"""

from typing import List

from backend.evaluation.llm import parse_indexed_verdicts
from backend.evaluation.schemas import MetricResult, RetrievedPassage, render_context

NAME = "faithfulness"

SYSTEM_PROMPT = "You are a meticulous fact-checking assistant. You answer only with valid JSON."

EXTRACT_PROMPT = """QUESTION:
{query}

ANSWER:
{answer}

Break the ANSWER into its individual factual claims. Each claim must be a short, self-contained statement that can be checked on its own (resolve pronouns). Ignore greetings, formatting, citation markers like [1], and statements that only say information is missing.

Return JSON: {{"claims": ["claim 1", "claim 2"]}}
Return {{"claims": []}} if the answer makes no factual claims."""

VERIFY_PROMPT = """CONTEXT:
{context}

CLAIMS:
{claims}

For each numbered claim decide whether it is supported by the CONTEXT: it is stated in or can be directly inferred from the CONTEXT. A claim that adds details the CONTEXT does not contain, or contradicts it, is NOT supported.

Return JSON: {{"verdicts": [{{"index": 1, "supported": true, "reason": "short reason"}}]}} with exactly one verdict per claim."""


def extract_claims(llm, query: str, answer: str) -> List[str]:
    data = llm.generate_json(EXTRACT_PROMPT.format(query=query, answer=answer), SYSTEM_PROMPT)
    claims = data.get("claims")
    if not isinstance(claims, list):
        raise ValueError("Claim extraction output is missing a 'claims' list")
    return [str(c).strip() for c in claims if str(c).strip()]


def verify_claims(llm, claims: List[str], context: str) -> List[bool]:
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, start=1))
    data = llm.generate_json(VERIFY_PROMPT.format(context=context, claims=numbered), SYSTEM_PROMPT)
    return parse_indexed_verdicts(data, "supported", len(claims))


def compute_score(verdicts: List[bool]) -> float:
    if not verdicts:
        raise ValueError("Faithfulness is undefined for zero claims")
    return sum(1 for v in verdicts if v) / len(verdicts)


def evaluate_faithfulness(llm, query: str, answer: str, passages: List[RetrievedPassage]) -> MetricResult:
    try:
        claims = extract_claims(llm, query, answer)
        if not claims:
            return MetricResult.not_applicable(NAME, "The answer contains no factual claims to verify.")
        verdicts = verify_claims(llm, claims, render_context(passages))
        return MetricResult.completed(
            NAME,
            compute_score(verdicts),
            total_claims=len(claims),
            supported_claims=sum(verdicts),
        )
    except Exception as exc:
        return MetricResult.failed(NAME, f"Faithfulness evaluation failed: {exc}")
