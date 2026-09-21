import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.brain.agent import run_agent

task = "what is this platform I'm using, also write a python code to print 5 stars"
print("Running agent with task:", task)

try:
    res = run_agent(task, task_id="test-run-1")
    print("Agent execution succeeded!")
    print("Status:", res.get("status"))
    print("Result:", res.get("result", "")[:300])
    print("Steps completed:", len(res.get("steps", [])))
except Exception as e:
    import traceback
    print("AGENT EXECUTION FAILED:")
    traceback.print_exc()
