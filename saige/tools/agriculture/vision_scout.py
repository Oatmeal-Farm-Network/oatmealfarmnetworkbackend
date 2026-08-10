# --- tools/agriculture/vision_scout.py ---
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("farm_advisory.vision_scout")


def scout_image_b64(
    image_b64: str,
    *,
    crop_hint: str = "",
    people_id: str = "",
    business_id: str = "",
) -> Dict[str, Any]:
    """
    Run a lightweight multimodal scout using the shared Gemini client.
    Returns a structured packet suitable for monitoring / crop specialists.
    """
    raw_b64 = image_b64
    if "," in raw_b64[:80]:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        from llm import get_llm_farm
        from langchain_core.messages import HumanMessage

        llm = get_llm_farm()
        prompt = (
            "You are Saige's crop vision scout. Inspect this farm/field photo. "
            "Identify likely crop, visible stress (pest/disease/nutrient/water), "
            "and 2-4 concrete next actions. Be practical. "
            f"Context crop hint: {crop_hint or 'unknown'}. "
            "Respond in plain text under 180 words."
        )
        msg = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": f"data:image/jpeg;base64,{raw_b64}",
                },
            ]
        )
        resp = llm.invoke([msg])
        text = getattr(resp, "content", None) or str(resp)
        return {
            "source": "vision_scout",
            "text": text,
            "recommendations": [],
            "people_id": people_id,
            "business_id": business_id,
        }
    except Exception as e:
        logger.exception("[vision_scout] failed: %s", e)
        return {
            "source": "vision_scout",
            "text": f"Vision scout unavailable: {e}",
            "recommendations": [],
            "error": str(e),
        }


def scout_from_bytes(data: bytes, **kwargs) -> Dict[str, Any]:
    return scout_image_b64(base64.b64encode(data).decode("ascii"), **kwargs)
