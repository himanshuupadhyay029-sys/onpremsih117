import copy
import json

import numpy as np
import pytest

from backend import config
from backend.evaluation import evaluation_service, llm as llm_module
from backend.evaluation.schemas import METRIC_NAMES

from conftest import FakeLLM

QUERY = "How long must backup tapes be retained?"
ANSWER_TEXT = "ANSWER_SENTINEL: tapes are retained for 90 days [1]."
PASSAGE_TEXT = "PASSAGE_SENTINEL: retention is 90 days."
SOURCE_TEXT = "SOURCE_SENTINEL full policy. Backup tapes must be retained for 90 days. Restores are tested quarterly."
GT_TEXT = "Backup tapes must be retained for 90 days. Restores are tested quarterly."


def make_agent_result(**overrides):
    result = {
        "task_id": "task-1",
        "task": QUERY,
        "status": "complete",
        "result": f"{ANSWER_TEXT}\n\n**Referenced Sources:**\n  • [1] backup.md",
        "sources": [],
        "step_outputs": [
            {
                "step_num": 1,
                "tool": "search",
                "output": "stale attempt",
                "sources": [{"id": 1, "filename": "stale.md", "excerpt": "STALE", "breadcrumb": "stale"}],
            },
            {
                "step_num": 1,
                "tool": "search",
                "output": ANSWER_TEXT,
                "sources": [
                    {"id": 1, "filename": "backup.md", "breadcrumb": "backup > Retention", "excerpt": PASSAGE_TEXT,
                     "score": 0.91, "chunk_id": "backup_c3", "parent_id": "backup_p1"},
                    {"id": 2, "filename": "backup.md", "breadcrumb": "backup > Restores", "excerpt": "Restore drills.",
                     "score": 0.55, "chunk_id": "backup_c7", "parent_id": "backup_p2"},
                ],
            },
        ],
        "state_snapshot": {"original_task": QUERY},
    }
    result.update(overrides)
    return result


def full_handlers(**overrides):
    handlers = {
        "ground_truth": lambda p: GT_TEXT,
        "extract_claims": lambda p: {"claims": ["Tapes are retained for 90 days."]},
        "verify_claims": lambda p: {"verdicts": [{"index": 1, "supported": True}]},
        "reverse_questions": lambda p: {"questions": ["How long are tapes kept?", "Tape retention?", "Retention period?"]},
        "recall": lambda p: {"verdicts": [{"index": 1, "attributed": True}, {"index": 2, "attributed": False}]},
        "precision": lambda p: {"relevant": 1 if "PASSAGE_SENTINEL" in p else 0},
    }
    handlers.update(overrides)
    return handlers


def unit_embed(texts):
    return np.array([[1.0, 0.0] for _ in texts])


@pytest.fixture
def enabled(monkeypatch, knowledge_dir):
    monkeypatch.setattr(config, "ENABLE_EVALUATION", True)
    from backend.vault.source_store import save_source_text

    save_source_text("backup.md", SOURCE_TEXT, user_id="alice")
    monkeypatch.setattr(evaluation_service, "log_event", lambda **kwargs: None)


# ------------------------------------------------------------------- disabled --

def test_disabled_makes_zero_calls_and_leaves_answer_untouched(monkeypatch, no_model_calls):
    monkeypatch.setattr(config, "ENABLE_EVALUATION", False)

    def forbidden(*args, **kwargs):
        raise AssertionError("EvaluationLLM must not be constructed when disabled")

    monkeypatch.setattr(llm_module, "EvaluationLLM", forbidden)
    agent_result = make_agent_result()
    before = copy.deepcopy(agent_result)

    evaluation = evaluation_service.evaluate_agent_result(agent_result, user_id="alice")

    assert evaluation == {"enabled": False, "status": "disabled"}
    assert "metrics" not in evaluation  # no fake zero scores
    assert agent_result == before
    initial, eval_input = evaluation_service.prepare_evaluation(agent_result, user_id="alice")
    assert initial == {"enabled": False, "status": "disabled"} and eval_input is None


# -------------------------------------------------------------------- enabled --

def test_ground_truth_runs_first_and_never_sees_answer_or_context(enabled):
    llm = FakeLLM(full_handlers(), embed_fn=unit_embed)
    events = []
    evaluation = evaluation_service.evaluate_agent_result(
        make_agent_result(), user_id="alice", llm=llm, on_event=lambda name, payload: events.append((name, payload))
    )

    assert llm.kinds()[0] == "ground_truth"
    assert llm.kinds().count("ground_truth") == 1
    gt_prompt = llm.prompts("ground_truth")[0]
    assert SOURCE_TEXT in gt_prompt and QUERY in gt_prompt
    assert "ANSWER_SENTINEL" not in gt_prompt and "PASSAGE_SENTINEL" not in gt_prompt

    # GT-dependent metrics consumed the generated ground truth.
    assert GT_TEXT.split(". ")[0] in llm.prompts("recall")[0]
    assert all(GT_TEXT in p for p in llm.prompts("precision"))

    assert evaluation["status"] == "completed"
    assert evaluation["metrics"] == {
        "faithfulness": 1.0,
        "answer_relevancy": 1.0,
        "context_precision": 1.0,
        "context_recall": 0.5,
    }
    assert all(v is None for v in evaluation["errors"].values())
    assert "ground_truth" not in json.dumps(evaluation["metrics"])
    assert GT_TEXT not in json.dumps(evaluation)  # ground truth stays internal

    names = [name for name, _ in events]
    assert names[:2] == ["evaluation_stage", "evaluation_stage"]
    assert events[0][1]["status"] == "running" and events[1][1]["status"] == "completed"
    metric_events = [payload for name, payload in events if name == "evaluation_metric"]
    assert sorted(e["metric"] for e in metric_events) == sorted(METRIC_NAMES)
    assert all(e["type"] == "evaluation_metric" for e in metric_events)


def test_ground_truth_failure_fails_only_reference_metrics(enabled, knowledge_dir):
    llm = FakeLLM(full_handlers(), embed_fn=unit_embed)
    # Scope the answer to a document whose full text was never persisted.
    evaluation = evaluation_service.evaluate_agent_result(
        make_agent_result(), user_id="alice", vault_files=["unknown.md"], llm=llm
    )

    assert "ground_truth" not in llm.kinds()
    assert "recall" not in llm.kinds() and "precision" not in llm.kinds()
    assert evaluation["errors"]["ground_truth"]
    for name in ("context_recall", "context_precision"):
        assert evaluation["metric_status"][name] == "failed"
        assert evaluation["metrics"][name] is None
        assert evaluation["errors"][name]
    assert evaluation["metrics"]["faithfulness"] == 1.0
    assert evaluation["metrics"]["answer_relevancy"] == 1.0
    assert evaluation["status"] == "completed"


def test_individual_metric_failure_preserves_other_scores(enabled):
    def broken(prompt):
        raise RuntimeError("judge exploded")

    llm = FakeLLM(full_handlers(verify_claims=broken), embed_fn=unit_embed)
    evaluation = evaluation_service.evaluate_agent_result(make_agent_result(), user_id="alice", llm=llm)

    assert evaluation["metrics"]["faithfulness"] is None
    assert evaluation["metric_status"]["faithfulness"] == "failed"
    assert "judge exploded" in evaluation["errors"]["faithfulness"]
    assert evaluation["metrics"]["answer_relevancy"] == 1.0
    assert evaluation["metrics"]["context_recall"] == 0.5
    assert evaluation["metrics"]["context_precision"] == 1.0


def test_all_metrics_failing_marks_evaluation_failed(enabled):
    def broken(prompt):
        raise RuntimeError("down")

    llm = FakeLLM({k: broken for k in full_handlers()}, embed_fn=unit_embed)
    evaluation = evaluation_service.evaluate_agent_result(make_agent_result(), user_id="alice", llm=llm)
    assert evaluation["status"] == "failed"
    assert all(v is None for v in evaluation["metrics"].values())


def test_unexpected_pipeline_crash_never_raises(enabled, monkeypatch):
    def crash(*args, **kwargs):
        raise RuntimeError("thread pool on fire")

    monkeypatch.setattr(evaluation_service, "run_evaluation", crash)
    evaluation = evaluation_service.evaluate_agent_result(make_agent_result(), user_id="alice", llm=FakeLLM())
    assert evaluation["status"] == "failed"
    assert all(v is None for v in evaluation["metrics"].values())


# -------------------------------------------------------------- applicability --

@pytest.mark.parametrize(
    "overrides",
    [
        {"step_outputs": [{"step_num": 1, "tool": "llm", "output": "Hello!"}]},
        {"status": "awaiting_approval"},
        {"result": ""},
    ],
)
def test_non_rag_answers_are_not_applicable_without_calls(enabled, overrides):
    llm = FakeLLM()
    evaluation = evaluation_service.evaluate_agent_result(make_agent_result(**overrides), user_id="alice", llm=llm)
    assert evaluation["status"] == "not_applicable"
    assert all(v is None for v in evaluation["metrics"].values())
    assert llm.calls == []


# ----------------------------------------------------------- context contract --

def test_evaluator_receives_exact_final_ranked_context():
    eval_input, reason = evaluation_service.build_evaluation_input(make_agent_result(), user_id="alice")
    assert reason is None
    assert eval_input.answer == ANSWER_TEXT  # "Referenced Sources" footer stripped
    assert eval_input.query == QUERY
    assert [(p.rank, p.text, p.chunk_id, p.parent_id, p.breadcrumb) for p in eval_input.passages] == [
        (1, PASSAGE_TEXT, "backup_c3", "backup_p1", "backup > Retention"),
        (2, "Restore drills.", "backup_c7", "backup_p2", "backup > Restores"),
    ]
    assert eval_input.source_filenames == ["backup.md"]


def test_source_scope_prefers_explicit_vault_selection():
    eval_input, _ = evaluation_service.build_evaluation_input(
        make_agent_result(), user_id="alice", vault_files=["policy.pdf", "policy.pdf"]
    )
    assert eval_input.source_filenames == ["policy.pdf"]


# ------------------------------------------------------ backend/frontend contract --

def test_response_contract_distinguishes_zero_failed_and_disabled(enabled):
    zero_llm = FakeLLM(
        full_handlers(recall=lambda p: {"verdicts": [{"index": 1, "attributed": 0}, {"index": 2, "attributed": 0}]},
                      verify_claims=lambda p: (_ for _ in ()).throw(RuntimeError("x"))),
        embed_fn=unit_embed,
    )
    evaluation = evaluation_service.evaluate_agent_result(make_agent_result(), user_id="alice", llm=zero_llm)
    json.dumps(evaluation)  # serializable for SSE / DB meta

    assert set(evaluation) >= {"enabled", "status", "metrics", "metric_status", "errors"}
    assert set(evaluation["metrics"]) == set(METRIC_NAMES)
    assert set(evaluation["errors"]) == {"ground_truth", *METRIC_NAMES}
    # Legitimate zero:
    assert evaluation["metrics"]["context_recall"] == 0.0
    assert evaluation["metric_status"]["context_recall"] == "completed"
    assert evaluation["errors"]["context_recall"] is None
    # Failure is None + error, never 0.0:
    assert evaluation["metrics"]["faithfulness"] is None
    assert evaluation["metric_status"]["faithfulness"] == "failed"
    assert evaluation["errors"]["faithfulness"]
    # All scores normalized:
    assert all(v is None or 0.0 <= v <= 1.0 for v in evaluation["metrics"].values())
