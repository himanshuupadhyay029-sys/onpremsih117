"""ocr.py — Optical Character Recognition tool supporting dual engines (PaddleOCR & Tesseract).

Priority:
1. Pure PDF text layer extraction (via pypdf) if real embedded text exists (fast, exact).
2. PaddleOCR if installed (Primary engine).
3. Tesseract (via pytesseract) if installed (Fallback engine).

Every OCR run records per-block / average confidence scores, flags low_confidence (< 65%),
and logs an append-only audit event with external_calls=0.
"""

import os
# Disable oneDNN / PIR issues on Windows for CPU execution in Paddle
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.audit.logbook import log_event

# Threshold below which OCR is flagged for human review
LOW_CONFIDENCE_THRESHOLD = 0.65

# Lazy-loaded PaddleOCR instance cache
_PADDLE_OCR_INSTANCE = None


def _get_paddle_ocr():
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is None:
        try:
            import paddle
            try:
                paddle.set_flags({"FLAGS_use_mkldnn": 0, "FLAGS_enable_pir_api": 0})
            except Exception:
                pass

            from paddleocr import PaddleOCR
            _PADDLE_OCR_INSTANCE = PaddleOCR(lang="en")
        except Exception as exc:
            _PADDLE_OCR_INSTANCE = False
    return _PADDLE_OCR_INSTANCE if _PADDLE_OCR_INSTANCE is not False else None


def _parse_paddle_output(results: Any) -> Tuple[str, float, List[Dict[str, Any]]]:
    """Robustly parses results from both PaddleOCR v2 (nested list) and PaddleOCR v3/PaddleX (dicts)."""
    lines: List[str] = []
    confidences: List[float] = []
    word_boxes: List[Dict[str, Any]] = []

    if not results:
        return "", 0.0, []

    first = results[0] if isinstance(results, list) and len(results) > 0 else results

    if isinstance(first, dict):
        if "rec_texts" in first:
            texts = first.get("rec_texts", [])
            scores = first.get("rec_scores", [])
            boxes = first.get("dt_polys", first.get("rec_boxes", []))
            for i, text in enumerate(texts):
                t = str(text).strip()
                score = float(scores[i]) if i < len(scores) else 1.0
                box = boxes[i].tolist() if i < len(boxes) and hasattr(boxes[i], "tolist") else (boxes[i] if i < len(boxes) else [])
                if t:
                    lines.append(t)
                    confidences.append(score)
                    word_boxes.append({"text": t, "confidence": score, "box": box})
        elif "ocr_result" in first:
            return _parse_paddle_output([first["ocr_result"]])
        elif "text" in first or "transcription" in first:
            for item in (results if isinstance(results, list) else [results]):
                if isinstance(item, dict):
                    t = str(item.get("text", item.get("transcription", ""))).strip()
                    score = float(item.get("score", item.get("confidence", 1.0)))
                    box = item.get("points", item.get("box", []))
                    if t:
                        lines.append(t)
                        confidences.append(score)
                        word_boxes.append({"text": t, "confidence": score, "box": box})

    elif isinstance(first, list):
        for line in first:
            if isinstance(line, list) and len(line) == 2:
                box, text_conf = line
                if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                    t = str(text_conf[0]).strip()
                    score = float(text_conf[1])
                else:
                    t = str(text_conf).strip()
                    score = 1.0
                if t:
                    lines.append(t)
                    confidences.append(score)
                    word_boxes.append({"text": t, "confidence": score, "box": box})
            elif isinstance(line, dict):
                t = str(line.get("text", line.get("transcription", ""))).strip()
                score = float(line.get("score", line.get("confidence", 1.0)))
                box = line.get("points", line.get("box", []))
                if t:
                    lines.append(t)
                    confidences.append(score)
                    word_boxes.append({"text": t, "confidence": score, "box": box})

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(lines), round(avg_conf, 4), word_boxes


def _run_paddle_ocr(img_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Runs PaddleOCR on an image file path."""
    ocr_engine = _get_paddle_ocr()
    if ocr_engine is None:
        return None

    try:
        results = ocr_engine.ocr(str(img_path))
        full_text, avg_conf, word_boxes = _parse_paddle_output(results)

        return {
            "text": full_text,
            "confidence": avg_conf,
            "engine": "paddleocr",
            "word_boxes": word_boxes,
        }
    except Exception:
        return None


def _run_tesseract_ocr(img_input) -> Optional[Dict[str, Any]]:
    """Runs Tesseract OCR via pytesseract with real per-word confidence computation."""
    try:
        import pytesseract
        from PIL import Image

        # Auto-configure tesseract_cmd on Windows if not already in PATH
        import shutil
        if not shutil.which("tesseract"):
            candidates = [
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
            ]
            for candidate in candidates:
                if candidate.exists():
                    pytesseract.pytesseract.tesseract_cmd = str(candidate)
                    break

        if isinstance(img_input, (str, Path)):
            image = Image.open(str(img_input))
        else:
            image = img_input

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        words: List[str] = []
        confidences: List[float] = []
        word_boxes: List[Dict[str, Any]] = []

        n_boxes = len(data.get("text", []))
        for i in range(n_boxes):
            word = data["text"][i].strip()
            conf_raw = data["conf"][i]
            try:
                conf = float(conf_raw)
            except (ValueError, TypeError):
                continue

            # Tesseract sets conf = -1 for non-word bounding blocks (e.g. whitespace, paragraphs)
            if word and conf >= 0:
                words.append(word)
                conf_norm = conf / 100.0  # Normalized 0.0 - 1.0
                confidences.append(conf_norm)
                word_boxes.append({
                    "text": word,
                    "confidence": round(conf_norm, 4),
                    "box": [data["left"][i], data["top"][i], data["width"][i], data["height"][i]],
                })

        if not words or not confidences:
            # Empty or unreadable image
            raw_str = pytesseract.image_to_string(image).strip()
            if not raw_str:
                full_text = ""
                avg_conf = 0.0
            else:
                full_text = raw_str
                avg_conf = 0.2
        else:
            avg_conf = sum(confidences) / len(confidences)
            full_text = " ".join(words)

        return {
            "text": full_text,
            "confidence": round(avg_conf, 4),
            "engine": "pytesseract",
            "word_boxes": word_boxes,
        }
    except Exception:
        return None


def run_ocr(image_path: Union[str, Path]) -> Dict[str, Any]:
    """Runs OCR using the best available engine (PaddleOCR -> Tesseract)."""
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # 1. Try PaddleOCR first
    result = _run_paddle_ocr(p)
    
    # 2. Fall back to Tesseract
    if result is None:
        result = _run_tesseract_ocr(p)

    # 3. If neither worked
    if result is None:
        raise RuntimeError(
            "No OCR engine available. Please install either PaddleOCR (`pip install paddlepaddle paddleocr`) "
            "or Tesseract (`pip install pytesseract` + Tesseract binary from https://github.com/UB-Mannheim/tesseract/wiki)."
        )

    confidence = result.get("confidence", 0.0)
    low_conf = confidence < LOW_CONFIDENCE_THRESHOLD

    return {
        "text": result.get("text", ""),
        "confidence": confidence,
        "engine": result.get("engine", "unknown"),
        "low_confidence": low_conf,
        "word_boxes": result.get("word_boxes", []),
        "file_path": str(p),
    }


def extract_text(file_path: Union[str, Path], task_id: Optional[str] = None) -> Dict[str, Any]:
    """Extracts text from a document (PDF text layer, scanned PDF, or image file)."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    suffix = p.suffix.lower()

    # Fast path: check for embedded text in PDFs
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            extracted_pages = [(page.extract_text() or "").strip() for page in reader.pages]
            full_pdf_text = "\n\n".join(t for t in extracted_pages if t)
            
            # If the PDF has substantial extractable text, return directly without OCR
            if len(full_pdf_text.strip()) > 30:
                log_event(
                    task_id=task_id,
                    event_type="ocr",
                    actor="pdf_parser",
                    summary=f"Extracted embedded text from PDF '{p.name}' (pages: {len(reader.pages)})",
                    metadata={"file_path": str(p), "engine": "pdf_text_layer", "confidence": 1.0},
                    external_calls=0,
                )
                return {
                    "text": full_pdf_text,
                    "confidence": 1.0,
                    "engine": "pdf_text_layer",
                    "low_confidence": False,
                    "file_path": str(p),
                }
        except Exception:
            pass

    # Image-based path or scanned PDF
    ocr_result = run_ocr(p)

    log_event(
        task_id=task_id,
        event_type="ocr",
        actor=ocr_result["engine"],
        summary=f"OCR extracted text from '{p.name}' via {ocr_result['engine']} (confidence: {ocr_result['confidence']:.2f}, low_conf={ocr_result['low_confidence']})",
        metadata={
            "file_path": str(p),
            "engine": ocr_result["engine"],
            "confidence": ocr_result["confidence"],
            "low_confidence": ocr_result["low_confidence"],
            "char_count": len(ocr_result["text"]),
        },
        external_calls=0,
    )

    return ocr_result
