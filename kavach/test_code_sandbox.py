"""test_code_sandbox.py — Comprehensive test suite for the hardened code sandbox.

Verifies:
1. Language detection logic (Python, JavaScript, C)
2. Docker pre-flight state classification
3. Code generation prompt templates
4. Container execution (if Docker running) or Fail-Closed verification (if Docker offline)
5. Zero-network enforcement (--network none)
"""

import sys
import unittest
from backend.tools.code import detect_language, GENERATE_PROMPTS, RETRY_PROMPTS
from backend.tools.sandbox import inspect_docker_status, run_code, LANGUAGE_CONFIGS


class TestCodeSandbox(unittest.TestCase):

    def test_language_detection(self):
        """Verify prompt keyword matching accurately routes to the right language."""
        # Python detection (default and explicit)
        self.assertEqual(detect_language("write a python script to calculate primes"), "python")
        self.assertEqual(detect_language("compute the fibonacci sequence"), "python")
        self.assertEqual(detect_language("def solve_equation(x): return x * 2"), "python")

        # JavaScript / Node detection
        self.assertEqual(detect_language("write a javascript function to sort array"), "javascript")
        self.assertEqual(detect_language("create a node.js script that reads json"), "javascript")
        self.assertEqual(detect_language("in js, print the first 10 factorials"), "javascript")

        # C detection
        self.assertEqual(detect_language("write a c program to simulate pipe flow"), "c")
        self.assertEqual(detect_language("implement a quicksort algorithm in c"), "c")
        self.assertEqual(detect_language("#include <stdio.h> print hello world"), "c")

    def test_docker_preflight_classification(self):
        """Verify inspect_docker_status returns a known valid classification."""
        state, detail = inspect_docker_status()
        self.assertIn(state, {"HEALTHY", "DAEMON_STOPPED", "NOT_INSTALLED", "PERMISSION_DENIED", "ERROR"})
        print(f"\n[Test] Docker status on this machine: state='{state}', detail='{detail}'")

    def test_language_configs(self):
        """Verify all 3 supported languages have valid image, filename, and command mappings."""
        for lang in ["python", "javascript", "c"]:
            self.assertIn(lang, LANGUAGE_CONFIGS)
            cfg = LANGUAGE_CONFIGS[lang]
            self.assertTrue(cfg["image"])
            self.assertTrue(cfg["filename"])
            self.assertTrue(cfg["command"])

    def test_sandbox_execution_or_fail_closed(self):
        """Tests execution if Docker is healthy, or confirms strict fail-closed if Docker is offline."""
        state, detail = inspect_docker_status()

        if state == "HEALTHY":
            print("\n[Test] Docker is HEALTHY. Testing live execution for Python, JS, and C...")

            # 1. Python execution
            py_code = "print(sum([1, 2, 3, 4, 5]))"
            py_res = run_code(py_code, language="python")
            self.assertTrue(py_res["success"])
            self.assertEqual(py_res["stdout"].strip(), "15")
            self.assertEqual(py_res["exit_code"], 0)
            print("  [OK] Python container execution succeeded.")

            # 2. JavaScript execution
            js_code = "console.log([10, 20, 30].reduce((a, b) => a + b, 0));"
            js_res = run_code(js_code, language="javascript")
            if js_res["success"]:
                self.assertEqual(js_res["stdout"].strip(), "60")
                self.assertEqual(js_res["exit_code"], 0)
                print("  [OK] JavaScript (Node.js) container execution succeeded.")
            else:
                self.assertIn("[sandbox error]", js_res["stderr"])
                print(f"  [Note] JavaScript image not ready yet: {js_res['stderr'][:120]}...")

            # 3. C execution
            c_code = """
            #include <stdio.h>
            int main() {
                int total = 0;
                for(int i = 1; i <= 4; i++) { total += i; }
                printf("%d\\n", total);
                return 0;
            }
            """
            c_res = run_code(c_code, language="c")
            if c_res["success"]:
                self.assertEqual(c_res["stdout"].strip(), "10")
                self.assertEqual(c_res["exit_code"], 0)
                print("  [OK] C (gcc) container compilation and execution succeeded.")
            else:
                self.assertIn("[sandbox error]", c_res["stderr"])
                print(f"  [Note] C image not ready yet: {c_res['stderr'][:120]}...")

            # 4. Network isolation test (--network none)
            net_code = """
import urllib.request
try:
    urllib.request.urlopen("http://1.1.1.1", timeout=2)
    print("NET_SUCCESS")
except Exception as e:
    print(f"NET_BLOCKED: {type(e).__name__}")
"""
            net_res = run_code(net_code, language="python")
            self.assertTrue(net_res["success"])
            self.assertIn("NET_BLOCKED", net_res["stdout"])
            self.assertNotIn("NET_SUCCESS", net_res["stdout"])
            print("  [OK] Network isolation verified (--network none prevented connection).")

        else:
            print(f"\n[Test] Docker state is '{state}'. Verifying strict fail-closed behavior...")
            res = run_code("print('hello')", language="python")
            self.assertFalse(res["success"])
            self.assertEqual(res["exit_code"], -1)
            self.assertIn("[sandbox error]", res["stderr"])


if __name__ == "__main__":
    unittest.main()
