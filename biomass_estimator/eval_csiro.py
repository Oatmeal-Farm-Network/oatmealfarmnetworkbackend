"""
Evaluate / lightly calibrate the local CSIRO-style biomass estimator
against the downloaded competition train set.

Usage (from backend/ with venv):
  python -m biomass_estimator.eval_csiro --data-dir "C:\\Users\\supra\\Downloads\\csiro-biomass"
  python -m biomass_estimator.eval_csiro --data-dir "..." --calibrate --save-calibration biomass_estimator/calibration.npz
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

# Ensure backend root on path when run as script
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from biomass_estimator.estimator import estimate_biomass_from_image
from biomass_estimator.features import extract_features
from biomass_estimator.preprocess import prepare_dual_streams
from biomass_estimator.model import _canopy_scores, COMPONENT_KEYS

TARGETS = list(COMPONENT_KEYS)


def load_train_wide(data_dir: Path) -> dict:
    """
    Returns {image_path: {target_name: value, ... meta}}
    """
    rows = defaultdict(dict)
    meta = {}
    with open(data_dir / "train.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rel = row["image_path"].replace("\\", "/")
            rows[rel][row["target_name"]] = float(row["target"])
            meta[rel] = {
                "ndvi": float(row["Pre_GSHH_NDVI"]) if row.get("Pre_GSHH_NDVI") not in ("", None) else None,
                "height_cm": float(row["Height_Ave_cm"]) if row.get("Height_Ave_cm") not in ("", None) else None,
                "state": row.get("State"),
                "species": row.get("Species"),
            }
    return rows, meta


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot < 1e-12:
        return 0.0
    return float(1.0 - ss_res / ss_tot)


def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def competition_weighted_r2(per_target_r2: dict) -> float:
    # Approx competition weights from writeup / R² weighting emphasis on Total & GDM
    w = {
        "Dry_Total_g": 0.5,
        "GDM_g": 0.2,
        "Dry_Green_g": 0.1,
        "Dry_Dead_g": 0.1,
        "Dry_Clover_g": 0.1,
    }
    return float(sum(w[k] * per_target_r2[k] for k in TARGETS))


def feature_vector(image_bytes: bytes, img_size: int = 512) -> np.ndarray:
    full, left, right, _mode = prepare_dual_streams(image_bytes, img_size=img_size)
    bundle = extract_features(left, right, full)
    scores = _canopy_scores(bundle["fused"])
    fused = bundle["fused"]
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
            1.0,  # bias
        ],
        dtype=np.float64,
    )


def run_baseline(data_dir: Path, image_rels: list, labels: dict, img_size: int):
    preds = {t: [] for t in TARGETS}
    trues = {t: [] for t in TARGETS}
    missing = 0
    for i, rel in enumerate(image_rels):
        path = data_dir / rel
        if not path.is_file():
            missing += 1
            continue
        raw = path.read_bytes()
        out = estimate_biomass_from_image(raw)
        comps = out["features"]["components"]
        for t in TARGETS:
            preds[t].append(float(comps[t]))
            trues[t].append(float(labels[rel][t]))
        if (i + 1) % 50 == 0:
            print(f"  baseline {i+1}/{len(image_rels)}")
    return preds, trues, missing


def fit_ridge(X: np.ndarray, y: np.ndarray, l2: float = 1.0) -> np.ndarray:
    """Closed-form ridge: (X'X + λI)^{-1} X'y. Last column is bias (no penalty)."""
    xtx = X.T @ X
    n = xtx.shape[0]
    reg = np.eye(n) * l2
    reg[-1, -1] = 0.0  # don't penalize bias
    return np.linalg.solve(xtx + reg, X.T @ y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--img-size", type=int, default=512)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--save-calibration", type=str, default="")
    ap.add_argument("--max-images", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    os.environ.setdefault("BIOMASS_USE_DINO", "false")
    os.environ["BIOMASS_IMG_SIZE"] = str(args.img_size)

    labels, meta = load_train_wide(data_dir)
    images = sorted(labels.keys())
    if args.max_images > 0:
        images = images[: args.max_images]

    rng = np.random.default_rng(args.seed)
    idx = np.arange(len(images))
    rng.shuffle(idx)
    n_val = max(1, int(len(images) * args.val_frac))
    val_idx = set(idx[:n_val].tolist())
    train_rels = [images[i] for i in idx if i not in val_idx]
    val_rels = [images[i] for i in idx if i in val_idx]

    print(f"Dataset: {data_dir}")
    print(f"Images available in CSV: {len(images)} | train={len(train_rels)} val={len(val_rels)}")

    print("\n=== Baseline estimator (csiro-dual-v1 heuristics) on VAL ===")
    preds, trues, missing = run_baseline(data_dir, val_rels, labels, args.img_size)
    print(f"Missing files: {missing}")
    base_r2 = {}
    for t in TARGETS:
        base_r2[t] = r2_score(trues[t], preds[t])
        print(f"  {t:14s}  R2={base_r2[t]:+.3f}  MAE={mae(trues[t], preds[t]):.2f}  "
              f"mean_true={np.mean(trues[t]):.1f} mean_pred={np.mean(preds[t]):.1f}")
    print(f"  Weighted R2 ~ {competition_weighted_r2(base_r2):+.3f}")

    if not args.calibrate:
        print("\nRe-run with --calibrate to fit ridge heads on train fold and re-score val.")
        return

    print("\n=== Fitting ridge calibration on TRAIN features ===")
    X_train, y_train = [], defaultdict(list)
    for i, rel in enumerate(train_rels):
        path = data_dir / rel
        if not path.is_file():
            continue
        X_train.append(feature_vector(path.read_bytes(), args.img_size))
        for t in TARGETS:
            y_train[t].append(labels[rel][t])
        if (i + 1) % 50 == 0:
            print(f"  features {i+1}/{len(train_rels)}")
    X_train = np.vstack(X_train)
    weights = {t: fit_ridge(X_train, np.asarray(y_train[t], dtype=np.float64), l2=2.0) for t in TARGETS}
    print(f"  trained on {X_train.shape[0]} images, feat_dim={X_train.shape[1]}")

    print("\n=== Calibrated ridge heads on VAL ===")
    X_val, y_val_t, y_val_p = [], defaultdict(list), defaultdict(list)
    for rel in val_rels:
        path = data_dir / rel
        if not path.is_file():
            continue
        x = feature_vector(path.read_bytes(), args.img_size)
        X_val.append(x)
        for t in TARGETS:
            pred = float(np.dot(x, weights[t]))
            pred = max(0.0, pred)
            y_val_p[t].append(pred)
            y_val_t[t].append(labels[rel][t])
    # Physics post-hoc on calibrated preds
    for i in range(len(X_val)):
        green = y_val_p["Dry_Green_g"][i]
        dead = y_val_p["Dry_Dead_g"][i]
        clover = y_val_p["Dry_Clover_g"][i] * 0.8
        if dead > 20:
            dead *= 1.1
        elif dead < 10:
            dead *= 0.9
        gdm = green + clover
        total = gdm + dead
        y_val_p["Dry_Clover_g"][i] = clover
        y_val_p["Dry_Dead_g"][i] = dead
        y_val_p["GDM_g"][i] = gdm
        y_val_p["Dry_Total_g"][i] = total

    cal_r2 = {}
    for t in TARGETS:
        cal_r2[t] = r2_score(y_val_t[t], y_val_p[t])
        print(f"  {t:14s}  R2={cal_r2[t]:+.3f}  MAE={mae(y_val_t[t], y_val_p[t]):.2f}  "
              f"mean_true={np.mean(y_val_t[t]):.1f} mean_pred={np.mean(y_val_p[t]):.1f}")
    print(f"  Weighted R2 ~ {competition_weighted_r2(cal_r2):+.3f}")

    if args.save_calibration:
        out = Path(args.save_calibration)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            out,
            **{f"w_{t}": weights[t] for t in TARGETS},
            feature_names=np.array([
                "green_score", "dead_score", "clover_score", "cover", "exg_n", "vari_n",
                "green_frac", "dead_frac", "soil_frac", "brightness_mean", "brightness_std",
                "exg_mean", "vari_mean", "bias",
            ]),
            img_size=args.img_size,
            n_train=X_train.shape[0],
            val_weighted_r2=competition_weighted_r2(cal_r2),
            baseline_weighted_r2=competition_weighted_r2(base_r2),
        )
        print(f"\nSaved calibration → {out.resolve()}")
        print("Set BIOMASS_CALIBRATION_PATH to this file to use it at inference.")


if __name__ == "__main__":
    main()
