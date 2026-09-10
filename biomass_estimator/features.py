"""Vegetation proxy features (CPU) + optional DINOv2 embeddings."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import numpy as np

# Lazy torch state
_dino_model = None
_dino_device = None
_dino_failed = False


def _exg(rgb: np.ndarray) -> np.ndarray:
    """Excess Green index."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return 2.0 * g - r - b


def _vari(rgb: np.ndarray) -> np.ndarray:
    """Visible Atmospherically Resistant Index."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    denom = g + r - b
    denom = np.where(np.abs(denom) < 1e-6, 1e-6, denom)
    return (g - r) / denom


def stream_vegetation_features(rgb: np.ndarray) -> Dict[str, float]:
    """Compact canopy descriptors for one stream (H,W,3) in [0,1]."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    exg = _exg(rgb)
    vari = _vari(rgb)
    brightness = (r + g + b) / 3.0
    # Green pixel fraction: g dominant and reasonably bright
    green_mask = (g > r * 1.05) & (g > b * 1.05) & (g > 0.15)
    green_frac = float(np.mean(green_mask))
    # Dead / brown-ish: high red relative, mid brightness
    dead_mask = (r > g * 1.02) & (r > b) & (brightness > 0.12) & (brightness < 0.75)
    dead_frac = float(np.mean(dead_mask))
    # Soil / bare: low saturation-ish
    soil_mask = (np.abs(r - g) < 0.08) & (np.abs(g - b) < 0.08) & (brightness > 0.2)
    soil_frac = float(np.mean(soil_mask))

    return {
        "exg_mean": float(np.mean(exg)),
        "exg_p75": float(np.percentile(exg, 75)),
        "vari_mean": float(np.clip(np.mean(vari), -1.0, 1.0)),
        "green_frac": green_frac,
        "dead_frac": dead_frac,
        "soil_frac": soil_frac,
        "brightness_mean": float(np.mean(brightness)),
        "brightness_std": float(np.std(brightness)),
    }


def fuse_stream_features(left: Dict[str, float], right: Dict[str, float]) -> Dict[str, float]:
    """Mean/max fuse of left/right streams (CSIRO dual-view idea without attention)."""
    fused = {}
    for k in left:
        fused[k] = (left[k] + right[k]) / 2.0
        fused[f"{k}_max"] = max(left[k], right[k])
        fused[f"{k}_delta"] = abs(left[k] - right[k])
    return fused


def try_dino_embedding(rgb: np.ndarray) -> Optional[np.ndarray]:
    """
    Optional DINOv2 ViT-S/14 global embedding.
    Returns None if disabled, torch missing, or load/inference fails.
    """
    global _dino_model, _dino_device, _dino_failed

    use = os.getenv("BIOMASS_USE_DINO", "false").strip().lower() in ("1", "true", "yes", "on")
    if not use or _dino_failed:
        return None

    try:
        import torch
        from .preprocess import to_imagenet_tensor
    except Exception:
        _dino_failed = True
        return None

    try:
        if _dino_model is None:
            _dino_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _dino_model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", pretrained=True)
            _dino_model.eval()
            _dino_model.to(_dino_device)

        x = to_imagenet_tensor(rgb)
        t = torch.from_numpy(x).unsqueeze(0).to(_dino_device)
        # DINOv2 expects multiple of 14
        h, w = t.shape[-2], t.shape[-1]
        nh, nw = (h // 14) * 14, (w // 14) * 14
        if nh < 14 or nw < 14:
            return None
        t = t[..., :nh, :nw]
        with torch.no_grad():
            feat = _dino_model(t)
        return feat.squeeze(0).detach().cpu().numpy().astype(np.float32)
    except Exception as e:
        print(f"[biomass_estimator] DINO unavailable, using vegetation proxies: {e}")
        _dino_failed = True
        return None


def extract_features(left_rgb: np.ndarray, right_rgb: np.ndarray, full_rgb: np.ndarray) -> Dict[str, Any]:
    left_f = stream_vegetation_features(left_rgb)
    right_f = stream_vegetation_features(right_rgb)
    fused = fuse_stream_features(left_f, right_f)
    full_f = stream_vegetation_features(full_rgb)

    dino_l = try_dino_embedding(left_rgb)
    dino_r = try_dino_embedding(right_rgb)
    backbone = "vegetation-proxy"
    dino_norm = None
    if dino_l is not None and dino_r is not None:
        emb = (dino_l + dino_r) / 2.0
        dino_norm = float(np.linalg.norm(emb))
        # Light modulation of green_frac from embedding energy (no trained head yet)
        fused["dino_norm"] = dino_norm
        backbone = "dinov2_vits14+vegetation-proxy"

    return {
        "left": left_f,
        "right": right_f,
        "fused": fused,
        "full": full_f,
        "backbone": backbone,
        "dino_norm": dino_norm,
    }
