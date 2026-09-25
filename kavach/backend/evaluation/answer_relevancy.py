"""answer_relevancy.py — Does the answer address the question? (reverse-question generation)

LLM: from the answer ALONE, generate the questions it answers.
NumPy: embed original query + generated questions, average the cosine similarities.
Neither retrieved context nor Ground Truth is used.
"""

from typing import List

import numpy as np

from backend.evaluation.schemas import MetricResult

NAME = "answer_relevancy"
NUM_QUESTIONS = 3

SYSTEM_PROMPT = "You generate questions from answers. You answer only with valid JSON."

REVERSE_QUESTION_PROMPT = """ANSWER:
{answer}

Write {n} different questions that this ANSWER directly answers. Each question must be answerable from the ANSWER alone and should reflect what the ANSWER is actually about.

Return JSON: {{"questions": ["question 1", "question 2", "question 3"]}}"""


def generate_reverse_questions(llm, answer: str, n: int = NUM_QUESTIONS) -> List[str]:
    data = llm.generate_json(REVERSE_QUESTION_PROMPT.format(answer=answer, n=n), SYSTEM_PROMPT)
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Reverse-question output is missing a 'questions' list")
    cleaned = [str(q).strip() for q in questions if str(q).strip()]
    if not cleaned:
        raise ValueError("Evaluator generated no reverse questions")
    return cleaned[:n]


def compute_score(query_vector: np.ndarray, question_vectors: np.ndarray) -> float:
    """Mean cosine similarity between the query and each generated question, clipped to [0, 1]."""
    q = np.asarray(query_vector, dtype=np.float64)
    m = np.atleast_2d(np.asarray(question_vectors, dtype=np.float64))
    norms = np.linalg.norm(m, axis=1) * np.linalg.norm(q)
    if np.any(norms == 0):
        raise ValueError("Cannot compute cosine similarity for a zero vector")
    sims = (m @ q) / norms
    return float(np.clip(np.mean(sims), 0.0, 1.0))


def evaluate_answer_relevancy(llm, query: str, answer: str) -> MetricResult:
    try:
        questions = generate_reverse_questions(llm, answer)
        vectors = llm.embed([query] + questions)
        return MetricResult.completed(NAME, compute_score(vectors[0], vectors[1:]), questions_generated=len(questions))
    except Exception as exc:
        return MetricResult.failed(NAME, f"Answer relevancy evaluation failed: {exc}")
