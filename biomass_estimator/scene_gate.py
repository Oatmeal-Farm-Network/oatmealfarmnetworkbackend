"""Reject non-vegetation / non-field scenes before inventing kg DM/ha."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from .features import stream_vegetation_features


def _blue_water_frac(rgb: np.ndarray) -> float:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (b > r * 1.15) & (b > g * 1.08) & (b > 0.22)
    return float(np.mean(mask))


def _gray_indoor_frac(rgb: np.ndarray) -> float:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    bright = (r + g + b) / 3.0
    chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    mask = (chroma < 0.06) & (bright > 0.35)
    return float(np.mean(mask))


def _tile_green_stats(rgb: np.ndarray, n: int = 4) -> Tuple[float, float, float]:
    """Mean, std, min of green_frac over an n×n grid (mixed scenes → high std / low min)."""
    h, w = rgb.shape[:2]
    vals = []
    for i in range(n):
        for j in range(n):
            tile = rgb[i * h // n : (i + 1) * h // n, j * w // n : (j + 1) * w // n]
            if tile.size == 0:
                continue
            vals.append(stream_vegetation_features(tile)["green_frac"])
    if not vals:
        return 0.0, 1.0, 0.0
    a = np.asarray(vals, dtype=np.float64)
    return float(a.mean()), float(a.std()), float(a.min())


def assess_vegetation_scene(
    full_rgb: np.ndarray,
    full_features: Dict[str, float],
) -> Tuple[bool, str]:
    """
    Returns (ok, reason). ok=False → caller should reject the upload.
    Tuned for pasture/crop canopy photos; rejects pools, gardens with mixed objects, indoor.
    """
    green = float(full_features.get("green_frac", 0.0))
    exg = float(full_features.get("exg_mean", 0.0))
    soil = float(full_features.get("soil_frac", 0.0))
    dead = float(full_features.get("dead_frac", 0.0))
    blue = _blue_water_frac(full_rgb)
    gray = _gray_indoor_frac(full_rgb)
    veg_cover = green + 0.5 * dead
    _tg_mean, tg_std, tg_min = _tile_green_stats(full_rgb, n=4)

    if blue >= 0.04:
        return (
            False,
            "This photo looks like it contains water or a pool. "
            "Upload a top-down photo of pasture or crop canopy only.",
        )
    # Mixed backyard / amenity scenes: vegetation patches + paths/structures
    if tg_std >= 0.14 and tg_min < 0.40:
        return (
            False,
            "This looks like a mixed garden or yard scene, not a pasture/crop canopy. "
            "Fill the frame with grass or crop foliage (top-down).",
        )
    if gray >= 0.45 and green < 0.15:
        return (
            False,
            "This does not look like a field photo. "
            "Upload a top-down image of pasture or crop vegetation.",
        )
    if green < 0.10 and exg < 0.02:
        return (
            False,
            "Not enough vegetation detected. "
            "Upload a close top-down photo of pasture or crop canopy.",
        )
    if soil >= 0.55 and veg_cover < 0.18:
        return (
            False,
            "Mostly bare soil / non-canopy. "
            "Upload a photo where pasture or crop foliage fills the frame.",
        )
    if veg_cover < 0.12:
        return (
            False,
            "Vegetation cover is too low for a biomass estimate. "
            "Fill the frame with pasture or crop canopy.",
        )
    return True, ""


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
