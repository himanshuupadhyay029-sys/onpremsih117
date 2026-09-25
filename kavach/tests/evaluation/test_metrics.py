import numpy as np
import pytest

from backend.evaluation import answer_relevancy, context_precision_reference, context_recall, faithfulness
from backend.evaluation.schemas import GroundTruthResult, RetrievedPassage

from conftest import FakeLLM

QUERY = "How long must backup tapes be retained?"
ANSWER = "Backup tapes are retained for 90 days [1]. They are stored off-site [1]."

PASSAGES = [
    RetrievedPassage(rank=1, text="Backup tapes are retained for 90 days and stored off-site.", source_filename="backup.md"),
    RetrievedPassage(rank=2, text="The cafeteria opens at 8 AM.", source_filename="facilities.md"),
]

GT_OK = GroundTruthResult(
    ground_truth="Backup tapes must be retained for 90 days. Tapes are stored off-site. Restores are tested quarterly.",
    status="ok",
)
GT_FAILED = GroundTruthResult(ground_truth="", status="failed", error="source missing")


# ---------------------------------------------------------------- faithfulness --

def test_faithfulness_all_claims_supported():
    llm = FakeLLM({
        "extract_claims": lambda p: {"claims": ["Backup tapes are retained for 90 days.", "Tapes are stored off-site."]},
        "verify_claims": lambda p: {"verdicts": [{"index": 1, "supported": True}, {"index": 2, "supported": True}]},
    })
    result = faithfulness.evaluate_faithfulness(llm, QUERY, ANSWER, PASSAGES)
    assert result.status == "completed" and result.score == 1.0
    verify_prompt = llm.prompts("verify_claims")[0]
    assert PASSAGES[0].text in verify_prompt


def test_faithfulness_unsupported_and_unjudged_claims_count_against_score():
    llm = FakeLLM({
        "extract_claims": lambda p: {"claims": ["A", "B", "C", "D"]},
        # Claim 3 unsupported, claim 4 never ruled on.
        "verify_claims": lambda p: {"verdicts": [
            {"index": 1, "supported": True}, {"index": 2, "supported": "true"}, {"index": 3, "supported": False},
        ]},
    })
    result = faithfulness.evaluate_faithfulness(llm, QUERY, ANSWER, PASSAGES)
    assert result.score == 0.5
    assert result.details == {"total_claims": 4, "supported_claims": 2}


def test_faithfulness_zero_claims_is_not_applicable_not_zero():
    llm = FakeLLM({"extract_claims": lambda p: {"claims": []}})
    result = faithfulness.evaluate_faithfulness(llm, QUERY, "I don't have enough information.", PASSAGES)
    assert result.status == "not_applicable"
    assert result.score is None
    assert llm.kinds() == ["extract_claims"]


def test_faithfulness_failure_is_explicit():
    llm = FakeLLM({"extract_claims": lambda p: {"unexpected": 1}})
    result = faithfulness.evaluate_faithfulness(llm, QUERY, ANSWER, PASSAGES)
    assert result.status == "failed" and result.score is None and result.error


def test_faithfulness_compute_score_rejects_zero_claims():
    with pytest.raises(ValueError):
        faithfulness.compute_score([])


# ------------------------------------------------------------ answer relevancy --

def _embed_by_lookup(table):
    return lambda texts: np.array([table[t] for t in texts])


def test_answer_relevancy_relevant_answer_scores_high():
    questions = ["How long are backup tapes kept?", "What is the tape retention period?", "Where are tapes stored?"]
    table = {QUERY: [1.0, 0.0], questions[0]: [1.0, 0.0], questions[1]: [1.0, 0.0], questions[2]: [0.8, 0.6]}
    llm = FakeLLM({"reverse_questions": lambda p: {"questions": questions}}, embed_fn=_embed_by_lookup(table))
    result = answer_relevancy.evaluate_answer_relevancy(llm, QUERY, ANSWER)
    assert result.status == "completed"
    assert result.score == pytest.approx((1.0 + 1.0 + 0.8) / 3, abs=1e-4)


def test_answer_relevancy_irrelevant_answer_scores_zero():
    questions = ["When does the cafeteria open?", "What are the cafeteria hours?", "Is breakfast served?"]
    table = {QUERY: [1.0, 0.0], **{q: [0.0, 1.0] for q in questions}}
    llm = FakeLLM({"reverse_questions": lambda p: {"questions": questions}}, embed_fn=_embed_by_lookup(table))
    result = answer_relevancy.evaluate_answer_relevancy(llm, QUERY, "The cafeteria opens at 8 AM.")
    assert result.score == 0.0


def test_answer_relevancy_reverse_questions_come_from_answer_only():
    questions = ["q1", "q2", "q3", "q4"]
    table = {QUERY: [1.0, 0.0], **{q: [1.0, 0.0] for q in questions}}
    llm = FakeLLM({"reverse_questions": lambda p: {"questions": questions}}, embed_fn=_embed_by_lookup(table))
    answer_relevancy.evaluate_answer_relevancy(llm, QUERY, ANSWER)

    prompt = llm.prompts("reverse_questions")[0]
    assert ANSWER in prompt
    assert QUERY not in prompt
    assert PASSAGES[0].text not in prompt
    # One embedding call: original query followed by the (capped) three generated questions.
    embed_calls = [c["payload"] for c in llm.calls if c["kind"] == "embed"]
    assert embed_calls == [[QUERY, "q1", "q2", "q3"]]
    assert "embed" in llm.kinds() and llm.kinds().count("reverse_questions") == 1


def test_answer_relevancy_cosine_average_is_deterministic():
    q = np.array([3.0, 4.0])
    m = np.array([[3.0, 4.0], [4.0, 3.0], [0.0, 1.0]])
    expected = np.mean([1.0, 24 / 25, 4 / 5])
    assert answer_relevancy.compute_score(q, m) == pytest.approx(expected)
    assert answer_relevancy.compute_score(q, m) == answer_relevancy.compute_score(q, m)
    assert answer_relevancy.compute_score(np.array([1.0, 0.0]), np.array([[-1.0, 0.0]])) == 0.0


def test_answer_relevancy_embedding_failure_is_explicit():
    def broken(texts):
        raise RuntimeError("embedding service down")

    llm = FakeLLM({"reverse_questions": lambda p: {"questions": ["a", "b", "c"]}}, embed_fn=broken)
    result = answer_relevancy.evaluate_answer_relevancy(llm, QUERY, ANSWER)
    assert result.status == "failed" and result.score is None


# -------------------------------------------------------------- context recall --

def test_split_ground_truth_units():
    gt = (
        "Backup tapes must be retained for 90 days. Tapes are stored off-site.\n"
        "- Restores are tested quarterly.\n"
        "The source does not specify who approves exceptions."
    )
    assert context_recall.split_ground_truth(gt) == [
        "Backup tapes must be retained for 90 days.",
        "Tapes are stored off-site.",
        "Restores are tested quarterly.",
    ]


def _recall_llm(flags):
    return FakeLLM({
        "recall": lambda p: {"verdicts": [{"index": i, "attributed": f} for i, f in enumerate(flags, start=1)]},
    })


def test_context_recall_complete_retrieval():
    llm = _recall_llm([1, 1, 1])
    result = context_recall.evaluate_context_recall(llm, GT_OK, PASSAGES)
    assert result.score == 1.0
    prompt = llm.prompts("recall")[0]
    assert "Restores are tested quarterly." in prompt and PASSAGES[0].text in prompt


def test_context_recall_partial_retrieval():
    result = context_recall.evaluate_context_recall(_recall_llm([1, 1, 0]), GT_OK, PASSAGES)
    assert result.score == pytest.approx(2 / 3, abs=1e-4)
    assert result.details == {"total_units": 3, "attributed_units": 2}


def test_context_recall_missing_retrieval_is_a_real_zero():
    result = context_recall.evaluate_context_recall(_recall_llm([0, 0, 0]), GT_OK, PASSAGES)
    assert result.status == "completed" and result.score == 0.0


def test_context_recall_requires_ground_truth():
    llm = _recall_llm([1, 1, 1])
    result = context_recall.evaluate_context_recall(llm, GT_FAILED, PASSAGES)
    assert result.status == "failed" and result.score is None
    assert "source missing" in result.error
    assert llm.calls == []


# ------------------------------------------------- context precision (reference) --

@pytest.mark.parametrize(
    "verdicts, expected",
    [
        ([1, 1, 0], 1.0),
        ([1, 0, 0], 1.0),
        ([0, 1, 1], (1 / 2 + 2 / 3) / 2),
        ([0, 0, 1], 1 / 3),
        ([1, 0, 1], (1 + 2 / 3) / 2),
        ([0, 0, 0], 0.0),
    ],
)
def test_map_at_k(verdicts, expected):
    assert context_precision_reference.compute_score([bool(v) for v in verdicts]) == pytest.approx(expected)


def _judge_by_marker(relevant_markers):
    def handler(prompt):
        passage = prompt.split("RETRIEVED PASSAGE:\n", 1)[1]
        return {"relevant": 1 if any(m in passage for m in relevant_markers) else 0}
    return handler


RANKED = [
    RetrievedPassage(rank=1, text="Backup tapes are retained for 90 days.", source_filename="backup.md"),
    RetrievedPassage(rank=2, text="Restore drills happen every quarter.", source_filename="backup.md"),
    RetrievedPassage(rank=3, text="The cafeteria opens at 8 AM.", source_filename="facilities.md"),
]


def test_context_precision_relevant_top_ranked_chunks():
    llm = FakeLLM({"precision": _judge_by_marker(["90 days", "quarter"])})
    result = context_precision_reference.evaluate_context_precision(llm, QUERY, RANKED, GT_OK)
    assert result.score == 1.0
    assert result.details == {"k": 3, "relevant_passages": 2}
    for prompt in llm.prompts("precision"):
        assert GT_OK.ground_truth in prompt and QUERY in prompt


def test_context_precision_irrelevant_chunks():
    llm = FakeLLM({"precision": _judge_by_marker([])})
    result = context_precision_reference.evaluate_context_precision(llm, QUERY, RANKED, GT_OK)
    assert result.status == "completed" and result.score == 0.0


def test_context_precision_partially_useful_chunk_counts_as_relevant():
    # Passage 2 covers only one fact of the reference answer; the calibrated judge accepts partial evidence.
    llm = FakeLLM({"precision": _judge_by_marker(["quarter"])})
    result = context_precision_reference.evaluate_context_precision(llm, QUERY, RANKED, GT_OK)
    assert result.score == pytest.approx(0.5)
    assert "partial evidence counts" in llm.prompts("precision")[0]


def test_context_precision_is_ranking_sensitive_and_never_reorders():
    relevant_first = FakeLLM({"precision": _judge_by_marker(["90 days"])})
    relevant_last = FakeLLM({"precision": _judge_by_marker(["90 days"])})
    reversed_ranking = list(reversed(RANKED))

    top = context_precision_reference.evaluate_context_precision(relevant_first, QUERY, RANKED, GT_OK)
    bottom = context_precision_reference.evaluate_context_precision(relevant_last, QUERY, reversed_ranking, GT_OK)
    assert top.score == 1.0
    assert bottom.score == pytest.approx(1 / 3, abs=1e-4)


def test_context_precision_requires_ground_truth():
    llm = FakeLLM({"precision": _judge_by_marker(["90 days"])})
    result = context_precision_reference.evaluate_context_precision(llm, QUERY, RANKED, GT_FAILED)
    assert result.status == "failed" and result.score is None
    assert llm.calls == []


def test_context_precision_any_judge_failure_fails_the_metric():
    def flaky(prompt):
        if "cafeteria" in prompt:
            raise RuntimeError("judge crashed")
        return {"relevant": 1}

    result = context_precision_reference.evaluate_context_precision(FakeLLM({"precision": flaky}), QUERY, RANKED, GT_OK)
    assert result.status == "failed" and result.score is None
