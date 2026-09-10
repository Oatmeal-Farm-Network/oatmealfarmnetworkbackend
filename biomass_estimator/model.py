"""Map dual-stream features → 5 biomass components + interval confidence (CSIRO-style)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

# Interval borders from 1st-place writeup (grams dry matter per sample)
BORDERS_DICT = {
    "Dry_Clover_g": [1.6e-05, 3.9, 10.5353, 20.6523, 37.5911, 71.7865],
    "Dry_Dead_g": [1.6e-05, 6.1407, 13.1192, 23.277, 38.8581, 83.8407],
    "Dry_Green_g": [1.6e-05, 13.4232, 27.0782, 45.5236, 79.834, 157.9836],
    "Dry_Total_g": [1.6e-05, 23.4907, 41.1, 61.1, 96.8288, 185.7],
    "GDM_g": [1.6e-05, 16.5143, 30.507, 49.5585, 81.0, 157.9836],
}

COMPONENT_KEYS = ("Dry_Green_g", "Dry_Dead_g", "Dry_Clover_g", "GDM_g", "Dry_Total_g")


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _canopy_scores(fused: Dict[str, float]) -> Dict[str, float]:
    """Derive 0–1 intensity scores for green / dead / clover-like fractions."""
    green = float(np.clip(fused.get("green_frac", 0.0), 0.0, 1.0))
    dead = float(np.clip(fused.get("dead_frac", 0.0), 0.0, 1.0))
    soil = float(np.clip(fused.get("soil_frac", 0.0), 0.0, 1.0))
    exg = float(fused.get("exg_mean", 0.0))
    vari = float(fused.get("vari_mean", 0.0))
    # ExG typically ~[-0.2, 0.6] for pasture; map to [0,1]
    exg_n = float(np.clip((exg + 0.05) / 0.55, 0.0, 1.0))
    vari_n = float(np.clip((vari + 0.2) / 0.7, 0.0, 1.0))

    green_score = float(np.clip(0.55 * green + 0.25 * exg_n + 0.20 * vari_n, 0.0, 1.0))
    dead_score = float(np.clip(0.70 * dead + 0.20 * (1.0 - green) * 0.5 + 0.10 * soil, 0.0, 1.0))
    # Clover proxy: bright green with moderate variability (legume patches)
    clover_score = float(np.clip(green_score * (0.35 + 0.4 * fused.get("brightness_std", 0.1) * 4), 0.0, 0.85))
    # Ensure green/dead/clover don't all dominate soil
    cover = float(np.clip(1.0 - 0.6 * soil, 0.15, 1.0))
    return {
        "green_score": green_score * cover,
        "dead_score": dead_score * cover,
        "clover_score": clover_score * cover,
        "cover": cover,
        "exg_n": exg_n,
        "vari_n": vari_n,
    }


def _score_to_grams(score: float, borders: list) -> float:
    """
    Map 0–1 score onto competition gram range using interval midpoints.
    borders has 6 edges → 7 intervals; we treat score as position along the range.
    """
    # Effective max slightly above last border (rare high biomass)
    lo, hi = borders[0], borders[-1] * 1.15
    # Soft curve: more mass near mid canopy
    t = float(np.clip(score, 0.0, 1.0))
    t = t ** 0.85
    return max(0.0, _lerp(lo, hi, t))


def interval_index(value: float, borders: list) -> int:
    """Return bin index 0..6 for value given ascending borders (6 edges)."""
    for i, edge in enumerate(borders):
        if value < edge:
            return max(0, i)
    return len(borders)  # top bin


def interval_confidence(value: float, borders: list) -> float:
    """
    Higher confidence when value sits near an interval center, lower near edges.
    Also prefer mid-range over extreme zeros / saturation.
    """
    idx = interval_index(value, borders)
    edges = [0.0] + list(borders) + [borders[-1] * 1.3]
    # clamp idx
    idx = min(idx, len(edges) - 2)
    lo, hi = edges[idx], edges[idx + 1]
    mid = (lo + hi) / 2.0
    half = max((hi - lo) / 2.0, 1e-6)
    near_center = 1.0 - min(1.0, abs(value - mid) / half)
    # Penalize near-zero or very high
    span = borders[-1]
    magnitude = float(np.clip(value / max(span * 0.5, 1e-6), 0.15, 1.0))
    if value <= borders[0] * 10:
        magnitude *= 0.5
    return float(np.clip(0.35 + 0.45 * near_center + 0.20 * magnitude, 0.15, 0.92))


def predict_components(feature_bundle: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Independent regression-style mapping (no hard mass constraints during 'train'),
    matching the writeup philosophy; physics applied later in postprocess.
    """
    fused = feature_bundle["fused"]
    scores = _canopy_scores(fused)

    green = _score_to_grams(scores["green_score"], BORDERS_DICT["Dry_Green_g"])
    dead = _score_to_grams(scores["dead_score"], BORDERS_DICT["Dry_Dead_g"])
    clover = _score_to_grams(scores["clover_score"], BORDERS_DICT["Dry_Clover_g"])
    # Independent GDM / Total heads (will be reconciled in postprocess)
    gdm = _score_to_grams(
        float(np.clip(0.7 * scores["green_score"] + 0.3 * scores["clover_score"], 0, 1)),
        BORDERS_DICT["GDM_g"],
    )
    total = _score_to_grams(
        float(np.clip(0.55 * scores["green_score"] + 0.25 * scores["dead_score"] + 0.20 * scores["clover_score"], 0, 1)),
        BORDERS_DICT["Dry_Total_g"],
    )

    # Mild DINO modulation if present
    dino_norm = feature_bundle.get("dino_norm")
    if dino_norm is not None and dino_norm > 0:
        # Normalize typical ViT-S L2 norms (~10–40) into a small gain
        gain = float(np.clip(dino_norm / 25.0, 0.85, 1.15))
        green *= gain
        clover *= gain
        gdm *= gain
        total *= gain

    components = {
        "Dry_Green_g": round(green, 4),
        "Dry_Dead_g": round(dead, 4),
        "Dry_Clover_g": round(clover, 4),
        "GDM_g": round(gdm, 4),
        "Dry_Total_g": round(total, 4),
    }

    intervals = {
        k: {
            "bin": interval_index(components[k], BORDERS_DICT[k]),
            "confidence": round(interval_confidence(components[k], BORDERS_DICT[k]), 3),
        }
        for k in COMPONENT_KEYS
    }

    meta = {"scores": scores, "intervals": intervals}
    return components, meta
