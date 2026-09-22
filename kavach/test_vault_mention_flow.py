from backend.brain.router import route
from backend.brain.agent import _parse_master_plan
from backend.tools.search import search
from backend.vault.retrieve import retrieve

def test_router_with_vault_files():
    # If user mentions vault file, it should route to search
    dec = route(
        task="Summarize this",
        vault_files=["kavach_sop.pdf"],
    )
    assert dec.task_type == "search"
    assert "kavach_sop.pdf" in dec.reason

def test_planner_fallback_with_vault_files():
    steps = _parse_master_plan(
        raw="Invalid JSON LLM response",
        original_task="Explain section 4",
        vault_files=["kavach_sop.pdf"],
    )
    assert len(steps) == 1
    assert steps[0]["tool"] == "search"

def test_search_accepts_target_files():
    # Calling search with target_files should not fail even if store is empty or populated
    res = search("What is the temperature limit?", target_files=["dummy_sop.pdf"])
    assert "answer" in res
    assert "sources" in res
    assert "grounded" in res

if __name__ == "__main__":
    test_router_with_vault_files()
    print("[PASS] test_router_with_vault_files")
    test_planner_fallback_with_vault_files()
    print("[PASS] test_planner_fallback_with_vault_files")
    test_search_accepts_target_files()
    print("[PASS] test_search_accepts_target_files")
    print("All vault mention flow tests PASSED successfully!")

