"""generate_synthetic_scans.py — Generates synthetic test images for Phase 7 OCR & Vision verification."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "testdata" / "synthetic_scans"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_clean_inspection_note() -> Path:
    """Generates a clean synthetic inspection document image."""
    img = Image.new("RGB", (800, 500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw border
    draw.rectangle([(20, 20), (780, 480)], outline=(180, 180, 180), width=2)

    lines = [
        ("REFINERY UNIT 4 - PIPING & VALVE INSPECTION NOTE", 40, True),
        ("----------------------------------------------------------------", 70, False),
        ("Inspection Date: 2026-08-24   |   Inspector ID: ENG-9412", 100, False),
        ("Equipment Tag: VALVE-402-ALPHA", 140, True),
        ("Location: Catalytic Cracking Unit - Header Line 3", 180, False),
        ("Operating Pressure Reading: 142.5 PSI (Safe Limit: 160.0 PSI)", 220, True),
        ("Surface Temperature: 87.4 C", 260, False),
        ("Status: NORMAL OPERATION - No corrosion or seal leakage observed.", 300, True),
        ("Next Scheduled Maintenance: 2026-11-15", 340, False),
        ("Authorized Signature: E. Vance (Lead Safety Engineer)", 390, False),
    ]

    for text, y, bold in lines:
        draw.text((50, y), text, fill=(20, 20, 20))

    out_path = OUTPUT_DIR / "inspection_note_clean.png"
    img.save(str(out_path))
    print(f"Created clean synthetic scan: {out_path}")
    return out_path


def create_degraded_inspection_note() -> Path:
    """Generates a rotated/blurred synthetic scan simulating a low-quality scanner."""
    # Render base image larger for rotation quality
    base = Image.new("RGB", (900, 600), color=(248, 246, 240))
    draw = ImageDraw.Draw(base)

    draw.rectangle([(25, 25), (875, 575)], outline=(200, 195, 185), width=2)

    lines = [
        ("REFINERY UNIT 4 - PIPING & VALVE INSPECTION NOTE", 50),
        ("----------------------------------------------------------------", 80),
        ("Inspection Date: 2026-08-24   |   Inspector ID: ENG-9412", 110),
        ("Equipment Tag: VALVE-402-ALPHA", 150),
        ("Operating Pressure Reading: 142.5 PSI (Safe Limit: 160.0 PSI)", 190),
        ("Status: NORMAL OPERATION - No corrosion or seal leakage observed.", 230),
        ("Next Scheduled Maintenance: 2026-11-15", 270),
    ]

    for text, y in lines:
        draw.text((60, y), text, fill=(40, 35, 30))

    # Apply slight rotation (~6.5 degrees)
    rotated = base.rotate(6.5, resample=Image.BICUBIC, expand=True, fillcolor=(235, 230, 220))
    # Apply slight blur to simulate scan degradation
    blurred = rotated.filter(ImageFilter.GaussianBlur(radius=0.7))

    out_path = OUTPUT_DIR / "inspection_note_scanned.png"
    blurred.save(str(out_path))
    print(f"Created degraded/scanned synthetic scan: {out_path}")
    return out_path


def create_pressure_gauge_diagram() -> Path:
    """Generates a synthetic technical diagram of a pressure gauge dial for vision testing."""
    img = Image.new("RGB", (600, 600), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)

    # Dial circle
    draw.ellipse([(100, 100), (500, 500)], fill=(240, 245, 250), outline=(50, 60, 80), width=4)
    # Inner rim
    draw.ellipse([(120, 120), (480, 480)], outline=(150, 160, 180), width=2)

    # Dial center
    draw.ellipse([(285, 285), (315, 315)], fill=(40, 40, 40))

    # Dial labels & numbers
    draw.text((230, 150), "100", fill=(30, 30, 30))
    draw.text((380, 200), "150", fill=(30, 30, 30))
    draw.text((410, 300), "200", fill=(30, 30, 30))
    draw.text((160, 200), "50", fill=(30, 30, 30))
    draw.text((150, 300), "0", fill=(30, 30, 30))

    draw.text((220, 380), "STEAM PRESSURE", fill=(20, 30, 50))
    draw.text((270, 410), "PSI", fill=(80, 80, 80))

    # Needle pointing towards ~142 PSI (upper right quadrant)
    draw.line([(300, 300), (375, 215)], fill=(200, 20, 20), width=5)

    out_path = OUTPUT_DIR / "pressure_gauge_diagram.png"
    img.save(str(out_path))
    print(f"Created synthetic pressure gauge diagram: {out_path}")
    return out_path


if __name__ == "__main__":
    create_clean_inspection_note()
    create_degraded_inspection_note()
    create_pressure_gauge_diagram()
    print("All synthetic test images generated in testdata/synthetic_scans/")
