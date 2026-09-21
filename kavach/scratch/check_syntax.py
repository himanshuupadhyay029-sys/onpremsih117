import py_compile
from pathlib import Path

backend_dir = Path("backend")
errors = []

for py_file in backend_dir.rglob("*.py"):
    try:
        py_compile.compile(str(py_file), doraise=True)
    except Exception as e:
        errors.append((str(py_file), str(e)))

print(f"Checked {len(list(backend_dir.rglob('*.py')))} files.")
if errors:
    print("Errors found:")
    for f, err in errors:
        print(f"{f}: {err}")
else:
    print("All backend Python files compiled cleanly with 0 syntax errors!")
