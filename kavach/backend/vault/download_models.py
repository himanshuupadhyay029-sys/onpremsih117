"""download_models.py — Sovereign model pre-fetcher for new PC setup / air-gapped prep.

Pre-downloads and caches the default Neural Cross-Encoder Reranker
(ms-marco-MiniLM-L-6-v2 or ms-marco-MiniLM-L-12-v2) into the local project
directory so the system operates completely offline without internet access.

Usage:
    python -m backend.vault.download_models
    python -m backend.vault.download_models --model cross-encoder/ms-marco-MiniLM-L-12-v2
"""

import argparse
import sys
from pathlib import Path

from backend import config


def main():
    parser = argparse.ArgumentParser(description="Pre-download KAVACH reranker models.")
    parser.add_argument(
        "--model",
        type=str,
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        help="Model ID to pre-download (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2 or cross-encoder/ms-marco-MiniLM-L-12-v2)",
    )
    parser.add_argument(
        "--save-local",
        action="store_true",
        help="Save model files directly to kavach/models/reranker/ for portable air-gapped transport",
    )
    args = parser.parse_args()

    print(f"[*] Pre-downloading Cross-Encoder model: '{args.model}'...")

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print("[!] 'sentence-transformers' not installed. Please run: pip install -r requirements.txt")
        sys.exit(1)

    try:
        model = CrossEncoder(args.model)
        print(f"[+] Successfully cached '{args.model}' to HuggingFace local cache.")

        if args.save_local:
            target_dir = config.PROJECT_ROOT / "models" / "reranker"
            target_dir.mkdir(parents=True, exist_ok=True)
            model.save(str(target_dir))
            print(f"[+] Saved standalone portable model weights to: {target_dir}")

        print("[OK] Reranker model is ready for sovereign on-premises execution.")
    except Exception as exc:
        print(f"[!] Failed to download model: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
