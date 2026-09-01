"""test_phase7.py — Comprehensive verification for Phase 7 (OCR & Vision)."""

import json
from pathlib import Path
import sys
import docx

ROOT_DIR = Path(__file__).resolve().parent
KAVACH_DIR = ROOT_DIR / "kavach" if (ROOT_DIR / "kavach").exists() else ROOT_DIR

for p in [str(ROOT_DIR), str(KAVACH_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import config
from backend.audit.logbook import read_events
from backend.brain.agent import run_agent
from backend.tools.ocr import extract_text, run_ocr
from backend.tools.vision import describe_image
from backend.vault.ingest import ingest_document
from scripts.generate_synthetic_scans import (
    create_clean_inspection_note,
    create_degraded_inspection_note,
    create_pressure_gauge_diagram,
)


def inspect_docx(file_path: Path):
    print(f"\n--- Content of {file_path.name} ---")
    doc = docx.Document(str(file_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for i, p in enumerate(paragraphs, 1):
        print(f"  [{i}] {p}")


def print_audit_trail(task_id: str, title: str):
    print(f"\n==================================================")
    print(f"AUDIT TRAIL: {title} (Task ID: {task_id})")
    print(f"==================================================")
    events = read_events(task_id=task_id)
    for i, ev in enumerate(events, 1):
        print(f"[{i}] {ev.get('timestamp')} | Event: {ev.get('event_type').upper()} | Actor: {ev.get('actor')} | External: {ev.get('external_calls')}")
        print(f"    Summary: {ev.get('summary')}")


def main():
    print("=== KAVACH Phase 7: OCR & Vision Verification ===")

    # ----------------------------------------------------
    # 1. Generate synthetic test data
    # ----------------------------------------------------
    print("\n--- 1. Generating Synthetic Test Images ---")
    clean_img = create_clean_inspection_note()
    scanned_img = create_degraded_inspection_note()
    gauge_img = create_pressure_gauge_diagram()
    print("Generated test images:")
    print(f"  - Clean Scan  : {clean_img.name} ({clean_img.stat().st_size} bytes)")
    print(f"  - Degraded    : {scanned_img.name} ({scanned_img.stat().st_size} bytes)")
    print(f"  - Dial Diagram: {gauge_img.name} ({gauge_img.stat().st_size} bytes)")

    # ----------------------------------------------------
    # 2. OCR on Clean Synthetic Image
    # ----------------------------------------------------
    print("\n--- 2. Running OCR on Clean Synthetic Image ---")
    clean_ocr = extract_text(clean_img)
    print(f"Engine Used     : {clean_ocr['engine']}")
    print(f"Confidence Score: {clean_ocr['confidence'] * 100:.1f}%")
    print(f"Low Confidence? : {clean_ocr['low_confidence']}")
    print("Extracted Text:")
    for line in clean_ocr["text"].splitlines():
        if line.strip():
            print(f"  > {line.strip()}")

    # ----------------------------------------------------
    # 3. OCR on Rotated/Degraded Synthetic Image
    # ----------------------------------------------------
    print("\n--- 3. Running OCR on Degraded Synthetic Image (Rotated/Blurred) ---")
    degraded_ocr = extract_text(scanned_img)
    print(f"Engine Used     : {degraded_ocr['engine']}")
    print(f"Confidence Score: {degraded_ocr['confidence'] * 100:.1f}%")
    print(f"Low Confidence? : {degraded_ocr['low_confidence']}")
    print("Extracted Text:")
    for line in degraded_ocr["text"].splitlines():
        if line.strip():
            print(f"  > {line.strip()}")

    # ----------------------------------------------------
    # 4. Ingest Scanned Document into Knowledge Vault & Run Agent
    # ----------------------------------------------------
    print("\n--- 4. Ingesting Scanned Image into Vault & Testing Grounded Search + Writer ---")
    ingest_res = ingest_document(clean_img)
    print(f"Vault Ingestion Result: {ingest_res}")

    task_query = "Search SOPs and inspection notes for the operating pressure reading of VALVE-402-ALPHA and draft an inspection report document."
    print(f"Running Agent Task: {task_query}")
    agent_res = run_agent(task_query)
    print(f"Agent Task ID : {agent_res['task_id']}")
    print(f"Agent Status  : {agent_res['status']}")
    print(f"Agent Result  :\n{agent_res['result']}")
    print("Sources Cited:")
    for s in agent_res.get("sources", []):
        fn = s.get("filename") if isinstance(s, dict) else str(s)
        print(f"  - Source: {fn}")

    gen_files = agent_res.get("generated_files", [])
    if gen_files:
        for gf in gen_files:
            if gf.get("file_path"):
                inspect_docx(Path(gf["file_path"]))

    # ----------------------------------------------------
    # 5. Multimodal Vision Analysis on Technical Diagram
    # ----------------------------------------------------
    print("\n--- 5. Multimodal Vision Analysis (qwen2.5vl:3b) on Gauge Diagram ---")
    vision_res = describe_image(
        gauge_img,
        question="What is this gauge measuring and approximately what reading is the red needle pointing to?",
    )
    print(f"Vision Model Used : {vision_res['model']}")
    print(f"Vision Analysis Response:\n{vision_res['description']}")

    # ----------------------------------------------------
    # 6. Audit Trail Verification
    # ----------------------------------------------------
    print_audit_trail(agent_res["task_id"], "OCR Vault Ingest, Search & Write Task")

    print("\n=== Phase 7 Verification Complete! ===")


if __name__ == "__main__":
    main()
