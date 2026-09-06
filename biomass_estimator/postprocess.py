"""CSIRO writeup post-processing + grams → kg DM/ha."""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple


def apply_writeup_postprocess(components: Dict[str, float]) -> Dict[str, float]:
    """
    Post-processing from 1st-place notes:
    - scale Clover ×0.8
    - adjust Dead ×1.1 if >20, ×0.9 if <10
    Then physics post-hoc: GDM = Green + Clover, Total = GDM + Dead
    """
    green = max(0.0, float(components.get("Dry_Green_g", 0.0)))
    dead = max(0.0, float(components.get("Dry_Dead_g", 0.0)))
    clover = max(0.0, float(components.get("Dry_Clover_g", 0.0)))

    clover *= 0.8
    if dead > 20:
        dead *= 1.1
    elif dead < 10:
        dead *= 0.9

    # Zero-out tiny noise (writeup-style)
    if green < 0.2:
        green = 0.0
    if dead < 0.2:
        dead = 0.0
    if clover < 0.2:
        clover = 0.0

    gdm = green + clover
    total = gdm + dead

    return {
        "Dry_Green_g": round(green, 4),
        "Dry_Dead_g": round(dead, 4),
        "Dry_Clover_g": round(clover, 4),
        "GDM_g": round(gdm, 4),
        "Dry_Total_g": round(total, 4),
    }


def grams_to_kg_per_ha(total_g: float, sample_area_m2: float | None = None) -> float:
    """
    Convert dry-matter grams in the photographed sample area to kg DM/ha.
    kg/ha = (g / 1000) / (area_m2 / 10000) = g * 10 / area_m2
    """
    if sample_area_m2 is None:
        sample_area_m2 = float(os.getenv("BIOMASS_SAMPLE_AREA_M2", "0.25"))
    sample_area_m2 = max(float(sample_area_m2), 1e-6)
    return round((float(total_g) * 10.0) / sample_area_m2, 1)


def overall_confidence(intervals: Dict[str, Any], components: Dict[str, float]) -> float:
    """Weight Total/GDM interval confidences highest (competition R² weights)."""
    weights = {
        "Dry_Total_g": 0.5,
        "GDM_g": 0.2,
        "Dry_Green_g": 0.1,
        "Dry_Dead_g": 0.1,
        "Dry_Clover_g": 0.1,
    }
    acc = 0.0
    wsum = 0.0
    for k, w in weights.items():
        conf = (intervals.get(k) or {}).get("confidence")
        if conf is None:
            continue
        acc += w * float(conf)
        wsum += w
    base = acc / wsum if wsum else 0.4
    # Slight boost when total biomass is in a plausible mid range
    total = float(components.get("Dry_Total_g", 0.0))
    if 15 <= total <= 120:
        base = min(0.95, base + 0.05)
    return round(float(base), 3)


def finalize(
    raw_components: Dict[str, float],
    intervals: Dict[str, Any],
    sample_area_m2: float | None = None,
) -> Tuple[Dict[str, float], float, float]:
    """Returns (components, biomass_kg_per_ha, confidence)."""
    components = apply_writeup_postprocess(raw_components)
    # Recompute intervals conceptually already done; confidence from pre-post intervals is fine
    conf = overall_confidence(intervals, components)
    kg_ha = grams_to_kg_per_ha(components["Dry_Total_g"], sample_area_m2)
    return components, kg_ha, conf
