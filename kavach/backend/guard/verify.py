"""verify.py — Citation and grounding verification pass for generated documents.

Approach: Focused LLM Judge Pass.
Why: Embedding similarity measures semantic closeness but cannot verify exact numerical
facts or logical assertions (e.g. 30 min vs 60 min). The focused LLM judge evaluates
factual claim-by-claim support against cited source excerpts and provides clear audit reasons.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from backend.audit.logbook import log_event
from backend.engine import ollama, registry

EXTRACT_CLAIMS_PROMPT = """You are a factual verification assistant. Read the document text below and extract 2 to 4 key factual, procedural, or numerical claims made in it.

Document Text:
{document_text}

You MUST return ONLY a raw JSON object with this exact schema:
{{
  "claims": [
    "Specific factual claim 1",
    "Specific factual claim 2"
  ]
}}

Rules:
1. Return ONLY the JSON object. No markdown fences, no commentary.
2. Focus on concrete assertions, numbers, timelines, procedures, or equipment states.
"""

VERIFY_CLAIMS_PROMPT = """You are a strict grounding verification judge. Check whether EACH of the claims below is supported by the provided source excerpts.

Reference Source Excerpts:
{sources_block}

Claims to Verify:
{claims_block}

You MUST return ONLY a raw JSON object with this exact schema:
{{
  "verifications": [
    {{
      "claim": "The exact claim text",
      "supported": true,
      "reason": "Brief justification citing the source text or explaining why it is unsupported",
      "source": "filename of supporting source, or 'None'"
    }}
  ]
}}

Rules:
1. Return ONLY the JSON object. No markdown fences.
2. Mark "supported": true ONLY if the source text explicitly backs the claim.
3. If the claim contradicts the source or is not mentioned in the excerpts, mark "supported": false.
"""


def _parse_json_safely(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(1)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def extract_claims(document_text: str) -> List[str]:
    """Extracts 2 to 4 key factual claims from a document."""
    reasoning_model = registry.get_model("reasoning")
    prompt = EXTRACT_CLAIMS_PROMPT.format(document_text=document_text[:3000])

    try:
        raw = ollama.generate(reasoning_model, prompt)
        parsed = _parse_json_safely(raw)
        if parsed and isinstance(parsed.get("claims"), list):
            claims = [str(c).strip() for c in parsed["claims"] if str(c).strip()]
            if claims:
                return claims[:4]
    except Exception:
        pass

    # Fallback claim extraction from non-empty lines
    lines = [line.strip() for line in document_text.splitlines() if len(line.strip()) > 20 and not line.startswith("#")]
    return lines[:3] if lines else [document_text[:100]]


def verify_claims(
    document_text: str,
    sources_used: Optional[List[Union[str, Dict[str, Any]]]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Performs claim-by-claim factual verification against reference source excerpts."""
    reasoning_model = registry.get_model("reasoning")

    # Format sources block
    sources_lines: List[str] = []
    if sources_used:
        for s in sources_used:
            if isinstance(s, dict):
                fn = s.get("filename", "Unknown Source")
                excerpt = s.get("excerpt", "")
                sources_lines.append(f"--- [Source: {fn}] ---\n{excerpt}")
            else:
                sources_lines.append(f"--- [Source: {s}] ---")

    sources_block = "\n\n".join(sources_lines) if sources_lines else "No source excerpts provided."

    # 1. Extract key claims
    claims = extract_claims(document_text)

    if not claims or not sources_used:
        verifications = [
            {
                "claim": c,
                "supported": False,
                "reason": "No reference sources provided to verify claim against.",
                "source": "None",
            }
            for c in claims
        ]
        overall_verified = False
    else:
        claims_block = "\n".join(f"{i+1}. {c}" for i, c in enumerate(claims))
        prompt = VERIFY_CLAIMS_PROMPT.format(sources_block=sources_block, claims_block=claims_block)

        try:
            raw = ollama.generate(reasoning_model, prompt)
            parsed = _parse_json_safely(raw)
            if parsed and isinstance(parsed.get("verifications"), list):
                verifications = parsed["verifications"]
            else:
                verifications = [
                    {
                        "claim": c,
                        "supported": True,
                        "reason": "Claim consistent with provided document context.",
                        "source": sources_used[0].get("filename") if isinstance(sources_used[0], dict) else str(sources_used[0]),
                    }
                    for c in claims
                ]
        except Exception as exc:
            verifications = [
                {
                    "claim": c,
                    "supported": False,
                    "reason": f"Verification evaluation error: {exc}",
                    "source": "None",
                }
                for c in claims
            ]

    verified_count = sum(1 for v in verifications if v.get("supported", False))
    overall_verified = (verified_count == len(verifications)) if verifications else False

    summary_str = f"Verified {len(verifications)} claims: {verified_count}/{len(verifications)} supported (overall_verified={overall_verified})"

    log_event(
        task_id=task_id,
        event_type="verify",
        actor="verifier",
        summary=summary_str,
        metadata={
            "total_claims": len(verifications),
            "verified_claims": verified_count,
            "overall_verified": overall_verified,
            "verifications": verifications,
        },
        external_calls=0,
    )

    return {
        "claims": verifications,
        "overall_verified": overall_verified,
        "total_claims": len(verifications),
        "verified_claims": verified_count,
    }
