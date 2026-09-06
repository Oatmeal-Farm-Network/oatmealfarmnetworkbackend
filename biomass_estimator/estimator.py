"""Public entry: estimate_biomass_from_image(bytes) → API-shaped dict."""

from __future__ import annotations

import os
from typing import Any, Dict

from .features import extract_features, stream_vegetation_features
from .model import predict_components
from .postprocess import finalize
from .preprocess import prepare_dual_streams
from .scene_gate import assess_vegetation_scene, rejection_payload

MODEL_VERSION = "csiro-dual-v1"


def estimate_biomass_from_image(image_bytes: bytes, field_id: int | None = None) -> Dict[str, Any]:
    """
    Local multi-domain pasture/crop biomass estimate.
    Prefers calibrated DINOv2 heads when available. No paid vision / LLM APIs.
    May return rejected=True for non-vegetation scenes.
    """
    if not image_bytes:
        raise ValueError("Empty image")

    # Prefer dataset-calibrated heads when a calibration pack is present
    try:
        from .calibration import estimate_with_calibration

        calibrated = estimate_with_calibration(image_bytes, field_id=field_id)
        if calibrated is not None:
            return calibrated
    except Exception as e:
        print(f"[biomass_estimator] calibration path failed, falling back: {e}")

    img_size = int(os.getenv("BIOMASS_IMG_SIZE", "512"))
    img_size = max(224, min(img_size, 1024))
    sample_area = float(os.getenv("BIOMASS_SAMPLE_AREA_M2", "0.25"))

    full, left, right, stream_mode = prepare_dual_streams(image_bytes, img_size=img_size)
    full_stats = stream_vegetation_features(full)
    ok, reason = assess_vegetation_scene(full, full_stats)
    if not ok:
        return rejection_payload(reason, field_id=field_id)

    feature_bundle = extract_features(left, right, full)
    raw_components, meta = predict_components(feature_bundle)
    components, kg_ha, confidence = finalize(
        raw_components, meta["intervals"], sample_area_m2=sample_area
    )

    return {
        "rejected": False,
        "biomass_kg_per_ha": kg_ha,
        "confidence": confidence,
        "model_version": MODEL_VERSION,
        "features": {
            "components": components,
            "intervals": meta["intervals"],
            "scores": meta["scores"],
            "backbone": feature_bundle.get("backbone"),
            "sample_area_m2": sample_area,
            "img_size": img_size,
            "field_id": field_id,
            "green_frac": feature_bundle["fused"].get("green_frac"),
            "dead_frac": feature_bundle["fused"].get("dead_frac"),
            "exg_mean": feature_bundle["fused"].get("exg_mean"),
            "vari_mean": feature_bundle["fused"].get("vari_mean"),
            "stream": stream_mode,
            "cost_model": "local-cpu",
        },
    }
