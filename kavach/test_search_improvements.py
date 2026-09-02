"""test_search_improvements.py — Verification test suite for router keyword additions
and source citation rendering.
"""

import unittest
from backend.brain.router import route, _score_task
from backend.tools.search import search


class TestSearchImprovements(unittest.TestCase):

    def test_new_industrial_keyword_routing(self):
        """Test 5 realistic industrial/refinery queries with newly added keywords
        and confirm they route directly via fast rule-based matching."""
        queries = [
            # 1. Procedural query with 'steps for' and 'lockout'
            ("What are the steps for lockout tagout on pump 4?", "search"),
            # 2. Tolerance / limit query with 'maximum' and 'operating range'
            ("What is the maximum operating range for the condenser valve?", "search"),
            # 3. Emergency / compliance query with 'emergency' and 'protocol'
            ("What is the emergency shutdown protocol for crude distillation unit?", "search"),
            # 4. Maintenance schedule query with 'preventive maintenance' and 'inspection'
            ("Where is the preventive maintenance schedule for heat exchangers?", "search"),
            # 5. Formal document drafting with 'draft a' and 'safety report'
            ("Draft a safety report on hazardous gas isolation compliance", "document"),
            # 6. Formal summary document with 'executive summary'
            ("Prepare an executive summary of the quarterly pipeline inspection report", "document"),
        ]

        print("\n--- Testing 6 Realistic Industrial Query Routing Decisions ---")
        for query, expected_type in queries:
            decision = route(query)
            print(f"Task: '{query}'")
            print(f"  -> Routed: task_type='{decision.task_type}', reason='{decision.reason}'")
            self.assertEqual(decision.task_type, expected_type)
            self.assertIn("rule-based keyword match", decision.reason)

    def test_grounded_search_and_sources(self):
        """Test a grounded search query and verify return shape and source citations."""
        print("\n--- Testing Grounded Search and Source Extraction ---")
        res = search("What is the required response time for Severity 1 incidents?")
        print(f"Query Answer Preview: {res['answer'][:150]}...")
        print(f"Grounded: {res['grounded']}")
        print(f"Sources Count: {len(res['sources'])}")
        for s in res["sources"]:
            print(f"  - Source file: {s.get('filename')}")
            self.assertTrue(s.get("filename"))
            self.assertTrue(s.get("excerpt"))

        self.assertIn("grounded", res)
        self.assertIn("sources", res)
        self.assertIn("answer", res)


if __name__ == "__main__":
    unittest.main()
