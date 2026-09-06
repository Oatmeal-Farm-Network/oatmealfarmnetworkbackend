"""Load CSIRO / multi-domain calibration (vegetation ridge or DINOv2 PCA+ridge)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .model import COMPONENT_KEYS, _canopy_scores, BORDERS_DICT, interval_index, interval_confidence
from .features import extract_features, try_dino_embedding, stream_vegetation_features
from .preprocess import prepare_dual_streams
from .postprocess import apply_writeup_postprocess, grams_to_kg_per_ha, overall_confidence
from .scene_gate import assess_vegetation_scene, rejection_payload

_DEFAULT_MULTI = Path(__file__).resolve().parent / "calibration_multidomain.npz"
_DEFAULT_DINO = Path(__file__).resolve().parent / "calibration_dino.npz"
_DEFAULT_VEG = Path(__file__).resolve().parent / "calibration.npz"


@lru_cache(maxsize=2)
def _load_npz(path: str) -> Optional[dict]:
    p = Path(path)
    if not p.is_file():
        return None
    data = np.load(p, allow_pickle=True)
    raw_mode = data["mode"] if "mode" in data.files else "veg_ridge"
    if hasattr(raw_mode, "item"):
        try:
            raw_mode = raw_mode.item()
        except Exception:
            raw_mode = str(raw_mode)
    mode = str(raw_mode).strip()
    out = {
        "mode": mode,
        "weights": {t: data[f"w_{t}"] for t in COMPONENT_KEYS},
    }
    if "model_version" in data.files:
        mv = data["model_version"]
        out["model_version"] = str(mv.item() if hasattr(mv, "item") else mv)
    if mode == "dino_pca_ridge":
        out["pca_components"] = data["pca_components"]
        out["pca_mean"] = data["pca_mean"]
        out["img_size"] = int(data["img_size"]) if "img_size" in data.files else 518
        out["backbone"] = str(data["backbone"]) if "backbone" in data.files else "dinov2_vits14"
    return out


def calibration_path() -> Optional[str]:
    """Prefer multi-domain pack, then CSIRO DINO, then veg, then env override."""
    env = os.getenv("BIOMASS_CALIBRATION_PATH", "").strip()
    force_veg = os.getenv("BIOMASS_FORCE_VEG_CALIB", "").strip().lower() in ("1", "true", "yes")

    if env and Path(env).is_file():
        # Honor explicit path unless it is the old veg pack while better packs exist
        name = Path(env).name
        if force_veg or name not in ("calibration.npz",):
            if name == "calibration.npz" and (_DEFAULT_MULTI.is_file() or _DEFAULT_DINO.is_file()) and not force_veg:
                pass  # fall through to prefer better packs
            else:
                return env

    if _DEFAULT_MULTI.is_file() and not force_veg:
        return str(_DEFAULT_MULTI)
    if _DEFAULT_DINO.is_file() and not force_veg:
        return str(_DEFAULT_DINO)
    if env and Path(env).is_file():
        return env
    if _DEFAULT_VEG.is_file():
        return str(_DEFAULT_VEG)
    return None


def _veg_vector(scores: dict, fused: dict) -> np.ndarray:
    return np.array(
        [
            scores["green_score"],
            scores["dead_score"],
            scores["clover_score"],
            scores["cover"],
            scores["exg_n"],
            scores["vari_n"],
            fused.get("green_frac", 0.0),
            fused.get("dead_frac", 0.0),
            fused.get("soil_frac", 0.0),
            fused.get("brightness_mean", 0.0),
            fused.get("brightness_std", 0.0),
            fused.get("exg_mean", 0.0),
            fused.get("vari_mean", 0.0),
            1.0,
        ],
        dtype=np.float64,
    )


def _dino_vector(left_rgb, right_rgb, scores: dict, fused: dict) -> np.ndarray:
    emb_l = try_dino_embedding(left_rgb)
    emb_r = try_dino_embedding(right_rgb)
    if emb_l is None or emb_r is None:
        raise RuntimeError("DINOv2 required for this calibration but embedding failed")

    def _n(v):
        return v / (np.linalg.norm(v) + 1e-8)

    mean = _n((emb_l + emb_r) / 2.0)
    diff = _n(np.abs(emb_l - emb_r))
    veg = _veg_vector(scores, fused)[:-1]
    return np.concatenate([mean, diff, veg, np.array([1.0])]).astype(np.float64)


def _apply_pca(x: np.ndarray, components: np.ndarray, mean: np.ndarray) -> np.ndarray:
    bias = x[-1:]
    z = x[:-1]
    zr = (z - mean) @ components.T
    return np.concatenate([zr, bias])


def estimate_with_calibration(image_bytes: bytes, field_id: int | None = None) -> Optional[dict]:
    path = calibration_path()
    if not path:
        return None
    pack = _load_npz(path)
    if not pack:
        return None

    mode = pack["mode"]
    try:
        Path(__file__).resolve().parent.joinpath("_calib_debug.txt").write_text(
            f"path={path}\nmode={mode!r}\n", encoding="utf-8"
        )
    except Exception:
        pass
    if mode == "dino_pca_ridge":
        os.environ["BIOMASS_USE_DINO"] = "true"
        img_size = int(os.getenv("BIOMASS_IMG_SIZE", str(pack.get("img_size", 518))))
        img_size = max(224, (img_size // 14) * 14)
    else:
        img_size = int(os.getenv("BIOMASS_IMG_SIZE", "512"))
        img_size = max(224, min(img_size, 1024))

    sample_area = float(os.getenv("BIOMASS_SAMPLE_AREA_M2", "0.25"))
    full, left, right, stream_mode = prepare_dual_streams(image_bytes, img_size=img_size)

    # Scene gate on full-frame vegetation stats (before heavy DINO if possible)
    full_stats = stream_vegetation_features(full)
    ok, reason = assess_vegetation_scene(full, full_stats)
    if not ok:
        return rejection_payload(reason, field_id=field_id)

    bundle = extract_features(left, right, full)
    scores = _canopy_scores(bundle["fused"])
    fused = bundle["fused"]

    if mode == "dino_pca_ridge":
        x = _dino_vector(left, right, scores, fused)
        x = _apply_pca(x, pack["pca_components"], pack["pca_mean"])
        model_version = pack.get("model_version") or "csiro-dinov2-v1"
        backbone = pack.get("backbone", "dinov2_vits14")
    else:
        x = _veg_vector(scores, fused)
        model_version = pack.get("model_version") or "csiro-dual-v1-calibrated"
        backbone = bundle.get("backbone")

    raw = {}
    for t in COMPONENT_KEYS:
        raw[t] = max(0.0, float(np.dot(x, pack["weights"][t])))

    components = apply_writeup_postprocess(raw)
    intervals = {
        k: {
            "bin": interval_index(components[k], BORDERS_DICT[k]),
            "confidence": round(interval_confidence(components[k], BORDERS_DICT[k]), 3),
        }
        for k in COMPONENT_KEYS
    }
    conf = overall_confidence(intervals, components)
    kg_ha = grams_to_kg_per_ha(components["Dry_Total_g"], sample_area)

    return {
        "rejected": False,
        "biomass_kg_per_ha": kg_ha,
        "confidence": conf,
        "model_version": model_version,
        "features": {
            "components": components,
            "intervals": intervals,
            "scores": scores,
            "backbone": backbone,
            "sample_area_m2": sample_area,
            "img_size": img_size,
            "field_id": field_id,
            "green_frac": fused.get("green_frac"),
            "dead_frac": fused.get("dead_frac"),
            "exg_mean": fused.get("exg_mean"),
            "vari_mean": fused.get("vari_mean"),
            "stream": stream_mode,
            "cost_model": "local-dino" if mode == "dino_pca_ridge" else "local-cpu",
            "calibration": path,
            "calibration_mode": mode,
        },
    }
