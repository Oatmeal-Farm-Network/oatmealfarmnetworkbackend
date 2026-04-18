"""
Pest / disease detection from crop photos.

Uses the existing Gemini vision LLM (no new API key, no new dependency)
to identify pests, diseases, and nutrient deficiencies from an uploaded
photograph. Returns a structured result with a confidence bucket and
recommended next steps.

Deliberately conservative: if the model isn't sure, it says so and
suggests human confirmation routes (local extension office, plant
clinic, iNaturalist ID help).
"""
from __future__ import annotations

import base64
import json
import re
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage

try:
    from llm import llm as _shared_llm
except Exception as _e:
    _shared_llm = None
    print(f"[pest_detection] shared LLM unavailable: {_e}")


VISION_PROMPT = """You are an agronomy vision assistant. The user has uploaded a photo
of a crop/plant. Identify:
1. The most likely pest, disease, or nutrient deficiency visible (or "healthy" if none).
2. Your confidence level: "high", "medium", "low", or "uncertain".
3. The specific visible symptoms you used for the diagnosis.
4. 2-4 concrete next-step actions the farmer should take.
5. Any common look-alikes worth ruling out.

Respond as STRICT JSON with exactly these keys:
{
  "diagnosis": "string — the suspected pest/disease/deficiency name",
  "confidence": "high | medium | low | uncertain",
  "category": "pest | disease | deficiency | abiotic | healthy | unknown",
  "symptoms_observed": ["string", ...],
  "recommended_actions": ["string", ...],
  "look_alikes": ["string", ...],
  "crop_identified": "string — your best guess at what crop this is, or 'unknown'",
  "notes": "string — any caveats"
}
Do NOT include markdown, code fences, or prose outside the JSON. If the image
is not a plant/crop, respond with diagnosis="not_a_plant", confidence="high"."""


def _normalize_image(image_b64: str) -> tuple[str, str]:
    """Strip data-URL prefix if present; return (base64_payload, mime_type)."""
    mime = "image/jpeg"
    s = image_b64.strip()
    m = re.match(r"^data:(image/[^;]+);base64,(.*)$", s, re.DOTALL)
    if m:
        mime = m.group(1)
        s = m.group(2)
    return s, mime


def _parse_json(text: str) -> Optional[Dict]:
    """Best-effort JSON extraction from an LLM response."""
    if not text:
        return None
    # strip code fences
    text = re.sub(r"^\s*```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    # find the first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def detect_from_base64(image_b64: str, extra_notes: str = "") -> Dict:
    """Send base64 image to vision LLM and return structured detection."""
    if _shared_llm is None:
        return {
            "status": "unavailable",
            "message": "Vision LLM not configured on this server.",
        }

    payload, mime = _normalize_image(image_b64)
    if not payload:
        return {"status": "error", "message": "No image data provided."}

    prompt_text = VISION_PROMPT
    if extra_notes:
        prompt_text += f"\n\nFarmer's note: {extra_notes[:500]}"

    message = HumanMessage(content=[
        {"type": "text", "text": prompt_text},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{payload}"},
        },
    ])

    try:
        response = _shared_llm.invoke([message])
        raw = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return {"status": "error", "message": f"Vision model error: {e}"}

    parsed = _parse_json(raw)
    if not parsed:
        return {
            "status": "ok",
            "diagnosis": "unknown",
            "confidence": "uncertain",
            "category": "unknown",
            "symptoms_observed": [],
            "recommended_actions": [
                "Retake the photo in good daylight and upload again.",
                "Post the photo to a local extension office or iNaturalist for human ID.",
            ],
            "look_alikes": [],
            "crop_identified": "unknown",
            "notes": "Model response could not be parsed as JSON.",
            "raw": raw[:500],
        }

    parsed.setdefault("confidence", "uncertain")
    parsed.setdefault("category", "unknown")
    parsed.setdefault("symptoms_observed", [])
    parsed.setdefault("recommended_actions", [])
    parsed.setdefault("look_alikes", [])
    parsed.setdefault("crop_identified", "unknown")
    parsed.setdefault("notes", "")
    parsed["status"] = "ok"
    return parsed


def format_for_llm(image_b64: str, notes: str = "") -> str:
    """Return a human-readable summary of a detection (used by the Saige tool)."""
    result = detect_from_base64(image_b64, notes)
    if result.get("status") != "ok":
        return f"Pest detection unavailable: {result.get('message', 'unknown error')}"
    lines = [f"Diagnosis: {result.get('diagnosis')} ({result.get('category', 'unknown')}, "
             f"confidence: {result.get('confidence', 'uncertain')})"]
    if result.get("crop_identified") and result["crop_identified"] != "unknown":
        lines.append(f"Crop identified: {result['crop_identified']}")
    if result.get("symptoms_observed"):
        lines.append("Symptoms observed:")
        for s in result["symptoms_observed"]:
            lines.append(f"  - {s}")
    if result.get("recommended_actions"):
        lines.append("Recommended actions:")
        for s in result["recommended_actions"]:
            lines.append(f"  - {s}")
    if result.get("look_alikes"):
        lines.append(f"Rule out: {', '.join(result['look_alikes'])}")
    if result.get("notes"):
        lines.append(f"Notes: {result['notes']}")
    return "\n".join(lines)


# No @tool wrapper: image data is too large to pass through the ReAct
# loop as a function argument. Saige invokes this via REST endpoint and
# the result is fed back as conversation context instead.
