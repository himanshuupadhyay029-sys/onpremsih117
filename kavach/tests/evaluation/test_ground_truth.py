import inspect

import pytest

from backend import config
from backend.evaluation.ground_truth import (
    AuthoritativeSource,
    SourceUnavailableError,
    build_ground_truth,
    generate_ground_truth,
    load_authoritative_source,
)
from backend.vault import ingest
from backend.vault.source_store import load_source_text, save_source_text

from conftest import FakeLLM

SOURCE = "# Backup Policy\n\nBackup tapes must be retained for 90 days.\n\nRestores are tested quarterly."


def test_generator_signature_cannot_receive_answer_or_context():
    params = set(inspect.signature(generate_ground_truth).parameters)
    assert params == {"llm", "query", "full_source_document"}
    assert not {"answer", "context", "passages", "retrieved_context"} & set(
        inspect.signature(build_ground_truth).parameters
    )


def test_ground_truth_uses_query_and_full_source():
    llm = FakeLLM({"ground_truth": lambda p: "Backup tapes must be retained for 90 days."})
    result = generate_ground_truth(llm, "How long are tapes retained?", SOURCE)
    assert result.ok and result.ground_truth == "Backup tapes must be retained for 90 days."
    prompt = llm.prompts("ground_truth")[0]
    assert SOURCE in prompt and "How long are tapes retained?" in prompt


def test_ground_truth_failures_are_explicit():
    assert generate_ground_truth(FakeLLM(), "q", "   ").status == "failed"

    def boom(prompt):
        raise RuntimeError("model offline")

    failed = generate_ground_truth(FakeLLM({"ground_truth": boom}), "q", SOURCE)
    assert failed.status == "failed" and failed.ground_truth == "" and "model offline" in failed.error

    empty = generate_ground_truth(FakeLLM({"ground_truth": lambda p: "  "}), "q", SOURCE)
    assert empty.status == "failed"


def test_build_ground_truth_reports_unavailable_source_without_model_call():
    llm = FakeLLM()

    def loader(filenames, user_id=None):
        raise SourceUnavailableError("Full source text is not available for: x.md")

    result = build_ground_truth(llm, "q", ["x.md"], source_loader=loader)
    assert result.status == "failed" and "x.md" in result.error
    assert llm.calls == []


def test_build_ground_truth_flags_truncated_source():
    llm = FakeLLM({"ground_truth": lambda p: "answer"})
    loader = lambda filenames, user_id=None: AuthoritativeSource(text="abc", filenames=filenames, truncated=True)
    assert build_ground_truth(llm, "q", ["a.md"], source_loader=loader).source_truncated


def test_loader_reads_persisted_full_source_per_user(knowledge_dir):
    save_source_text("policy.md", SOURCE, user_id="alice")
    source = load_authoritative_source(["policy.md"], user_id="alice")
    assert source.text == SOURCE and not source.truncated
    with pytest.raises(SourceUnavailableError):
        load_authoritative_source(["policy.md"], user_id="bob")


def test_loader_combines_resolved_scope_and_fails_if_any_document_missing(knowledge_dir):
    save_source_text("a.md", "Alpha facts.", user_id="u")
    save_source_text("b.md", "Beta facts.", user_id="u")
    combined = load_authoritative_source(["a.md", "b.md"], user_id="u").text
    assert "=== Document: a.md ===\nAlpha facts." in combined and "=== Document: b.md ===\nBeta facts." in combined
    with pytest.raises(SourceUnavailableError, match="c.md"):
        load_authoritative_source(["a.md", "c.md"], user_id="u")
    with pytest.raises(SourceUnavailableError):
        load_authoritative_source([], user_id="u")


def test_loader_truncates_to_configured_budget(knowledge_dir):
    save_source_text("big.md", "x" * 500, user_id="u")
    source = load_authoritative_source(["big.md"], user_id="u", max_chars=100)
    assert len(source.text) == 100 and source.truncated


def test_loader_reextracts_legacy_uploads_without_model_calls(knowledge_dir, no_model_calls):
    uploads_dir, _ = config.get_user_vault_dirs("u")
    (uploads_dir / "legacy.md").write_text(SOURCE, encoding="utf-8")
    assert load_authoritative_source(["legacy.md"], user_id="u").text == SOURCE
    assert load_source_text("legacy.md", user_id="u") == SOURCE  # cached for next time

    (uploads_dir / "scan.png").write_bytes(b"not really a png")
    with pytest.raises(SourceUnavailableError):
        load_authoritative_source(["scan.png"], user_id="u")


def test_ingestion_persists_full_normalized_source_and_delete_removes_it(knowledge_dir, monkeypatch, tmp_path):
    monkeypatch.setattr(ingest.registry, "get_model", lambda role: "fake-embed")
    monkeypatch.setattr(ingest.ollama, "embed_batch", lambda model, texts, **kw: [[0.1, 0.2, 0.3] for _ in texts])
    monkeypatch.setattr(ingest, "log_event", lambda **kwargs: None)

    doc = tmp_path / "policy.md"
    doc.write_bytes(SOURCE.replace("\n", "\r\n").encode("utf-8"))
    result = ingest.ingest_document(doc, user_id="alice")
    assert result["chunk_count"] >= 1

    stored = load_source_text("policy.md", user_id="alice")
    assert stored == SOURCE  # the whole document, not chunks, with normalized newlines

    ingest.delete_document("policy.md", user_id="alice")
    assert load_source_text("policy.md", user_id="alice") is None
