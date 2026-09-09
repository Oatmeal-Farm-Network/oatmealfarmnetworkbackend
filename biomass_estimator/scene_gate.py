"""Scene checks for biomass uploads — prefer accept + lower confidence over reject."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np


def assess_vegetation_scene(
    full_rgb: np.ndarray,
    full_features: Dict[str, float],
) -> Tuple[bool, str]:
    """
    Returns (ok, reason).

    Accepts top-down, angled, side, and phone field photos.
    Only rejects nearly blank / non-image-like frames with essentially no vegetation signal.
    """
    green = float(full_features.get("green_frac", 0.0))
    exg = float(full_features.get("exg_mean", 0.0))
    dead = float(full_features.get("dead_frac", 0.0))
    brightness = float(full_features.get("brightness_mean", 0.5))
    veg_cover = green + 0.35 * dead

    # Completely black / white / empty frames
    if brightness < 0.04 or brightness > 0.97:
        if veg_cover < 0.02:
            return (
                False,
                "This image looks blank or over/underexposed. "
                "Upload a photo that shows plants or pasture.",
            )

    # Essentially no plant signal at all
    if veg_cover < 0.02 and exg < 0.0:
        return (
            False,
            "No vegetation detected in this photo. "
            "Upload an image that includes grass, crops, or plants.",
        )

    return True, ""


def scene_confidence_scale(full_features: Dict[str, float]) -> float:
    """
    Soft quality factor for atypical / sparse scenes (does not reject).
    1.0 = good canopy fill; lower for sparse / mixed photos.
    """
    green = float(full_features.get("green_frac", 0.0))
    dead = float(full_features.get("dead_frac", 0.0))
    veg = green + 0.35 * dead
    if veg >= 0.35:
        return 1.0
    if veg >= 0.15:
        return 0.85
    if veg >= 0.05:
        return 0.7
    return 0.55


def rejection_payload(reason: str, field_id: int | None = None) -> Dict[str, Any]:
    return {
        "rejected": True,
        "reject_reason": reason,
        "biomass_kg_per_ha": None,
        "confidence": 0.0,
        "model_version": "pasture-dinov2-v2",
        "features": {
            "rejected": True,
            "reject_reason": reason,
            "field_id": field_id,
        },
    }
